"""
AI Vision Analysis API endpoint
"""

from ninja import Router, UploadedFile, File
from pydantic import BaseModel
from typing import Optional, Dict, Any
from decimal import Decimal
from datetime import datetime
import logging

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip

logger = logging.getLogger(__name__)

# Magic bytes for allowed image formats
IMAGE_MAGIC_BYTES = [
    b'\xff\xd8\xff',           # JPEG
    b'\x89PNG\r\n\x1a\n',     # PNG
    b'GIF87a',                 # GIF87
    b'GIF89a',                 # GIF89
    b'RIFF',                   # WebP (RIFF....WEBP)
    b'BM',                     # BMP
]

def _is_valid_image_magic(file_obj) -> bool:
    """Check file magic bytes to verify it's actually an image."""
    header = file_obj.read(12)
    file_obj.seek(0)
    # WebP: RIFF + 4 bytes + WEBP
    if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        return True
    return any(header[:len(magic)] == magic for magic in IMAGE_MAGIC_BYTES if magic != b'RIFF')

ai_router = Router()


class PricingOption(BaseModel):
    type: str
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    period: Optional[str] = None


class AIAnalysisResponse(BaseModel):
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    category_confidence: float
    title: str
    description: str
    suggested_price: Optional[PricingOption] = None
    confidence: float
    provider: str
    log_id: int  # ID of AIAnalysisLog entry for tracking


@ai_router.post("/analyze-image/", response={200: AIAnalysisResponse, 400: dict, 429: dict, 503: dict}, auth=ProfileAuth())
@ratelimit(group='ai:analyze', key=user_or_ip, rate='5/m', method='POST')
def analyze_item_image(request, image: UploadedFile):
    """
    Analyze item image using AI vision API

    Supports: Claude Sonnet 4.5, OpenAI GPT-5, Google Cloud Vision
    Quota: 30 analyses per day per account (shared across all profiles)
    """
    from parahub.services.vision_ai import AIVisionService
    from parahub.services.quota import QuotaService, QuotaExceeded
    from parahub.models import AISettings, AIAnalysisLog
    from taxonomy.models import Category
    import time

    logger.info(f"AI analyze endpoint called by {request.auth_profile.id}")
    logger.info(f"Image received: {image}, type: {type(image)}, content_type: {getattr(image, 'content_type', 'N/A')}")

    start_time = time.time()
    original_size = image.size
    log_entry = None

    try:
        # Check quota BEFORE processing image
        account_id = request.auth_profile.account_id
        try:
            quota_info = QuotaService.check_quota(account_id, 'ai_analysis')
            if quota_info['remaining'] <= 0:
                logger.warning(f"Quota exceeded for account {account_id}: {quota_info}")
                return 429, {
                    "error": "Daily AI analysis quota exceeded",
                    "quota": quota_info
                }
        except Exception as e:
            logger.error(f"Quota check failed: {e}", exc_info=True)
            # Continue if quota service fails (don't block users due to service error)

    except Exception as e:
        logger.error(f"Error in quota check: {e}", exc_info=True)
        return 400, {"error": f"Failed to check quota: {str(e)}"}

    try:
        # Validate image — content_type + magic bytes (content_type can be spoofed)
        if not image.content_type.startswith('image/') or not _is_valid_image_magic(image.file):
            logger.warning(f"Invalid content type: {image.content_type}")
            # Log validation failure
            ai_settings = AISettings.get_instance()
            AIAnalysisLog.objects.create(
                profile=request.auth_profile,
                image_filename=getattr(image, 'name', 'unknown'),
                image_size_original=original_size,
                image_size_compressed=0,
                provider=ai_settings.provider if ai_settings.enabled else 'unknown',
                processing_time_ms=int((time.time() - start_time) * 1000),
                error_message=f"Invalid content type: {image.content_type}"
            )
            return 400, {"error": "File must be an image"}

        if image.size > 10 * 1024 * 1024:
            logger.warning(f"File too large: {image.size} bytes")
            # Log validation failure
            ai_settings = AISettings.get_instance()
            AIAnalysisLog.objects.create(
                profile=request.auth_profile,
                image_filename=getattr(image, 'name', 'unknown'),
                image_size_original=original_size,
                image_size_compressed=0,
                provider=ai_settings.provider if ai_settings.enabled else 'unknown',
                processing_time_ms=int((time.time() - start_time) * 1000),
                error_message=f"File too large: {image.size} bytes (max 10MB)"
            )
            return 400, {"error": "Image size must be less than 10MB"}

        # Read and compress image if needed (Claude has 5MB limit)
        from PIL import Image
        from io import BytesIO

        img = Image.open(image.file)

        # Convert to RGB if needed
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')

        # Resize if too large (max 1920px on longest side for AI analysis)
        max_size = 1920
        if img.width > max_size or img.height > max_size:
            ratio = min(max_size / img.width, max_size / img.height)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        # Compress to JPEG with quality adjustment to stay under 5MB
        output = BytesIO()
        quality = 85
        while quality > 20:
            output.seek(0)
            output.truncate()
            img.save(output, format='JPEG', quality=quality, optimize=True)
            if output.tell() < 5 * 1024 * 1024:  # Under 5MB
                break
            quality -= 10

        image_data = output.getvalue()
        logger.info(f"Image compressed: original {image.size} bytes, compressed {len(image_data)} bytes")

        # Get user's preferred language and currency
        # Fallback to cookie if profile language is not set (user may have selected language before auth)
        user_language = request.auth_profile.preferred_language
        if not user_language:
            # Try to get from cookie
            user_language = request.COOKIES.get('preferred_language', 'en')
            logger.info(f"Using language from cookie: {user_language}")

        user_currency = request.auth_profile.preferred_currency or 'EUR'

        # Analyze (pass user_id for WebSocket progress updates)
        try:
            result = AIVisionService.analyze_item_image(
                image_data,
                language=user_language,
                user_currency=user_currency,
                user_id=request.auth_profile.account_id  # For WS notifications
            )
        except ValueError as e:
            return 503, {"error": str(e)}

        # Get category name
        category_name = None
        if result.get('category_id'):
            try:
                category = Category.objects.get(id=result['category_id'])
                category_name = category.name
            except Category.DoesNotExist:
                logger.warning(f"AI suggested non-existent category: {result['category_id']}")

        # Get providers
        ai_settings = AISettings.get_instance()
        vision_provider = ai_settings.provider if ai_settings.enabled else 'unknown'
        categorization_provider = ai_settings.categorization_provider if ai_settings.enabled else 'unknown'

        # Calculate total processing time
        processing_time_ms = int((time.time() - start_time) * 1000)

        # Extract separate timings
        vision_processing_time_ms = result.get('vision_processing_time_ms')
        categorization_processing_time_ms = result.get('categorization_processing_time_ms')

        # Get category object for logging
        category_obj = None
        if result.get('category_id'):
            try:
                category_obj = Category.objects.get(id=result['category_id'])
            except Category.DoesNotExist:
                pass

        # Convert suggested_price Decimal to float for JSONField
        suggested_price_data = result.get('suggested_price')
        if suggested_price_data and suggested_price_data.get('amount'):
            suggested_price_data = suggested_price_data.copy()
            suggested_price_data['amount'] = float(suggested_price_data['amount'])

        # Extract vision usage info (step 1)
        vision_usage = result.get('vision_usage', {})
        vision_input_tokens = vision_usage.get('input_tokens') if vision_usage else None
        vision_output_tokens = vision_usage.get('output_tokens') if vision_usage else None
        vision_cost = vision_usage.get('estimated_cost_usd') if vision_usage else None

        # Extract categorization usage info (step 2)
        cat_usage = result.get('categorization_usage', {})
        cat_input_tokens = cat_usage.get('input_tokens') if cat_usage else None
        cat_output_tokens = cat_usage.get('output_tokens') if cat_usage else None
        cat_cost = cat_usage.get('estimated_cost_usd') if cat_usage else None

        # Legacy fields (total)
        total_input_tokens = (vision_input_tokens or 0) + (cat_input_tokens or 0)
        total_output_tokens = (vision_output_tokens or 0) + (cat_output_tokens or 0)
        total_cost = (vision_cost or 0) + (cat_cost or 0)

        # Save log
        log_entry = AIAnalysisLog.objects.create(
            profile=request.auth_profile,
            language=user_language,
            image_filename=getattr(image, 'name', 'unknown'),
            image_size_original=original_size,
            image_size_compressed=len(image_data),
            vision_provider=vision_provider,
            categorization_provider=categorization_provider,
            suggested_category=category_obj,
            suggested_category_confidence=result.get('category_confidence', 0.8),
            suggested_title=result.get('title', ''),
            suggested_description=result.get('description', ''),
            suggested_price=suggested_price_data,
            overall_confidence=result.get('confidence', 0.8),
            processing_time_ms=processing_time_ms,
            vision_processing_time_ms=vision_processing_time_ms,
            categorization_processing_time_ms=categorization_processing_time_ms,
            vision_input_tokens=vision_input_tokens,
            vision_output_tokens=vision_output_tokens,
            vision_cost_usd=vision_cost,
            categorization_input_tokens=cat_input_tokens,
            categorization_output_tokens=cat_output_tokens,
            categorization_cost_usd=cat_cost,
            input_tokens=total_input_tokens if total_input_tokens > 0 else None,
            output_tokens=total_output_tokens if total_output_tokens > 0 else None,
            estimated_cost_usd=total_cost if total_cost > 0 else None,
            # Raw data for debugging/transparency
            vision_request_prompt=result.get('vision_raw_prompt', ''),
            vision_response_raw=result.get('vision_raw_response', ''),
            categorization_request_prompt=result.get('categorization_raw_prompt', ''),
            categorization_response_raw=result.get('categorization_raw_response', '')
        )

        # Update usage stats
        ai_settings.total_requests += 1
        ai_settings.save(update_fields=['total_requests'])

        # Consume quota (after successful analysis)
        try:
            QuotaService.consume_quota(
                account_id=request.auth_profile.account_id,
                resource_type='ai_analysis',
                metadata={'log_id': log_entry.id}
            )
        except QuotaExceeded as e:
            # This should not happen (we checked before), but handle gracefully
            logger.error(f"Quota exceeded after analysis (race condition?): {e}")
        except Exception as e:
            # Don't fail the response if quota logging fails
            logger.error(f"Failed to consume quota: {e}", exc_info=True)

        logger.info(f"AI analysis completed for user {request.auth_profile.id} using vision={vision_provider}, cat={categorization_provider} in {processing_time_ms}ms (log_id={log_entry.id})")

        return 200, AIAnalysisResponse(
            category_id=result.get('category_id'),
            category_name=category_name,
            category_confidence=result.get('category_confidence', 0.8),
            title=result.get('title', ''),
            description=result.get('description', ''),
            suggested_price=result.get('suggested_price'),
            confidence=result.get('confidence', 0.8),
            provider=vision_provider,
            log_id=log_entry.id
        )

    except Exception as e:
        # Log error
        processing_time_ms = int((time.time() - start_time) * 1000)

        ai_settings = AISettings.get_instance()
        log_entry = AIAnalysisLog.objects.create(
            profile=request.auth_profile,
            image_filename=getattr(image, 'name', 'unknown'),
            image_size_original=original_size,
            image_size_compressed=0,
            vision_provider=ai_settings.provider if ai_settings.enabled else 'unknown',
            categorization_provider=ai_settings.categorization_provider if ai_settings.enabled else 'unknown',
            processing_time_ms=processing_time_ms,
            error_message=str(e)
        )

        logger.error(f"Error analyzing image: {e} (log_id={log_entry.id})", exc_info=True)
        return 400, {"error": f"Failed to analyze image: {str(e)}"}


class VoiceListingPricingOption(BaseModel):
    type: str  # sale, rent, free
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    unit: Optional[str] = None
    note: Optional[str] = None


class VoiceListingResponse(BaseModel):
    transcript: str
    title: str
    description: str
    item_type: Optional[str] = None  # CREDIT or DEBIT
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    pricing_options: list[VoiceListingPricingOption] = []
    is_international: bool = False
    confidence: float = 0.8
    error_message: Optional[str] = None


@ai_router.post("/voice-to-listing/", response={200: VoiceListingResponse, 400: dict, 429: dict, 503: dict}, auth=ProfileAuth())
@ratelimit(group='ai:voice', key=user_or_ip, rate='5/m', method='POST')
def voice_to_listing(request, audio: UploadedFile):
    """
    Convert voice recording to structured marketplace listing data.
    Transcribes audio via ElevenLabs STT, then uses Gemini Flash to extract listing fields.
    """
    from parahub.services.vision_ai import AIVisionService, build_category_list
    from parahub.services.quota import QuotaService, QuotaExceeded
    from parahub.models import AISettings
    from taxonomy.models import Category
    import httpx
    import json
    import time
    from pathlib import Path
    from google import genai
    from google.genai import types as genai_types

    start_time = time.time()

    # Check quota
    account_id = request.auth_profile.account_id
    try:
        quota_info = QuotaService.check_quota(account_id, 'ai_analysis')
        if quota_info['remaining'] <= 0:
            return 429, {"error": "Daily AI analysis quota exceeded", "quota": quota_info}
    except Exception as e:
        logger.error(f"Quota check failed: {e}", exc_info=True)

    # Validate audio size (max 25MB for ElevenLabs STT)
    audio_bytes = audio.read()
    if len(audio_bytes) < 1000:
        return 400, {"error": "Audio too short"}
    if len(audio_bytes) > 25 * 1024 * 1024:
        return 400, {"error": "Audio file too large (max 25MB)"}

    # Step 1: Transcribe audio via ElevenLabs STT
    elevenlabs_key_file = Path('/opt/parahub/.agents/.elevenlabs_key')
    if not elevenlabs_key_file.exists():
        return 503, {"error": "Speech-to-text service not configured"}
    elevenlabs_key = elevenlabs_key_file.read_text().strip()

    content_type = getattr(audio, 'content_type', 'audio/webm')
    ext = 'webm' if 'webm' in content_type else 'wav'

    try:
        resp = httpx.post(
            'https://api.elevenlabs.io/v1/speech-to-text',
            headers={'xi-api-key': elevenlabs_key},
            files={'file': (f'audio.{ext}', audio_bytes, content_type)},
            data={'model_id': 'scribe_v1'},
            timeout=30,
        )
        if resp.status_code != 200:
            logger.error(f"ElevenLabs STT error: {resp.status_code} {resp.text}")
            return 503, {"error": "Speech-to-text service error"}
        transcript = resp.json().get('text', '').strip()
    except Exception as e:
        logger.error(f"STT failed: {e}", exc_info=True)
        return 503, {"error": "Speech-to-text service unavailable"}

    if not transcript or len(transcript) < 3:
        return 200, VoiceListingResponse(
            transcript=transcript or '',
            title='',
            description='',
            error_message="Could not understand the recording. Please try again, speaking more clearly."
        )

    logger.info(f"Voice transcript for {request.auth_profile.id}: {transcript[:200]}")

    # Step 2: Get categories and user preferences
    categories = AIVisionService._get_categories()
    category_list, index_to_id = build_category_list(categories)

    user_language = request.auth_profile.preferred_language
    if not user_language:
        user_language = request.COOKIES.get('preferred_language', 'en')
    user_currency = request.auth_profile.preferred_currency or 'EUR'

    lang_names = {'en': 'English', 'ru': 'Russian', 'pt': 'Portuguese', 'es': 'Spanish', 'fr': 'French', 'de': 'German'}
    lang_name = lang_names.get(user_language, 'English')

    # Step 3: Send transcript + categories to Gemini Flash
    ai_settings = AISettings.get_instance()
    if not ai_settings.enabled or not ai_settings.google_api_key:
        return 503, {"error": "AI service not configured"}

    prompt = f"""You are a marketplace listing assistant. A user dictated what they want to post on a marketplace.
Extract structured listing data from their speech.

User's speech transcript:
"{transcript}"

User's preferred currency: {user_currency}
Respond in: {lang_name}

Available categories ({len(categories)} total, format: number:name):
{category_list}

Respond with ONLY a valid JSON object (no markdown, no explanations):
{{
    "title": "short listing title (max 80 chars), in {lang_name}",
    "description": "detailed description based on what user said, in {lang_name}",
    "item_type": "CREDIT if user offers/sells something, DEBIT if user needs/wants something, null if unclear",
    "category_index": number of the most appropriate category from the list above (or null if none fits),
    "pricing_options": [
        {{
            "type": "sale or rent or free",
            "amount": number or null,
            "currency": "{user_currency}",
            "unit": "optional unit like kg, hour, pcs, or null"
        }}
    ],
    "is_international": false,
    "confidence": 0.0 to 1.0,
    "error_message": "null if understood well, or a brief message in {lang_name} explaining what was unclear"
}}

Rules:
- Extract title and description from what the user said
- If the user mentioned a price, include it in pricing_options
- If no price mentioned, set pricing_options to a single sale option with null amount
- If the user said "free" or "for free", use type "free"
- If the user is looking for something (wants, needs, searching for), set item_type to "DEBIT"
- If the user is offering something (selling, giving, renting out), set item_type to "CREDIT"
- Choose the MOST SPECIFIC category by its NUMBER from the list
- If the listing is for remote services or digital goods, set is_international to true
- If the speech is too vague or you can't determine what the listing should be about, set confidence below 0.3 and write a helpful error_message"""

    try:
        client = genai.Client(api_key=ai_settings.google_api_key)
        response = client.models.generate_content(
            model='gemini-3.1-flash-lite-preview',
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=2048,
                response_mime_type='application/json'
            )
        )

        response_text = response.text if hasattr(response, 'text') else None
        if not response_text:
            return 503, {"error": "AI returned empty response"}

        response_text = response_text.strip()
        # Remove markdown code blocks if present
        if response_text.startswith("```"):
            lines = response_text.split('\n')
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            response_text = '\n'.join(lines).strip()

        result = json.loads(response_text)

    except Exception as e:
        logger.error(f"Gemini voice-to-listing error: {e}", exc_info=True)
        return 503, {"error": f"AI processing failed: {str(e)}"}

    # Convert category_index to category_id
    category_index = result.get('category_index')
    category_id = index_to_id.get(category_index) if category_index else None
    category_name = None
    if category_id:
        try:
            cat = Category.objects.get(id=category_id)
            category_name = cat.name
        except Category.DoesNotExist:
            category_id = None

    # Build pricing options
    pricing_options = []
    for po in result.get('pricing_options', []):
        pricing_options.append(VoiceListingPricingOption(
            type=po.get('type', 'sale'),
            amount=Decimal(str(po['amount'])) if po.get('amount') else None,
            currency=po.get('currency', user_currency),
            unit=po.get('unit'),
            note=po.get('note'),
        ))
    if not pricing_options:
        pricing_options = [VoiceListingPricingOption(type='sale', currency=user_currency)]

    # Consume quota
    try:
        QuotaService.consume_quota(
            account_id=account_id,
            resource_type='ai_analysis',
            metadata={'source': 'voice_to_listing'}
        )
    except Exception as e:
        logger.error(f"Failed to consume quota: {e}", exc_info=True)

    processing_ms = int((time.time() - start_time) * 1000)
    logger.info(f"Voice-to-listing completed for {request.auth_profile.id} in {processing_ms}ms, confidence={result.get('confidence', 0.8)}")

    return 200, VoiceListingResponse(
        transcript=transcript,
        title=result.get('title', ''),
        description=result.get('description', ''),
        item_type=result.get('item_type'),
        category_id=category_id,
        category_name=category_name,
        pricing_options=pricing_options,
        is_international=result.get('is_international', False),
        confidence=result.get('confidence', 0.8),
        error_message=result.get('error_message'),
    )


class QuotaInfoResponse(BaseModel):
    remaining: int
    limit: int
    used: int
    reset_at: datetime


@ai_router.get("/usage-quota/", response=QuotaInfoResponse, auth=ProfileAuth())
@ratelimit(group='ai:usage_quota', key=user_or_ip, rate='60/m')
def get_usage_quota(request):
    """
    Get current AI analysis quota for authenticated user's account

    Returns:
        {
            "remaining": 25,
            "limit": 30,
            "used": 5,
            "reset_at": "2025-11-04T00:00:00Z"
        }
    """
    from parahub.services.quota import QuotaService

    account_id = request.auth_profile.account_id
    quota_info = QuotaService.check_quota(account_id, 'ai_analysis')

    return QuotaInfoResponse(**quota_info)
