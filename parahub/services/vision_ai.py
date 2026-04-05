"""
AI Vision Service for item image analysis
Supports Claude, OpenAI, and Google Cloud Vision APIs
"""

import base64
import logging
from typing import Dict, Any, Optional, List
from decimal import Decimal
import anthropic
import openai
from google.cloud import vision
from google.oauth2 import service_account
from google import genai
from google.genai import types as genai_types
import json
import time
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


def build_category_list(categories: List[Dict[str, str]]) -> tuple[str, Dict[int, str]]:
    """
    Build compact numbered category list for AI prompts

    Returns:
        - category_list: Compact string (e.g., "1:Electronics,2:Books,3:Toys")
        - index_to_id: Mapping from index to ULID
    """
    index_to_id = {}
    category_items = []

    for idx, cat in enumerate(categories, start=1):
        index_to_id[idx] = cat['id']
        category_items.append(f"{idx}:{cat['name']}")

    category_list = ",".join(category_items)
    return category_list, index_to_id


class AIVisionProvider:
    """Base class for AI vision providers - extracts title/description/price from image"""

    def analyze_image(self, image_data: bytes, language: str = 'en') -> Dict[str, Any]:
        """
        Analyze image and return title, description, price (NO category)

        Args:
            image_data: Raw image bytes
            language: User's preferred language code (en, ru, pt, es, fr, etc.)

        Returns:
            {
                'title': str,
                'description': str,
                'suggested_price': {
                    'type': 'sale',
                    'amount': Decimal,
                    'currency': 'EUR'
                },
                'confidence': float (0-1),
                'usage': {  # Optional
                    'input_tokens': int,
                    'output_tokens': int,
                    'estimated_cost_usd': float
                }
            }
        """
        raise NotImplementedError

    def analyze_with_categories(self, image_data: bytes, categories: List[Dict[str, str]], language: str = 'en') -> Dict[str, Any]:
        """
        Analyze image AND select category in ONE request (optimization for same provider)

        Args:
            image_data: Raw image bytes
            categories: ALL available categories with id, name, slug
            language: User's preferred language code

        Returns:
            {
                'title': str,
                'description': str,
                'suggested_price': {...},
                'category_id': str,
                'category_confidence': float,
                'confidence': float,
                'usage': {...}
            }
        """
        # Default implementation: not supported, return None
        return None


class AICategorizationProvider:
    """Base class for AI categorization providers - selects category from text"""

    def categorize_from_text(self, title: str, description: str, categories: List[Dict[str, str]], language: str = 'en') -> Dict[str, Any]:
        """
        Categorize item based on title and description

        Args:
            title: Item title
            description: Item description
            categories: ALL available categories with id, name, slug
            language: User's preferred language code

        Returns:
            {
                'category_id': str (ULID),
                'category_confidence': float (0-1),
                'usage': {
                    'input_tokens': int,
                    'output_tokens': int,
                    'estimated_cost_usd': float
                }
            }
        """
        raise NotImplementedError


class ClaudeVisionProvider(AIVisionProvider):
    """Anthropic Claude Vision API provider (Haiku 4.5)"""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def analyze_image(self, image_data: bytes, language: str = 'en') -> Dict[str, Any]:
        # Encode image to base64
        image_b64 = base64.b64encode(image_data).decode('utf-8')

        # Language-specific instructions
        language_map = {
            'ru': 'Russian (русский)',
            'en': 'English',
            'pt': 'Portuguese (português)',
            'es': 'Spanish (español)',
            'fr': 'French (français)',
            'de': 'German (deutsch)',
            'it': 'Italian (italiano)',
            'zh': 'Chinese (中文)',
            'ja': 'Japanese (日本語)',
            'ko': 'Korean (한국어)'
        }
        language_name = language_map.get(language, 'English')

        prompt = f"""Analyze this product image and provide title, description, and price estimate in JSON format.

IMPORTANT: Generate the title and description in {language_name}. The user's preferred language is {language_name}, so all text fields MUST be written in {language_name}.

Respond with ONLY a valid JSON object (no markdown, no explanations) with this structure:
{{
    "title": "Short descriptive title (3-50 words) in {language_name}",
    "description": "Detailed description (50-200 words) in {language_name}",
    "suggested_price_eur": estimated price in EUR as a number (or null if cannot estimate),
    "confidence": 0.0 to 1.0
}}

Rules:
- Title and description MUST be written in {language_name}
- Title should be concise and descriptive
- Price should be realistic market value in EUR
- Set confidence based on image clarity and your certainty

CRITICAL - Description writing style:
- Write as if you are the SELLER describing YOUR item for sale
- Use first person perspective ("selling", "offering") or neutral description
- NEVER use phrases like "on the image", "in the photo", "shown", "depicted", "presented"
- Describe the SPECIFIC item in the photo, not general facts about the product category
- Mention actual condition, visible features, defects, damages, wear if present
- Focus on what makes THIS specific item unique or notable
- Keep it practical and honest - don't oversell with marketing language about vitamins/health benefits unless directly relevant
- If item looks new/unused, mention it. If used/worn, describe the condition honestly

Example BAD description (DO NOT DO THIS):
"На изображении представлен апельсин. Апельсины богаты витамином С..."

Example GOOD description:
"Свежие апельсины, 5 штук. Куплены вчера на рынке, один немного помят с боку. Остальные в отличном состоянии."

Example GOOD description:
"Ноутбук Dell XPS 15. Использовался 2 года, царапины на крышке, батарея держит около 3 часов. Работает без проблем, все порты исправны."
"""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=4096,  # High limit, let AI decide
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_b64
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }]
            )

            # Parse response
            response_text = message.content[0].text.strip()
            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            result = json.loads(response_text)

            # Extract usage info
            usage_info = None
            if hasattr(message, 'usage'):
                input_tokens = getattr(message.usage, 'input_tokens', 0)
                output_tokens = getattr(message.usage, 'output_tokens', 0)
                # Haiku 4.5 pricing (verified 2025-11-01): $1/1M input, $5/1M output
                cost = (input_tokens * 1.0 / 1_000_000) + (output_tokens * 5.0 / 1_000_000)
                usage_info = {
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'estimated_cost_usd': cost
                }

            # Convert to standard format
            return {
                'title': result.get('title', ''),
                'description': result.get('description', ''),
                'suggested_price': {
                    'type': 'sale',
                    'amount': Decimal(str(result['suggested_price_eur'])) if result.get('suggested_price_eur') else None,
                    'currency': 'EUR'
                } if result.get('suggested_price_eur') else None,
                'confidence': result.get('confidence', 0.8),
                'usage': usage_info,
                'raw_prompt': prompt,
                'raw_response': response_text
            }

        except Exception as e:
            logger.error(f"Claude API error: {e}")
            raise

    def analyze_with_categories(self, image_data: bytes, categories: List[Dict[str, str]], language: str = 'en') -> Dict[str, Any]:
        """ONE REQUEST: analyze image AND select category for Claude"""
        # Encode image to base64
        image_b64 = base64.b64encode(image_data).decode('utf-8')

        # Language-specific instructions
        language_map = {
            'ru': 'Russian (русский)',
            'en': 'English',
            'pt': 'Portuguese (português)',
            'es': 'Spanish (español)',
            'fr': 'French (français)',
            'de': 'German (deutsch)',
            'it': 'Italian (italiano)',
            'zh': 'Chinese (中文)',
            'ja': 'Japanese (日本語)',
            'ko': 'Korean (한국어)'
        }
        language_name = language_map.get(language, 'English')

        # Build compact category list (numbered)
        category_list, index_to_id = build_category_list(categories)

        prompt = f"""Analyze this product image and provide title, description, price, AND category in JSON format.

IMPORTANT: Generate the title and description in {language_name}. All text fields MUST be in {language_name}.

Available categories ({len(categories)} total, format: number:name):
{category_list}

Respond with ONLY a valid JSON object:
{{
    "title": "Short descriptive title (3-50 words) in {language_name}",
    "description": "Detailed description (50-200 words) in {language_name}",
    "suggested_price_eur": estimated price in EUR as a number (or null),
    "category_index": number of the most appropriate category from the list above,
    "category_confidence": 0.0 to 1.0,
    "confidence": 0.0 to 1.0
}}

Description writing style:
- Write as if you are the SELLER describing YOUR item for sale
- NEVER use phrases like "on the image", "in the photo", "shown", "depicted"
- Describe the SPECIFIC item in the photo, not general facts
- Mention actual condition, visible defects, damages, wear if present
- Keep it practical and honest

Category selection:
- Choose the MOST SPECIFIC and ACCURATE category by its NUMBER
- Pay careful attention to actual image content"""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_b64
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }]
            )

            # Parse response
            response_text = message.content[0].text.strip()
            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            result = json.loads(response_text)

            # Convert category_index to category_id using mapping
            category_index = result.get('category_index')
            category_id = index_to_id.get(category_index) if category_index else None

            # Extract usage info
            usage_info = None
            if hasattr(message, 'usage'):
                input_tokens = getattr(message.usage, 'input_tokens', 0)
                output_tokens = getattr(message.usage, 'output_tokens', 0)
                # Haiku 4.5 pricing
                cost = (input_tokens * 1.0 / 1_000_000) + (output_tokens * 5.0 / 1_000_000)
                usage_info = {
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'estimated_cost_usd': cost
                }

            return {
                'title': result.get('title', ''),
                'description': result.get('description', ''),
                'suggested_price': {
                    'type': 'sale',
                    'amount': Decimal(str(result['suggested_price_eur'])) if result.get('suggested_price_eur') else None,
                    'currency': 'EUR'
                } if result.get('suggested_price_eur') else None,
                'category_id': category_id,
                'category_confidence': result.get('category_confidence', 0.8),
                'confidence': result.get('confidence', 0.8),
                'usage': usage_info
            }

        except Exception as e:
            logger.error(f"Claude one-request error: {e}")
            raise


class OpenAIVisionProvider(AIVisionProvider):
    """OpenAI GPT-5 Vision API provider"""

    def __init__(self, api_key: str, model: str = "gpt-5"):
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model

    def analyze_image(self, image_data: bytes, language: str = 'en') -> Dict[str, Any]:
        # Encode image to base64
        image_b64 = base64.b64encode(image_data).decode('utf-8')

        # Language-specific instructions
        language_map = {
            'ru': 'Russian (русский)',
            'en': 'English',
            'pt': 'Portuguese (português)',
            'es': 'Spanish (español)',
            'fr': 'French (français)',
            'de': 'German (deutsch)',
            'it': 'Italian (italiano)',
            'zh': 'Chinese (中文)',
            'ja': 'Japanese (日本語)',
            'ko': 'Korean (한국어)'
        }
        language_name = language_map.get(language, 'English')

        prompt = f"""Analyze this product image and provide title, description, and price estimate in JSON format.

IMPORTANT: Generate the title and description in {language_name}. The user's preferred language is {language_name}, so all text fields MUST be written in {language_name}.

Respond with ONLY a valid JSON object (no markdown, no explanations) with this structure:
{{
    "title": "Short descriptive title (3-50 words) in {language_name}",
    "description": "Detailed description (50-200 words) in {language_name}",
    "suggested_price_eur": estimated price in EUR as a number (or null if cannot estimate),
    "confidence": 0.0 to 1.0
}}

Rules:
- Title and description MUST be written in {language_name}
- Title should be concise and descriptive
- Price should be realistic market value in EUR
- Set confidence based on image clarity and your certainty

CRITICAL - Description writing style:
- Write as if you are the SELLER describing YOUR item for sale
- Use first person perspective ("selling", "offering") or neutral description
- NEVER use phrases like "on the image", "in the photo", "shown", "depicted", "presented"
- Describe the SPECIFIC item in the photo, not general facts about the product category
- Mention actual condition, visible features, defects, damages, wear if present
- Focus on what makes THIS specific item unique or notable
- Keep it practical and honest - don't oversell with marketing language about vitamins/health benefits unless directly relevant
- If item looks new/unused, mention it. If used/worn, describe the condition honestly

Example BAD description (DO NOT DO THIS):
"На изображении представлен апельсин. Апельсины богаты витамином С..."

Example GOOD description:
"Свежие апельсины, 5 штук. Куплены вчера на рынке, один немного помят с боку. Остальные в отличном состоянии."

Example GOOD description:
"Ноутбук Dell XPS 15. Использовался 2 года, царапины на крышке, батарея держит около 3 часов. Работает без проблем, все порты исправны."
"""

        try:
            # GPT-5 models require max_completion_tokens instead of max_tokens
            api_params = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_b64}"
                                }
                            }
                        ]
                    }
                ],
                "response_format": {"type": "json_object"}
            }

            # Use max_completion_tokens for GPT-5 models, max_tokens for older models
            # High limits - let AI decide how much it needs
            if self.model.startswith('gpt-5'):
                api_params['max_completion_tokens'] = 4096  # GPT-5 uses reasoning tokens
            else:
                api_params['max_tokens'] = 4096  # High limit

            response = self.client.chat.completions.create(**api_params)

            # Parse response
            response_text = response.choices[0].message.content
            if not response_text:
                logger.error(f"OpenAI {self.model} returned empty content. Full response: {response}")
                raise ValueError(f"OpenAI {self.model} returned empty response")

            response_text = response_text.strip()
            logger.info(f"OpenAI {self.model} vision response length: {len(response_text)} chars")
            result = json.loads(response_text)

            # Extract usage info
            usage_info = None
            if hasattr(response, 'usage'):
                input_tokens = getattr(response.usage, 'prompt_tokens', 0)
                output_tokens = getattr(response.usage, 'completion_tokens', 0)

                # Pricing based on model (verified 2025-11-01)
                if self.model == 'gpt-5':
                    cost = (input_tokens * 1.25 / 1_000_000) + (output_tokens * 10.0 / 1_000_000)
                elif self.model == 'gpt-5-mini':
                    cost = (input_tokens * 0.50 / 1_000_000) + (output_tokens * 5.0 / 1_000_000)
                elif self.model == 'gpt-5-nano':
                    cost = (input_tokens * 0.15 / 1_000_000) + (output_tokens * 1.50 / 1_000_000)
                else:
                    cost = (input_tokens * 1.25 / 1_000_000) + (output_tokens * 10.0 / 1_000_000)
                usage_info = {
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'estimated_cost_usd': cost
                }

            # Convert to standard format
            return {
                'title': result.get('title', ''),
                'description': result.get('description', ''),
                'suggested_price': {
                    'type': 'sale',
                    'amount': Decimal(str(result['suggested_price_eur'])) if result.get('suggested_price_eur') else None,
                    'currency': 'EUR'
                } if result.get('suggested_price_eur') else None,
                'confidence': result.get('confidence', 0.8),
                'usage': usage_info,
                'raw_prompt': prompt,
                'raw_response': response_text
            }

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

    def analyze_with_categories(self, image_data: bytes, categories: List[Dict[str, str]], language: str = 'en') -> Dict[str, Any]:
        """ONE REQUEST: analyze image AND select category for OpenAI"""
        # Encode image to base64
        image_b64 = base64.b64encode(image_data).decode('utf-8')

        # Language-specific instructions
        language_map = {
            'ru': 'Russian (русский)',
            'en': 'English',
            'pt': 'Portuguese (português)',
            'es': 'Spanish (español)',
            'fr': 'French (français)',
            'de': 'German (deutsch)',
            'it': 'Italian (italiano)',
            'zh': 'Chinese (中文)',
            'ja': 'Japanese (日本語)',
            'ko': 'Korean (한국어)'
        }
        language_name = language_map.get(language, 'English')

        # Build compact category list (numbered)
        category_list, index_to_id = build_category_list(categories)

        prompt = f"""Analyze this product image and provide title, description, price, AND category in JSON format.

IMPORTANT: Generate the title and description in {language_name}. All text fields MUST be in {language_name}.

Available categories ({len(categories)} total, format: number:name):
{category_list}

Respond with ONLY a valid JSON object:
{{
    "title": "Short descriptive title (3-50 words) in {language_name}",
    "description": "Detailed description (50-200 words) in {language_name}",
    "suggested_price_eur": estimated price in EUR as a number (or null),
    "category_index": number of the most appropriate category from the list above,
    "category_confidence": 0.0 to 1.0,
    "confidence": 0.0 to 1.0
}}

Description writing style:
- Write as if you are the SELLER describing YOUR item for sale
- NEVER use phrases like "on the image", "in the photo", "shown", "depicted"
- Describe the SPECIFIC item in the photo, not general facts
- Mention actual condition, visible defects, damages, wear if present
- Keep it practical and honest

Category selection:
- Choose the MOST SPECIFIC and ACCURATE category by its NUMBER
- Pay careful attention to actual image content"""

        try:
            # GPT-5 models require max_completion_tokens
            api_params = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_b64}"
                                }
                            }
                        ]
                    }
                ],
                "response_format": {"type": "json_object"}
            }

            if self.model.startswith('gpt-5'):
                api_params['max_completion_tokens'] = 4096
            else:
                api_params['max_tokens'] = 4096

            response = self.client.chat.completions.create(**api_params)

            # Parse response
            response_text = response.choices[0].message.content
            if not response_text:
                logger.error(f"OpenAI {self.model} one-request returned empty content")
                raise ValueError(f"OpenAI {self.model} returned empty response")

            response_text = response_text.strip()
            result = json.loads(response_text)

            # Convert category_index to category_id using mapping
            category_index = result.get('category_index')
            category_id = index_to_id.get(category_index) if category_index else None

            # Extract usage info
            usage_info = None
            if hasattr(response, 'usage'):
                input_tokens = getattr(response.usage, 'prompt_tokens', 0)
                output_tokens = getattr(response.usage, 'completion_tokens', 0)

                # Pricing based on model
                if self.model == 'gpt-5':
                    cost = (input_tokens * 1.25 / 1_000_000) + (output_tokens * 10.0 / 1_000_000)
                elif self.model == 'gpt-5-mini':
                    cost = (input_tokens * 0.50 / 1_000_000) + (output_tokens * 5.0 / 1_000_000)
                elif self.model == 'gpt-5-nano':
                    cost = (input_tokens * 0.15 / 1_000_000) + (output_tokens * 1.50 / 1_000_000)
                else:
                    cost = (input_tokens * 1.25 / 1_000_000) + (output_tokens * 10.0 / 1_000_000)

                usage_info = {
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'estimated_cost_usd': cost
                }

            return {
                'title': result.get('title', ''),
                'description': result.get('description', ''),
                'suggested_price': {
                    'type': 'sale',
                    'amount': Decimal(str(result['suggested_price_eur'])) if result.get('suggested_price_eur') else None,
                    'currency': 'EUR'
                } if result.get('suggested_price_eur') else None,
                'category_id': category_id,
                'category_confidence': result.get('category_confidence', 0.8),
                'confidence': result.get('confidence', 0.8),
                'usage': usage_info
            }

        except Exception as e:
            logger.error(f"OpenAI {self.model} one-request error: {e}")
            raise


class GeminiFlashVisionProvider(AIVisionProvider):
    """Google Gemini 2.5 Flash Vision API provider"""

    def __init__(self, api_key: str, model: str = 'gemini-3.1-flash-lite-preview'):
        self.client = genai.Client(api_key=api_key)
        self.model_name = model

    def analyze_image(self, image_data: bytes, language: str = 'en') -> Dict[str, Any]:
        # Language-specific instructions
        language_map = {
            'ru': 'Russian (русский)',
            'en': 'English',
            'pt': 'Portuguese (português)',
            'es': 'Spanish (español)',
            'fr': 'French (français)',
            'de': 'German (deutsch)',
            'it': 'Italian (italiano)',
            'zh': 'Chinese (中文)',
            'ja': 'Japanese (日本語)',
            'ko': 'Korean (한국어)'
        }
        language_name = language_map.get(language, 'English')

        prompt = f"""Analyze this product image and provide title, description, and price estimate in JSON format.

IMPORTANT: Generate the title and description in {language_name}. The user's preferred language is {language_name}, so all text fields MUST be written in {language_name}.

Respond with ONLY a valid JSON object (no markdown, no explanations) with this structure:
{{
    "title": "Short descriptive title (3-50 words) in {language_name}",
    "description": "Detailed description (50-200 words) in {language_name}",
    "suggested_price_eur": estimated price in EUR as a number (or null if cannot estimate),
    "confidence": 0.0 to 1.0
}}

Rules:
- Title and description MUST be written in {language_name}
- Title should be concise and descriptive
- Price should be realistic market value in EUR
- Set confidence based on image clarity and your certainty

CRITICAL - Description writing style:
- Write as if you are the SELLER describing YOUR item for sale
- Use first person perspective ("selling", "offering") or neutral description
- NEVER use phrases like "on the image", "in the photo", "shown", "depicted", "presented"
- Describe the SPECIFIC item in the photo, not general facts about the product category
- Mention actual condition, visible features, defects, damages, wear if present
- Focus on what makes THIS specific item unique or notable
- Keep it practical and honest - don't oversell with marketing language about vitamins/health benefits unless directly relevant
- If item looks new/unused, mention it. If used/worn, describe the condition honestly

Example BAD description (DO NOT DO THIS):
"На изображении представлен апельсин. Апельсины богаты витамином С..."

Example GOOD description:
"Свежие апельсины, 5 штук. Куплены вчера на рынке, один немного помят с боку. Остальные в отличном состоянии."

Example GOOD description:
"Ноутбук Dell XPS 15. Использовался 2 года, царапины на крышке, батарея держит около 3 часов. Работает без проблем, все порты исправны."
"""

        try:
            # Upload image
            import PIL.Image
            from io import BytesIO
            img = PIL.Image.open(BytesIO(image_data))

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt, img],
                config=genai_types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=4096,
                    response_mime_type='application/json'
                )
            )

            # Check safety filters and finish reason
            if response.candidates:
                candidate = response.candidates[0]
                finish_reason = candidate.finish_reason
                if finish_reason and finish_reason != genai_types.FinishReason.STOP:
                    logger.error(f"Gemini blocked response: finish_reason={finish_reason.name}")
                    raise ValueError(f"Gemini blocked response: {finish_reason.name}")

            # Parse response
            response_text = response.text if hasattr(response, 'text') else None
            if not response_text:
                logger.error(f"Gemini returned empty response. Full: {response}")
                raise ValueError("Gemini returned empty response")

            response_text = response_text.strip()
            if not response_text:
                logger.error(f"Gemini returned whitespace-only response")
                raise ValueError("Gemini returned empty response after strip")

            # Remove markdown code blocks if present (Gemini sometimes wraps JSON)
            if response_text.startswith("```"):
                lines = response_text.split('\n')
                # Remove first line (```json or ```)
                lines = lines[1:]
                # Remove last line (```)
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                response_text = '\n'.join(lines).strip()

            result = json.loads(response_text)

            # Extract usage info
            usage_info = None
            if hasattr(response, 'usage_metadata'):
                input_tokens = response.usage_metadata.prompt_token_count
                output_tokens = response.usage_metadata.candidates_token_count

                # Pricing based on model (verified 2025-11-01)
                if 'lite' in self.model_name.lower():
                    # Flash-Lite: $0.10/$0.40
                    cost = (input_tokens * 0.10 / 1_000_000) + (output_tokens * 0.40 / 1_000_000)
                else:
                    # Flash: $0.30/$2.50
                    cost = (input_tokens * 0.30 / 1_000_000) + (output_tokens * 2.50 / 1_000_000)
                usage_info = {
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'estimated_cost_usd': cost
                }

            # Convert to standard format
            return {
                'title': result.get('title', ''),
                'description': result.get('description', ''),
                'suggested_price': {
                    'type': 'sale',
                    'amount': Decimal(str(result['suggested_price_eur'])) if result.get('suggested_price_eur') else None,
                    'currency': 'EUR'
                } if result.get('suggested_price_eur') else None,
                'confidence': result.get('confidence', 0.8),
                'usage': usage_info,
                'raw_prompt': prompt,  # Save for debugging
                'raw_response': response_text  # Save for debugging
            }

        except json.JSONDecodeError as e:
            logger.error(f"Gemini JSON parse error: {e}. Response text: '{response_text if 'response_text' in locals() else 'N/A'}'")
            raise ValueError(f"Gemini returned invalid JSON: {e}")
        except Exception as e:
            logger.error(f"Gemini Flash Vision API error: {e}")
            raise

    def analyze_with_categories(self, image_data: bytes, categories: List[Dict[str, str]], language: str = 'en') -> Dict[str, Any]:
        """ONE REQUEST: analyze image AND select category"""
        # Language-specific instructions
        language_map = {
            'ru': 'Russian (русский)',
            'en': 'English',
            'pt': 'Portuguese (português)',
            'es': 'Spanish (español)',
            'fr': 'French (français)',
            'de': 'German (deutsch)',
            'it': 'Italian (italiano)',
            'zh': 'Chinese (中文)',
            'ja': 'Japanese (日本語)',
            'ko': 'Korean (한국어)'
        }
        language_name = language_map.get(language, 'English')

        # Build compact category list (numbered)
        category_list, index_to_id = build_category_list(categories)

        prompt = f"""Analyze this product image and provide title, description, price, AND category in JSON format.

IMPORTANT: Generate the title and description in {language_name}. All text fields MUST be in {language_name}.

Available categories ({len(categories)} total, format: number:name):
{category_list}

Respond with ONLY a valid JSON object:
{{
    "title": "Short descriptive title (3-50 words) in {language_name}",
    "description": "Detailed description (50-200 words) in {language_name}",
    "suggested_price_eur": estimated price in EUR as a number (or null),
    "category_index": number of the most appropriate category from the list above,
    "category_confidence": 0.0 to 1.0,
    "confidence": 0.0 to 1.0
}}

Description writing style:
- Write as if you are the SELLER describing YOUR item for sale
- NEVER use phrases like "on the image", "in the photo", "shown", "depicted"
- Describe the SPECIFIC item in the photo, not general facts
- Mention actual condition, visible defects, damages, wear if present
- Keep it practical and honest

Category selection:
- Choose the MOST SPECIFIC and ACCURATE category by its NUMBER
- Pay careful attention to actual image content"""

        try:
            import PIL.Image
            from io import BytesIO
            img = PIL.Image.open(BytesIO(image_data))

            response = self.model.generate_content(
                [prompt, img],
                generation_config={
                    'temperature': 0.7,
                    'max_output_tokens': 4096,  # High limit (one-request needs more)
                    'response_mime_type': 'application/json'
                }
            )

            response_text = response.text if hasattr(response, 'text') else None
            if not response_text:
                logger.error(f"Gemini returned empty response. Full: {response}")
                raise ValueError("Gemini returned empty response")

            response_text = response_text.strip()

            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                lines = response_text.split('\n')
                lines = lines[1:]  # Remove first line
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]  # Remove last line
                response_text = '\n'.join(lines).strip()

            result = json.loads(response_text)

            # Convert category_index to category_id using mapping
            category_index = result.get('category_index')
            category_id = index_to_id.get(category_index) if category_index else None

            # Extract usage info
            usage_info = None
            if hasattr(response, 'usage_metadata'):
                input_tokens = response.usage_metadata.prompt_token_count
                output_tokens = response.usage_metadata.candidates_token_count
                cost = (input_tokens * 0.075 / 1_000_000) + (output_tokens * 0.30 / 1_000_000)
                usage_info = {
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'estimated_cost_usd': cost
                }

            return {
                'title': result.get('title', ''),
                'description': result.get('description', ''),
                'suggested_price': {
                    'type': 'sale',
                    'amount': Decimal(str(result['suggested_price_eur'])) if result.get('suggested_price_eur') else None,
                    'currency': 'EUR'
                } if result.get('suggested_price_eur') else None,
                'category_id': category_id,
                'category_confidence': result.get('category_confidence', 0.8),
                'confidence': result.get('confidence', 0.8),
                'usage': usage_info
            }

        except Exception as e:
            logger.error(f"Gemini Flash one-request error: {e}")
            raise


class HaikuCategorizationProvider(AICategorizationProvider):
    """Claude Haiku 4.5 for fast categorization"""

    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)

    def categorize_from_text(self, title: str, description: str, categories: List[Dict[str, str]], language: str = 'en') -> Dict[str, Any]:
        # Build compact category list (numbered)
        category_list, index_to_id = build_category_list(categories)

        prompt = f"""Select the most appropriate category for this item based on its title and description.

Item title: {title}
Item description: {description}

Available categories ({len(categories)} total, format: number:name):
{category_list}

Respond with ONLY a valid JSON object (no markdown, no explanations):
{{
    "category_index": number of the most appropriate category from the list above,
    "confidence": 0.0 to 1.0
}}

Rules:
- Choose the MOST SPECIFIC and ACCURATE category by its NUMBER
- Base your decision ONLY on the title and description provided
- The category NUMBER must be from the list above"""

        try:
            message = self.client.messages.create(
                model="claude-haiku-4-5",  # Updated to Haiku 4.5 (Oct 2025)
                max_tokens=1024,  # Higher limit for categorization
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            # Parse response
            response_text = message.content[0].text.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            result = json.loads(response_text)

            # Extract usage info
            usage_info = None
            if hasattr(message, 'usage'):
                input_tokens = getattr(message.usage, 'input_tokens', 0)
                output_tokens = getattr(message.usage, 'output_tokens', 0)
                # Haiku 4.5 pricing (verified 2025-11-01): $1/1M input, $5/1M output
                cost = (input_tokens * 1.0 / 1_000_000) + (output_tokens * 5.0 / 1_000_000)
                usage_info = {
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'estimated_cost_usd': cost
                }

            # Convert category_index to category_id using mapping
            category_index = result.get('category_index')
            category_id = index_to_id.get(category_index) if category_index else None

            return {
                'category_id': category_id,
                'category_confidence': result.get('confidence', 0.8),
                'usage': usage_info,
                'raw_prompt': prompt,  # Save for debugging
                'raw_response': response_text  # Save for debugging
            }

        except Exception as e:
            logger.error(f"Haiku categorization error: {e}")
            raise


class GPT5NanoCategorizationProvider(AICategorizationProvider):
    """GPT-5 nano for very cheap categorization"""

    def __init__(self, api_key: str):
        self.client = openai.OpenAI(api_key=api_key)

    def categorize_from_text(self, title: str, description: str, categories: List[Dict[str, str]], language: str = 'en') -> Dict[str, Any]:
        # Build compact category list (numbered)
        category_list, index_to_id = build_category_list(categories)

        prompt = f"""Select the most appropriate category for this item based on its title and description.

Item title: {title}
Item description: {description}

Available categories ({len(categories)} total, format: number:name):
{category_list}

Respond with ONLY a valid JSON object (no markdown, no explanations):
{{
    "category_index": number of the most appropriate category from the list above,
    "confidence": 0.0 to 1.0
}}

Rules:
- Choose the MOST SPECIFIC and ACCURATE category by its NUMBER
- Base your decision ONLY on the title and description provided
- The category NUMBER must be from the list above"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-5-nano",
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=2048,  # High limit for reasoning tokens
                response_format={"type": "json_object"}
            )

            # Parse response
            response_text = response.choices[0].message.content
            if not response_text:
                logger.error(f"GPT-5 nano returned empty content. Full response: {response}")
                raise ValueError("GPT-5 nano returned empty response")

            response_text = response_text.strip()
            logger.info(f"GPT-5 nano raw response: {response_text[:200]}")
            result = json.loads(response_text)

            # Extract usage info
            usage_info = None
            if hasattr(response, 'usage'):
                input_tokens = getattr(response.usage, 'prompt_tokens', 0)
                output_tokens = getattr(response.usage, 'completion_tokens', 0)
                # GPT-5 nano pricing (verified 2025-11-01): $0.15/1M input, $1.50/1M output
                cost = (input_tokens * 0.15 / 1_000_000) + (output_tokens * 1.50 / 1_000_000)
                usage_info = {
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'estimated_cost_usd': cost
                }

            # Convert category_index to category_id using mapping
            category_index = result.get('category_index')
            category_id = index_to_id.get(category_index) if category_index else None

            return {
                'category_id': category_id,
                'category_confidence': result.get('confidence', 0.8),
                'usage': usage_info,
                'raw_prompt': prompt,
                'raw_response': response_text
            }

        except Exception as e:
            logger.error(f"GPT-5 nano categorization error: {e}")
            raise


class GPT5MiniCategorizationProvider(AICategorizationProvider):
    """GPT-5 mini for mid-tier categorization"""

    def __init__(self, api_key: str):
        self.client = openai.OpenAI(api_key=api_key)

    def categorize_from_text(self, title: str, description: str, categories: List[Dict[str, str]], language: str = 'en') -> Dict[str, Any]:
        # Build compact category list (numbered)
        category_list, index_to_id = build_category_list(categories)

        prompt = f"""Select the most appropriate category for this item based on its title and description.

Item title: {title}
Item description: {description}

Available categories ({len(categories)} total, format: number:name):
{category_list}

Respond with ONLY a valid JSON object (no markdown, no explanations):
{{
    "category_index": number of the most appropriate category from the list above,
    "confidence": 0.0 to 1.0
}}

Rules:
- Choose the MOST SPECIFIC and ACCURATE category by its NUMBER
- Base your decision ONLY on the title and description provided
- The category NUMBER must be from the list above"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=2048,  # High limit
                response_format={"type": "json_object"}
            )

            # Parse response
            response_text = response.choices[0].message.content
            if not response_text:
                logger.error(f"GPT-5 mini returned empty content")
                raise ValueError("GPT-5 mini returned empty response")

            response_text = response_text.strip()
            result = json.loads(response_text)

            # Extract usage info
            usage_info = None
            if hasattr(response, 'usage'):
                input_tokens = getattr(response.usage, 'prompt_tokens', 0)
                output_tokens = getattr(response.usage, 'completion_tokens', 0)
                # GPT-5 mini pricing (verified 2025-11-01): $0.50/1M input, $5/1M output
                cost = (input_tokens * 0.50 / 1_000_000) + (output_tokens * 5.0 / 1_000_000)
                usage_info = {
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'estimated_cost_usd': cost
                }

            # Convert category_index to category_id using mapping
            category_index = result.get('category_index')
            category_id = index_to_id.get(category_index) if category_index else None

            return {
                'category_id': category_id,
                'category_confidence': result.get('confidence', 0.8),
                'usage': usage_info,
                'raw_prompt': prompt,
                'raw_response': response_text
            }

        except Exception as e:
            logger.error(f"GPT-5 mini categorization error: {e}")
            raise


class GeminiFlashCategorizationProvider(AICategorizationProvider):
    """Google Gemini Flash categorization (supports Flash and Flash-Lite)"""

    def __init__(self, api_key: str, model: str = 'gemini-3.1-flash-lite-preview'):
        self.client = genai.Client(api_key=api_key)
        self.model_name = model

    def categorize_from_text(self, title: str, description: str, categories: List[Dict[str, str]], language: str = 'en') -> Dict[str, Any]:
        # Build compact category list (numbered)
        category_list, index_to_id = build_category_list(categories)

        prompt = f"""Select the most appropriate category for this item based on its title and description.

Item title: {title}
Item description: {description}

Available categories ({len(categories)} total, format: number:name):
{category_list}

Respond with ONLY a valid JSON object (no markdown, no explanations):
{{
    "category_index": number of the most appropriate category from the list above,
    "confidence": 0.0 to 1.0
}}

Rules:
- Choose the MOST SPECIFIC and ACCURATE category by its NUMBER
- Base your decision ONLY on the title and description provided
- The category NUMBER must be from the list above"""

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=1024,
                    response_mime_type='application/json'
                )
            )

            # Parse response
            response_text = response.text if hasattr(response, 'text') else None
            if not response_text:
                logger.error(f"Gemini returned empty response. Full: {response}")
                raise ValueError("Gemini returned empty response")

            response_text = response_text.strip()

            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                lines = response_text.split('\n')
                lines = lines[1:]  # Remove first line (```json or ```)
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]  # Remove last line (```)
                response_text = '\n'.join(lines).strip()

            result = json.loads(response_text)

            # Extract usage info
            usage_info = None
            if hasattr(response, 'usage_metadata'):
                input_tokens = response.usage_metadata.prompt_token_count
                output_tokens = response.usage_metadata.candidates_token_count

                # Pricing based on model (verified 2025-11-01)
                if 'lite' in self.model_name.lower():
                    # Flash-Lite: $0.10/$0.40
                    cost = (input_tokens * 0.10 / 1_000_000) + (output_tokens * 0.40 / 1_000_000)
                else:
                    # Flash: $0.30/$2.50
                    cost = (input_tokens * 0.30 / 1_000_000) + (output_tokens * 2.50 / 1_000_000)
                usage_info = {
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'estimated_cost_usd': cost
                }

            # Convert category_index to category_id using mapping
            category_index = result.get('category_index')
            category_id = index_to_id.get(category_index) if category_index else None

            return {
                'category_id': category_id,
                'category_confidence': result.get('confidence', 0.8),
                'usage': usage_info,
                'raw_prompt': prompt,  # Save for debugging
                'raw_response': response_text  # Save for debugging
            }

        except Exception as e:
            logger.error(f"Gemini Flash categorization error: {e}")
            raise


class AIVisionService:
    """Main service for AI vision analysis"""

    @staticmethod
    def get_provider() -> Optional[AIVisionProvider]:
        """Get configured AI vision provider from settings"""
        try:
            from parahub.models import AISettings
            ai_settings = AISettings.objects.first()

            if ai_settings and ai_settings.enabled:
                provider = ai_settings.provider

                if provider == 'haiku' and ai_settings.claude_api_key:
                    return ClaudeVisionProvider(ai_settings.claude_api_key, model="claude-haiku-4-5")

                elif provider == 'gpt-5' and ai_settings.openai_api_key:
                    return OpenAIVisionProvider(ai_settings.openai_api_key, model="gpt-5")

                elif provider == 'gpt-5-mini' and ai_settings.openai_api_key:
                    return OpenAIVisionProvider(ai_settings.openai_api_key, model="gpt-5-mini")

                elif provider == 'gpt-5-nano' and ai_settings.openai_api_key:
                    return OpenAIVisionProvider(ai_settings.openai_api_key, model="gpt-5-nano")

                elif provider == 'gemini-flash' and ai_settings.google_api_key:
                    return GeminiFlashVisionProvider(ai_settings.google_api_key, model='gemini-3.1-flash-lite-preview')

                elif provider == 'gemini-flash-lite' and ai_settings.google_api_key:
                    return GeminiFlashVisionProvider(ai_settings.google_api_key, model='gemini-3.1-flash-lite-preview')

        except Exception as e:
            logger.warning(f"Could not load AI vision provider: {e}")

        return None

    @staticmethod
    def get_categorization_provider() -> Optional[AICategorizationProvider]:
        """Get configured categorization provider from settings"""
        try:
            from parahub.models import AISettings
            ai_settings = AISettings.objects.first()

            if ai_settings and ai_settings.enabled:
                cat_provider = ai_settings.categorization_provider

                if cat_provider == 'haiku':
                    # Use Claude Haiku
                    if ai_settings.claude_api_key:
                        return HaikuCategorizationProvider(ai_settings.claude_api_key)

                elif cat_provider == 'gpt-5-nano':
                    # Use GPT-5 nano
                    if ai_settings.openai_api_key:
                        return GPT5NanoCategorizationProvider(ai_settings.openai_api_key)

                elif cat_provider == 'gpt-5-mini':
                    # Use GPT-5 mini
                    if ai_settings.openai_api_key:
                        return GPT5MiniCategorizationProvider(ai_settings.openai_api_key)

                elif cat_provider == 'gemini-flash':
                    # Use Gemini Flash
                    if ai_settings.google_api_key:
                        return GeminiFlashCategorizationProvider(ai_settings.google_api_key, model='gemini-3.1-flash-lite-preview')

                elif cat_provider == 'gemini-flash-lite':
                    # Use Gemini Flash-Lite
                    if ai_settings.google_api_key:
                        return GeminiFlashCategorizationProvider(ai_settings.google_api_key, model='gemini-3.1-flash-lite-preview')

                elif cat_provider == 'same':
                    # Use same as vision provider (or cheaper variant)
                    if ai_settings.provider == 'haiku' and ai_settings.claude_api_key:
                        return HaikuCategorizationProvider(ai_settings.claude_api_key)

                    elif ai_settings.provider in ['gpt-5', 'gpt-5-mini', 'gpt-5-nano'] and ai_settings.openai_api_key:
                        return GPT5NanoCategorizationProvider(ai_settings.openai_api_key)

                    elif ai_settings.provider in ['gemini-flash', 'gemini-flash-lite'] and ai_settings.google_api_key:
                        # Use same Gemini model for categorization
                        if ai_settings.provider == 'gemini-flash':
                            return GeminiFlashCategorizationProvider(ai_settings.google_api_key, model='gemini-3.1-flash-lite-preview')
                        else:
                            return GeminiFlashCategorizationProvider(ai_settings.google_api_key, model='gemini-3.1-flash-lite-preview')

        except Exception as e:
            logger.warning(f"Could not load categorization provider: {e}")

        # Fallback: use Haiku if Claude key available
        try:
            from parahub.models import AISettings
            ai_settings = AISettings.objects.first()
            if ai_settings and ai_settings.claude_api_key:
                return HaikuCategorizationProvider(ai_settings.claude_api_key)
        except Exception:
            pass

        return None

    @staticmethod
    def _smart_round_price(amount: 'Decimal') -> 'Decimal':
        """
        Smart rounding for prices based on magnitude.

        Examples:
        - 12.5 → 12.50 (< 100: keep 2 decimals)
        - 450.75 → 450 (100-1000: round to integer)
        - 4580 → 4600 (1000-10000: round to nearest 50/100)
        - 421571.41 → 420000 (> 10000: round to thousands)

        Args:
            amount: Price as Decimal

        Returns:
            Smartly rounded Decimal
        """
        from decimal import Decimal
        import math

        if amount < 100:
            # Keep 2 decimals for small amounts
            return amount.quantize(Decimal('0.01'))
        elif amount < 1000:
            # Round to integer
            return Decimal(int(round(amount)))
        elif amount < 10000:
            # Round to nearest 50 or 100
            rounded = int(math.ceil(amount / 50) * 50)
            return Decimal(rounded)
        else:
            # Round to nearest thousand
            rounded = int(math.ceil(amount / 1000) * 1000)
            return Decimal(rounded)

    @staticmethod
    def _convert_price_to_currency(suggested_price: Dict[str, Any], target_currency: str) -> Dict[str, Any]:
        """
        Convert suggested_price from EUR to target currency with smart rounding.

        Args:
            suggested_price: Dict with type, amount (Decimal), currency ('EUR')
            target_currency: Target currency code (e.g., 'RUB', 'USD')

        Returns:
            Dict with converted and smartly rounded amount and target currency
        """
        if not suggested_price or not suggested_price.get('amount'):
            return suggested_price

        if suggested_price.get('currency') == target_currency:
            return suggested_price

        try:
            from currency.models import ExchangeRate
            from decimal import Decimal

            amount_eur = suggested_price['amount']
            amount_target = ExchangeRate.convert(
                amount=amount_eur,
                from_currency='EUR',
                to_currency=target_currency
            )

            # Apply smart rounding
            amount_rounded = AIVisionService._smart_round_price(amount_target)

            return {
                'type': suggested_price['type'],
                'amount': amount_rounded,
                'currency': target_currency
            }
        except Exception as e:
            logger.warning(f"Failed to convert price from EUR to {target_currency}: {e}, using EUR")
            return suggested_price

    @staticmethod
    def analyze_item_image(image_data: bytes, language: str = 'en', user_currency: str = 'EUR', user_id: str = None) -> Dict[str, Any]:
        """
        Analyze item image using one-step or two-step process:
        - ONE STEP: if same provider for vision & categorization (faster, cheaper)
        - TWO STEPS: different providers (vision → categorization) with WS progress updates

        Args:
            image_data: Raw image bytes
            language: User's preferred language code (en, ru, pt, es, fr, etc.)
            user_currency: User's preferred currency code (EUR, USD, RUB, etc.)
            user_id: User ID for WebSocket notifications (optional)

        Returns:
            Dict with:
            - category_id, category_confidence
            - title, description, suggested_price (converted to user_currency), confidence
            - vision_usage, categorization_usage
            - vision_processing_time_ms, categorization_processing_time_ms
            - vision_raw_prompt, vision_raw_response (for logging)
            - categorization_raw_prompt, categorization_raw_response (for logging)

        Raises:
            ValueError if no AI provider is configured
        """
        from parahub.models import AISettings

        vision_provider = AIVisionService.get_provider()
        if not vision_provider:
            raise ValueError("No AI vision provider configured.")

        categorization_provider = AIVisionService.get_categorization_provider()
        if not categorization_provider:
            raise ValueError("No categorization provider configured.")

        # Get ALL categories
        categories = AIVisionService._get_categories()

        # Check if ONE-REQUEST optimization is enabled
        ai_settings = AISettings.objects.first()

        # Determine if using same provider (handle 'same' categorization option)
        cat_is_same = (
            ai_settings.categorization_provider == 'same'
            or ai_settings.categorization_provider == ai_settings.provider
        )

        # Check if provider supports one-request
        supports_one_request = ai_settings.provider in [
            'haiku',  # Claude Haiku 4.5
            'gemini-flash', 'gemini-flash-lite',  # Gemini models
            'gpt-5', 'gpt-5-mini', 'gpt-5-nano'  # OpenAI models
        ]

        use_one_request = (
            ai_settings
            and ai_settings.use_single_request  # User enabled via checkbox
            and cat_is_same  # Both use same provider
            and supports_one_request  # Provider has analyze_with_categories() method
        )

        if use_one_request:
            # ONE REQUEST: Vision + Categorization together
            logger.info(f"Using ONE-REQUEST optimization (provider: {ai_settings.provider})")
            vision_start = time.time()

            result = vision_provider.analyze_with_categories(image_data, categories, language)

            if result:  # analyze_with_categories succeeded
                vision_time_ms = int((time.time() - vision_start) * 1000)

                # Convert price to user's currency
                suggested_price = AIVisionService._convert_price_to_currency(
                    result.get('suggested_price'),
                    user_currency
                )

                # Send WebSocket progress update for ONE-REQUEST mode too
                if user_id:
                    try:
                        from parahub.services.ws_publish import ws_publish

                        suggested_price_ws = None
                        if suggested_price and suggested_price.get('amount'):
                            suggested_price_ws = {
                                'type': suggested_price['type'],
                                'amount': float(suggested_price['amount']),
                                'currency': suggested_price['currency']
                            }

                        ws_publish(f"user:{user_id}", {
                            "type": "ai.analysis_progress",
                            "step": "vision",
                            "title": result.get('title', ''),
                            "description": result.get('description', ''),
                            "suggested_price": suggested_price_ws,
                            "confidence": result.get('confidence', 0.8),
                            "next_step": "Done",
                        })
                        logger.info(f"Sent WS progress update to user {user_id}: one-request completed")
                    except Exception as e:
                        logger.warning(f"Failed to send WS progress update (one-request): {e}")

                return {
                    'category_id': result.get('category_id'),
                    'category_confidence': result.get('category_confidence', 0.8),
                    'title': result.get('title', ''),
                    'description': result.get('description', ''),
                    'suggested_price': suggested_price,
                    'confidence': result.get('confidence', 0.8),
                    'vision_usage': result.get('usage'),
                    'categorization_usage': None,  # No separate categorization request
                    'vision_processing_time_ms': vision_time_ms,
                    'categorization_processing_time_ms': 0
                }

        # TWO REQUESTS: Vision then Categorization (fallback or different providers)
        logger.info("Using TWO-REQUEST process (vision then categorization)")

        # Step 1: Vision analysis
        vision_start = time.time()
        vision_result = vision_provider.analyze_image(image_data, language)
        vision_time_ms = int((time.time() - vision_start) * 1000)

        # Convert price to user's currency
        vision_result['suggested_price'] = AIVisionService._convert_price_to_currency(
            vision_result.get('suggested_price'),
            user_currency
        )

        # Send WebSocket progress update (vision step completed)
        if user_id:
            try:
                from parahub.services.ws_publish import ws_publish

                suggested_price_ws = None
                if vision_result.get('suggested_price') and vision_result['suggested_price'].get('amount'):
                    suggested_price_ws = {
                        'type': vision_result['suggested_price']['type'],
                        'amount': float(vision_result['suggested_price']['amount']),
                        'currency': vision_result['suggested_price']['currency']
                    }

                ws_publish(f"user:{user_id}", {
                    "type": "ai.analysis_progress",
                    "step": "vision",
                    "title": vision_result.get('title', ''),
                    "description": vision_result.get('description', ''),
                    "suggested_price": suggested_price_ws,
                    "confidence": vision_result.get('confidence', 0.8),
                    "next_step": "Selecting category...",
                })
                logger.info(f"Sent WS progress update to user {user_id}: vision step completed")
            except Exception as e:
                logger.warning(f"Failed to send WS progress update: {e}")

        # Step 2: Categorization
        categorization_start = time.time()
        categorization_result = categorization_provider.categorize_from_text(
            title=vision_result.get('title', ''),
            description=vision_result.get('description', ''),
            categories=categories,
            language=language
        )
        categorization_time_ms = int((time.time() - categorization_start) * 1000)

        # Merge results
        return {
            'category_id': categorization_result.get('category_id'),
            'category_confidence': categorization_result.get('category_confidence', 0.8),
            'title': vision_result.get('title', ''),
            'description': vision_result.get('description', ''),
            'suggested_price': vision_result.get('suggested_price'),
            'confidence': vision_result.get('confidence', 0.8),
            'vision_usage': vision_result.get('usage'),
            'categorization_usage': categorization_result.get('usage'),
            'vision_processing_time_ms': vision_time_ms,
            'categorization_processing_time_ms': categorization_time_ms,
            # Raw data for debugging/transparency
            'vision_raw_prompt': vision_result.get('raw_prompt', ''),
            'vision_raw_response': vision_result.get('raw_response', ''),
            'categorization_raw_prompt': categorization_result.get('raw_prompt', ''),
            'categorization_raw_response': categorization_result.get('raw_response', '')
        }

    @staticmethod
    def _get_categories() -> List[Dict[str, str]]:
        """Get ALL LEAF categories (no limit), cached for 1 hour"""
        cache_key = 'ai_categorization_all_leaf_categories'
        categories = cache.get(cache_key)

        if not categories:
            from taxonomy.models import Category
            from django.db.models import Count

            # Get ALL leaf categories (categories with no children)
            categories = list(
                Category.objects.filter(is_active=True)
                .annotate(children_count=Count('children'))
                .filter(children_count=0)  # Only leafs
                .values('id', 'name', 'slug')
                .order_by('name')  # Alphabetical for consistency
            )
            cache.set(cache_key, categories, 3600)  # 1 hour

        return categories
