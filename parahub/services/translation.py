"""Machine translation service — pluggable provider, Gemini Flash Lite first.

Fills the *machine* layer of the two-layer i18n scheme only: authoritative
``*_i18n`` maps are human-written and never touched here. Callers cache the
result themselves (per-row ``mt_cache``) and wipe that cache when the source
text is edited.

Failure contract: every public method returns ``None`` instead of raising —
an unavailable provider degrades to showing the original text, never to an
error on the read path.

Security contract: provider output is untrusted input. For HTML fields the
caller passes its own sanitizer and ``translate_html()`` applies it to the
translation before returning — the same nh3 profile that guards user input
must guard the model's output.
"""
import logging
import time
from typing import Callable, Optional, Tuple

logger = logging.getLogger(__name__)

# The 6 project locales — the only languages worth caching.
PROJECT_LANGS = {'en', 'ru', 'pt', 'es', 'de', 'fr'}

# Fresh provider calls allowed per API request (unit = one translate() call).
# Cached entries are free; a cold list warms progressively across requests.
MT_PER_REQUEST_CAP = 3

LANGUAGE_NAMES = {
    'en': 'English',
    'ru': 'Russian',
    'pt': 'Portuguese',
    'es': 'Spanish',
    'de': 'German',
    'fr': 'French',
}

GEMINI_TRANSLATION_MODEL = 'gemini-3.5-flash-lite'


class GeminiTranslationProvider:
    """Gemini Flash Lite translation. Marketing/UGC copy needs an LLM's
    register awareness; volume is tiny, so per-call cost is negligible."""

    def __init__(self, api_key: str, model: str = GEMINI_TRANSLATION_MODEL):
        from google import genai
        self.client = genai.Client(api_key=api_key)
        self.model_name = model
        # Token usage of the most recent translate() call, for TranslationLog.
        # Safe as instance state: get_provider() builds a fresh provider per
        # call, so two concurrent requests never share one.
        self.last_usage: Tuple[int, int] = (0, 0)

    def translate(self, text: str, source_lang: str, target_lang: str,
                  html: bool = False) -> str:
        from google.genai import types as genai_types

        source = LANGUAGE_NAMES.get(source_lang, source_lang)
        target = LANGUAGE_NAMES.get(target_lang, target_lang)
        if html:
            prompt = (
                f"Translate the text content of this HTML fragment from {source} to {target}. "
                "Keep every HTML tag and attribute exactly as it is — translate only the "
                "human-readable text between tags. Keep the tone and register of the original. "
                "Return only the translated HTML fragment, nothing else.\n\n"
                f"{text}"
            )
        else:
            prompt = (
                f"Translate from {source} to {target}, keeping the tone and register "
                "of the original. Return only the translation, nothing else.\n\n"
                f"{text}"
            )

        self.last_usage = (0, 0)
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=4096,
            ),
        )
        # Read usage before the blocked/empty checks below: a refused answer is
        # still billed for its input tokens, and the ledger must show that.
        usage = getattr(response, 'usage_metadata', None)
        if usage is not None:
            self.last_usage = (getattr(usage, 'prompt_token_count', 0) or 0,
                               getattr(usage, 'candidates_token_count', 0) or 0)
        if response.candidates:
            finish_reason = response.candidates[0].finish_reason
            if finish_reason and finish_reason != genai_types.FinishReason.STOP:
                raise ValueError(f"Gemini blocked translation: {finish_reason.name}")
        result = (response.text or '').strip() if hasattr(response, 'text') else ''
        if not result:
            raise ValueError("Gemini returned empty translation")
        return result


def _usage_of(provider) -> Tuple[int, int]:
    """(input, output) tokens of the provider's last call.

    Deliberately defensive: test doubles are MagicMocks with no real usage, and
    a call logged at zero tokens is a far better outcome than an exception on
    the read path.
    """
    usage = getattr(provider, 'last_usage', None)
    if (isinstance(usage, tuple) and len(usage) == 2
            and all(isinstance(v, int) for v in usage)):
        return usage
    return (0, 0)


def _log_translation(*, provider, source_lang, target_lang, text, context,
                     started_at, is_html=False, error=None):
    """Write one ``TranslationLog`` row.

    Never raises: accounting must not be able to break the path it measures.
    Every value is stringified before slicing because the provider may be a
    test double whose attributes are mocks, not strings.
    """
    try:
        from parahub.models import TranslationLog
        from parahub.services.ai_pricing import cost_usd

        model_name = str(getattr(provider, 'model_name', '') or '')[:64]
        input_tokens, output_tokens = _usage_of(provider)
        ctx = context or {}
        TranslationLog.objects.create(
            model_name=model_name,
            source_lang=str(source_lang or '')[:10],
            target_lang=str(target_lang or '')[:10],
            object_type=str(ctx.get('object_type') or '')[:32],
            object_id=str(ctx.get('object_id') or '')[:26],
            field_name=str(ctx.get('field_name') or '')[:32],
            source_chars=len(text or ''),
            is_html=is_html,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd(model_name, input_tokens, output_tokens),
            duration_ms=int((time.monotonic() - started_at) * 1000),
            success=error is None,
            error_message=str(error)[:300] if error else '',
        )
    except Exception as e:
        logger.warning("Failed to log translation usage: %s", e)


class TranslationService:
    """Entry point. Provider comes from AISettings (same key as vision/zenith);
    swapping the provider touches only this module — cache and callers stay.

    Every provider call is written to ``TranslationLog``; ``context`` names the
    row being translated so spend can be attributed to an object and field.
    """

    @staticmethod
    def get_provider() -> Optional[GeminiTranslationProvider]:
        try:
            from parahub.models import AISettings
            ai_settings = AISettings.objects.first()
            if ai_settings and ai_settings.enabled and ai_settings.google_api_key:
                return GeminiTranslationProvider(ai_settings.google_api_key)
        except Exception as e:
            logger.warning(f"Could not load translation provider: {e}")
        return None

    @staticmethod
    def translate(text: str, source_lang: str, target_lang: str,
                  context: Optional[dict] = None) -> Optional[str]:
        """Plain-text translation, or None if unavailable/failed.

        ``context`` is an optional ``{object_type, object_id, field_name}`` dict
        used only to attribute the cost in ``TranslationLog``.
        """
        if not text or source_lang == target_lang:
            return None
        provider = TranslationService.get_provider()
        if not provider:
            return None
        started_at = time.monotonic()
        try:
            result = provider.translate(text, source_lang, target_lang)
        except Exception as e:
            logger.warning(f"Translation {source_lang}->{target_lang} failed: {e}")
            _log_translation(provider=provider, source_lang=source_lang,
                             target_lang=target_lang, text=text, context=context,
                             started_at=started_at, error=e)
            return None
        _log_translation(provider=provider, source_lang=source_lang,
                         target_lang=target_lang, text=text, context=context,
                         started_at=started_at)
        return result

    @staticmethod
    def translate_html(html: str, source_lang: str, target_lang: str,
                       sanitizer: Callable[[str], str],
                       context: Optional[dict] = None) -> Optional[str]:
        """HTML translation, re-sanitized with the caller's profile, or None."""
        if not html or source_lang == target_lang:
            return None
        provider = TranslationService.get_provider()
        if not provider:
            return None
        started_at = time.monotonic()
        try:
            translated = provider.translate(html, source_lang, target_lang, html=True)
        except Exception as e:
            logger.warning(f"HTML translation {source_lang}->{target_lang} failed: {e}")
            _log_translation(provider=provider, source_lang=source_lang,
                             target_lang=target_lang, text=html, context=context,
                             started_at=started_at, is_html=True, error=e)
            return None
        _log_translation(provider=provider, source_lang=source_lang,
                         target_lang=target_lang, text=html, context=context,
                         started_at=started_at, is_html=True)
        return sanitizer(translated)


def resolve_mt_fields(*, model, pk, source_lang, mt_cache, translate_to,
                      mt_budget, fields):
    """Cached-or-fresh machine translation for one UGC row (``mt_cache`` pattern).

    ``fields`` is ``{name: source_text}``; each field resolves independently:
    ``mt_cache[translate_to][name]`` when present, otherwise one fresh provider
    call while ``mt_budget`` lasts (a 1-element list shared across the request,
    unit = one ``translate()`` call). Fresh results are merged into the row's
    ``mt_cache`` through a read-modify-write on a freshly loaded copy, so a
    concurrent writer for a sibling language loses at worst its own entry.

    The model owns invalidation: if its text is editable, the editing endpoint
    must wipe ``mt_cache`` on a real change (market pattern); immutable text
    (civic ideas) needs no wipe path at all.

    Returns ``({name: translation_or_None}, any_translated)``.
    """
    out = {name: None for name in fields}
    if (not translate_to or translate_to not in PROJECT_LANGS
            or not source_lang or source_lang == translate_to):
        return out, False
    cached = (mt_cache or {}).get(translate_to) or {}
    fresh_entry = {}
    for name, text in fields.items():
        out[name] = cached.get(name)
        if out[name] is None and text and mt_budget[0] > 0:
            mt_budget[0] -= 1
            translated = TranslationService.translate(
                text, source_lang, translate_to,
                context={'object_type': model.__name__.lower(),
                         'object_id': pk, 'field_name': name})
            if translated:
                fresh_entry[name] = out[name] = translated
    if fresh_entry:
        row_cache = model.objects.filter(pk=pk).values_list('mt_cache', flat=True).first() or {}
        row_cache[translate_to] = {**(row_cache.get(translate_to) or {}), **fresh_entry}
        model.objects.filter(pk=pk).update(mt_cache=row_cache)
    return out, any(v is not None for v in out.values())
