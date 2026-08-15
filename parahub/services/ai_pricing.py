"""Model prices in one place, so every AI path can cost its own calls.

Values are the published standard rates — no caching, batch, or priority
discounts. Token models carry an input and an output rate per 1M tokens; image
models carry a third rate, because an image comes back as output tokens billed
at their own (much higher) rate than the text in the same response. Providers
that do not bill by token at all (speech) are priced per unit, see `UNIT_PRICING`.

Why this is centralised: the prices used to live inline at each call site, keyed
off substring checks like `'lite' in model_name`. That silently mispriced every
call the moment a model was renamed or a tier was added — a spend counter that
is quietly wrong is worse than none. One table, one lookup, one place to edit
when a price changes.

Adding a model: put its id here in the same change that starts using it,
otherwise `cost_usd()` returns 0 and the spend disappears from the logs.
`cost_usd` logs a warning in that case rather than failing silently.

Sources: ai.google.dev/gemini-api/docs/pricing,
developers.openai.com/api/docs/pricing, the Anthropic pricing table, and
elevenlabs.io/pricing/api.
"""
import logging
from decimal import Decimal
from typing import Any, NamedTuple, Optional

logger = logging.getLogger(__name__)

_MILLION = Decimal('1000000')


class Prices(NamedTuple):
    """USD per 1M tokens. `image_output` is None for models that emit no image."""
    input: Decimal
    output: Decimal
    image_output: Optional[Decimal] = None


MODEL_PRICING = {
    # Google Gemini — text
    'gemini-3.6-flash': Prices(Decimal('1.50'), Decimal('7.50')),
    'gemini-3.5-flash': Prices(Decimal('1.50'), Decimal('9.00')),
    'gemini-3.5-flash-lite': Prices(Decimal('0.30'), Decimal('2.50')),
    'gemini-3.1-flash-lite': Prices(Decimal('0.25'), Decimal('1.50')),
    'gemini-3.1-flash-lite-preview': Prices(Decimal('0.25'), Decimal('1.50')),
    # Google Gemini — image generation. The output rate is for the text and
    # thinking tokens in the same response; the image bills separately, and its
    # token count is set by the requested resolution, not by the picture:
    #   Pro       1120 @ 1K/2K ($0.134),                        2000 @ 4K ($0.24)
    #   Flash     747 @ 0.5K ($0.045), 1120 @ 1K ($0.067), 1680 @ 2K, 2520 @ 4K
    #   Flash-Lite            1120 @ 1K ($0.0336)
    'gemini-3-pro-image': Prices(Decimal('2.00'), Decimal('12.00'), Decimal('120.00')),
    'gemini-3.1-flash-image': Prices(Decimal('0.50'), Decimal('3.00'), Decimal('60.00')),
    'gemini-3.1-flash-lite-image': Prices(Decimal('0.25'), Decimal('1.50'), Decimal('30.00')),
    # Retired preview alias of gemini-3-pro-image — kept so a caller that still
    # carries the old id is priced rather than logged at 0.
    'gemini-3-pro-image-preview': Prices(Decimal('2.00'), Decimal('12.00'), Decimal('120.00')),
    # OpenAI
    'gpt-5': Prices(Decimal('1.25'), Decimal('10.00')),
    'gpt-5-mini': Prices(Decimal('0.25'), Decimal('2.00')),
    'gpt-5-nano': Prices(Decimal('0.05'), Decimal('0.40')),
    # Anthropic
    'claude-haiku-4-5': Prices(Decimal('1.00'), Decimal('5.00')),
}

# Back-compat alias: this table was Gemini-only when it was introduced.
GEMINI_PRICING = MODEL_PRICING

# Providers billed per unit of media rather than per token.
# `scribe_v1` is priced at the published Scribe rate — ElevenLabs quotes one
# transcription price, not a per-version one.
UNIT_PRICING = {
    # model id -> (USD per unit, unit name)
    'eleven_multilingual_v2': (Decimal('0.10') / Decimal('1000'), 'characters'),
    # Flash bills at half the credit rate of Multilingual v2 — same characters,
    # half the price (elevenlabs.io/pricing/api).
    'eleven_flash_v2_5': (Decimal('0.05') / Decimal('1000'), 'characters'),
    'scribe_v1': (Decimal('0.22') / Decimal('3600'), 'audio_seconds'),
}


# `AISettings.provider` / `.categorization_provider` store a TIER ALIAS, not a
# model id, so the admin dropdown survives model releases. This is the single
# place that resolves an alias to the id actually billed — keep the two tiers
# distinct here, or picking "Gemini Flash" in the admin silently gets you
# Flash-Lite and the setting lies about what it does. It lives beside the prices
# so the admin can label each tier with what it really costs.
GEMINI_MODEL_BY_ALIAS = {
    'gemini-flash': 'gemini-3.6-flash',
    'gemini-flash-lite': 'gemini-3.5-flash-lite',
}
GEMINI_DEFAULT_MODEL = 'gemini-3.5-flash-lite'


def gemini_model_for(provider_alias: str) -> str:
    """Model id for a settings alias. Unknown alias -> the cheap tier: an
    unrecognised setting must not silently escalate spend."""
    return GEMINI_MODEL_BY_ALIAS.get(provider_alias, GEMINI_DEFAULT_MODEL)


# Every `AISettings` provider alias, not just the Gemini ones. The OpenAI tiers
# are their own model ids; the others indirect.
ALIAS_TO_MODEL = {
    'haiku': 'claude-haiku-4-5',
    'gpt-5-nano': 'gpt-5-nano',
    'gpt-5-mini': 'gpt-5-mini',
    **GEMINI_MODEL_BY_ALIAS,
}


def model_for_alias(alias: str) -> Optional[str]:
    """Model id a settings alias bills as, or None for a non-model alias
    ('same' — categorization following the vision provider)."""
    return ALIAS_TO_MODEL.get(alias)


def tier_label(name: str, alias: str) -> str:
    """'<name> — <model id> ($in/$out per 1M)' for an admin dropdown.

    Built from the price table rather than typed into the choices, because a
    hand-written label goes stale the first time a tier is repointed and then
    quietly misinforms whoever is choosing a provider — which is how the
    dropdown came to advertise Gemini 2.5 prices for a 3.x model.
    """
    model = model_for_alias(alias)
    if not model:
        return name
    priced = rates(model)
    if not priced:
        return f'{name} — {model} (unpriced)'
    return f'{name} — {model} (${priced.input:g}/${priced.output:g} per 1M)'


class GeminiUsage(NamedTuple):
    """One Gemini call's billable quantities, already split by rate."""
    input_tokens: int
    output_tokens: int   # text + thinking — billed at the text output rate
    image_tokens: int    # image-modality output — billed at the image rate
    cost: Decimal


def rates(model: str) -> Optional[Prices]:
    """Prices for a model, or None when it is unpriced."""
    return MODEL_PRICING.get(model)


def cost_usd(model: str, input_tokens: int, output_tokens: int,
             image_output_tokens: int = 0) -> Decimal:
    """USD for one call. Unknown model -> 0, with a warning: the log row still
    carries the model id, so an unpriced call stays auditable after the fact.

    `output_tokens` is text (and thinking) output only. Image output is passed
    separately because it bills at a different rate — on Gemini 3 Pro Image the
    image rate is 10x the text one, so folding the two together would understate
    an illustration by an order of magnitude.
    """
    priced = rates(model)
    if not priced:
        logger.warning("No price entry for model %r — call logged at 0 cost", model)
        return Decimal('0')
    total = (Decimal(input_tokens or 0) * priced.input
             + Decimal(output_tokens or 0) * priced.output)
    if image_output_tokens:
        image_rate = priced.image_output
        if image_rate is None:
            logger.warning("Model %r returned %d image tokens but has no image rate — "
                           "billing them as text output", model, image_output_tokens)
            image_rate = priced.output
        total += Decimal(image_output_tokens) * image_rate
    return total / _MILLION


def unit_cost_usd(model: str, units) -> Decimal:
    """USD for a per-unit provider call (characters of speech, seconds of audio)."""
    priced = UNIT_PRICING.get(model)
    if not priced:
        logger.warning("No unit price entry for model %r — call logged at 0 cost", model)
        return Decimal('0')
    price, _unit = priced
    return Decimal(str(units or 0)) * price


def unit_name(model: str) -> str:
    """What `units` counts for this model — for the log row, so a number without
    a dimension never lands in the ledger."""
    priced = UNIT_PRICING.get(model)
    return priced[1] if priced else ''


def gemini_usage(model: str, usage_metadata: Any) -> GeminiUsage:
    """Read a `google.genai` usage_metadata into billable quantities + cost.

    Three traps this exists to hide from call sites:
      - `candidates_token_count` INCLUDES image-modality tokens, so pricing it
        wholesale at the text rate underbills an image ~10x.
      - `thoughts_token_count` is NOT in `candidates_token_count` but is billed
        at the output rate, so ignoring it underbills any thinking model.
      - both detail lists can be absent on a blocked or empty response.
    """
    if usage_metadata is None:
        return GeminiUsage(0, 0, 0, Decimal('0'))

    input_tokens = getattr(usage_metadata, 'prompt_token_count', 0) or 0
    candidates = getattr(usage_metadata, 'candidates_token_count', 0) or 0
    thoughts = getattr(usage_metadata, 'thoughts_token_count', 0) or 0

    image_tokens = 0
    for detail in (getattr(usage_metadata, 'candidates_tokens_details', None) or []):
        modality = getattr(detail, 'modality', None)
        if getattr(modality, 'name', str(modality)).upper().endswith('IMAGE'):
            image_tokens += getattr(detail, 'token_count', 0) or 0

    text_output = max(candidates - image_tokens, 0) + thoughts
    cost = cost_usd(model, input_tokens, text_output, image_tokens)
    return GeminiUsage(input_tokens, text_output, image_tokens, cost)
