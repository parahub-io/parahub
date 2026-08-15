"""Write one row per paid model call for the paths with no ledger of their own.

Call sites use these helpers instead of touching `AIUsageLog` directly so that
the pricing split (image tokens vs text tokens vs per-unit media) lives in one
place, and so that a metering failure can never take down the feature being
metered — every helper swallows its own errors.
"""
import logging
from decimal import Decimal

from asgiref.sync import sync_to_async

from parahub.services import ai_pricing

logger = logging.getLogger(__name__)


def record_gemini(kind: str, model: str, response, *, profile=None, duration_ms: int = 0,
                  meta: dict = None, success: bool = True, error: str = ''):
    """Log a `google.genai` call, pricing image output at the image rate.

    `response` is the SDK response; usage is read off `usage_metadata`, which is
    absent on a blocked answer — that logs as a zero-token row rather than
    raising, because a blocked call still tells us the path was exercised.
    """
    usage = ai_pricing.gemini_usage(model, getattr(response, 'usage_metadata', None))
    return _write(kind, model, profile=profile, duration_ms=duration_ms, meta=meta,
                  success=success, error=error,
                  input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                  image_tokens=usage.image_tokens, cost=usage.cost)


def record_tokens(kind: str, model: str, input_tokens: int, output_tokens: int, *,
                  profile=None, duration_ms: int = 0, meta: dict = None,
                  success: bool = True, error: str = ''):
    """Log a token-billed call from a provider whose SDK is not google.genai."""
    return _write(kind, model, profile=profile, duration_ms=duration_ms, meta=meta,
                  success=success, error=error,
                  input_tokens=input_tokens, output_tokens=output_tokens, image_tokens=0,
                  cost=ai_pricing.cost_usd(model, input_tokens, output_tokens))


def record_units(kind: str, model: str, units, *, profile=None, duration_ms: int = 0,
                 meta: dict = None, success: bool = True, error: str = ''):
    """Log a call billed per unit of media (speech characters, audio seconds)."""
    return _write(kind, model, profile=profile, duration_ms=duration_ms, meta=meta,
                  success=success, error=error,
                  units=Decimal(str(units or 0)), unit_kind=ai_pricing.unit_name(model),
                  cost=ai_pricing.unit_cost_usd(model, units))


def _write(kind, model, *, profile=None, duration_ms=0, meta=None, success=True, error='',
           input_tokens=0, output_tokens=0, image_tokens=0, units=Decimal('0'),
           unit_kind='', cost=Decimal('0')):
    from parahub.models import AIUsageLog
    try:
        return AIUsageLog.objects.create(
            kind=kind, model_name=model, profile=profile,
            input_tokens=input_tokens, output_tokens=output_tokens, image_tokens=image_tokens,
            units=units, unit_kind=unit_kind, cost_usd=cost,
            duration_ms=int(duration_ms or 0), success=success, error_message=(error or '')[:300],
            meta=meta or {},
        )
    except Exception:
        # Metering must never break the path it measures.
        logger.exception("Failed to write AIUsageLog row for %s/%s", kind, model)
        return None


arecord_gemini = sync_to_async(record_gemini, thread_sensitive=True)
arecord_tokens = sync_to_async(record_tokens, thread_sensitive=True)
arecord_units = sync_to_async(record_units, thread_sensitive=True)
