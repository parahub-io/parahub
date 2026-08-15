"""
Avatar stylizer — redraws a profile photo in the brand editorial-watercolor
style, preserving the person's identity (reference-image conditioning).

This module is canonical for the style: the prompt is assembled here and
nowhere else, and /me/avatar/stylize/prompt/ serves this same text to members
who want to run it on their own tool.

Cost note: $0.046/image; callers must gate with the 'avatar_stylize' quota
(QuotaService) before invoking stylize().
"""

import logging
from io import BytesIO

from PIL import Image

logger = logging.getLogger(__name__)

# Nano Banana 2 at native avatar size. Chosen over Nano Banana Pro on a
# four-portrait comparison: identity and style hold at a third of Pro's price
# ($0.046 vs $0.141) and a third of its latency (5.8s vs 19s). Repointing this
# is a spend decision — measure the candidate on real portraits first, the
# cheap tiers differ in how well they keep a face, not in whether they render.
MODEL = "gemini-3.1-flash-image"

# NOT the "1K/2K/4K" set the SDK docstring lists: this model also takes "512",
# which returns a native 512x512 for 747 image tokens instead of 1120. Avatars
# are stored at 512 (OUTPUT_SIZE), so a 1K generation would buy pixels the
# center-crop then throws away. The API rejects "0.5K", the spelling Google's
# own price list uses for this tier.
IMAGE_SIZE = "512"

IDENTITY = (
    "Redraw the person from the reference photo as a stylized avatar portrait. "
    "PRESERVE THE PERSON'S IDENTITY: same face shape and facial features, same "
    "hairstyle and hair color, same skin tone, same age, same glasses and "
    "accessories, same expression, same clothing style. The person must remain "
    "clearly recognizable to someone who knows them."
)

STYLE = (
    "STYLE: Warm contemporary watercolor editorial portrait — hand-painted "
    "with soft blooms, gentle edges and subtle paper grain, a modern fresh "
    "palette, clearly today's world, realistic human proportions. Weave in "
    "warm golden yellow (#FFE216) and deep indigo accents where natural "
    "(clothing, background wash). Background: clean pale warm paper with a "
    "single loose golden watercolor stroke behind the head and shoulders."
)

# Bigger-head rule: smaller compositions turned to mush at 24 px avatar chips;
# the recompose instruction keeps source framing quirks (selfie arms, tilted
# cameras) out of the avatar.
AVATAR_COMP = (
    "RECOMPOSE regardless of the source framing: a tight head-and-shoulders "
    "bust, front-facing. The head is LARGE — it fills about 70% of the frame "
    "height, chin in the lower half, eyes about 40% from the top. Shoulders "
    "just enter the bottom edge; arms, hands and anything below the chest are "
    "OUT of frame. Square 1:1 composition. The image will be shown cropped to "
    "a SMALL CIRCLE: face centered, background simple and calm, nothing "
    "important near corners or edges. Bold readable shapes that survive a "
    "32-pixel thumbnail."
)

NEG = (
    "No text, no words, no letters, no logos, no watermark, no frame, no "
    "panels, single person only. Do not change the person's age, gender, "
    "ethnicity, build or expression. Normalize the lighting: even, warm, "
    "flattering light regardless of the reference photo's lighting."
)

PROMPT = f"{IDENTITY}\n\n{STYLE}\n\n{AVATAR_COMP}\n\n{NEG}"

# Avatars are stored at 400x400 (see profiles/photos.upload_avatar); 512 keeps
# a little headroom for the preview modal without shipping the 1024 master.
OUTPUT_SIZE = 512


class StylizeError(Exception):
    """Generation failed (safety filter, API error, empty response)."""


def stylize(image_bytes: bytes, profile=None, source: str = '') -> bytes:
    """Reference photo bytes -> square editorial-watercolor JPEG bytes.

    Raises StylizeError when the model returns no image (safety filter or
    API failure) — callers map it to a 503.

    `profile`/`source` are only for the spend ledger; generation ignores them.
    """
    import time

    from google import genai
    from google.genai import types

    from parahub.models import AISettings, AIUsageLog
    from parahub.services import ai_usage

    settings = AISettings.objects.first()
    if not settings or not settings.google_api_key:
        raise StylizeError("AI service not configured")

    client = genai.Client(api_key=settings.google_api_key)
    ref = Image.open(BytesIO(image_bytes))

    started = time.monotonic()
    response = client.models.generate_content(
        model=MODEL,
        contents=[ref, PROMPT],
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
            image_config=types.ImageConfig(image_size=IMAGE_SIZE),
        ),
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)

    data = None
    for part in response.parts:
        if part.inline_data:
            data = part.inline_data.data
            break

    # Logged before the empty-response check: a safety rejection still billed the
    # prompt, and an unexplained run of them is only visible if it is recorded.
    ai_usage.record_gemini(
        AIUsageLog.KIND_AVATAR_STYLIZE, MODEL, response,
        profile=profile, duration_ms=elapsed_ms, success=bool(data),
        error='' if data else 'No image returned',
        meta={'source': source} if source else None,
    )

    if not data:
        # Safety filter rejections come back as empty parts, not exceptions
        logger.warning("Avatar stylize returned no image (safety filter?)")
        raise StylizeError("No image returned")

    img = Image.open(BytesIO(data)).convert("RGB")
    w, h = img.size
    s = min(w, h)
    img = img.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2))
    img = img.resize((OUTPUT_SIZE, OUTPUT_SIZE), Image.LANCZOS)

    out = BytesIO()
    img.save(out, format="JPEG", quality=90, optimize=True)
    return out.getvalue()
