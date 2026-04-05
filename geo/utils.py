import logging

logger = logging.getLogger(__name__)
PELIAS_URL = "http://localhost:4000"


def get_country_code_from_coords(lat: float, lon: float) -> str:
    """Return ISO 3166-1 alpha-2 country code from coordinates via Pelias reverse geocoding."""
    import requests
    try:
        r = requests.get(
            f"{PELIAS_URL}/v1/reverse",
            params={'point.lat': lat, 'point.lon': lon, 'size': 1},
            timeout=5,
        )
        features = r.json().get('features', [])
        if features:
            return features[0].get('properties', {}).get('country_code', '') or ''
    except Exception as e:
        logger.warning(f"Pelias reverse geocode failed: {e}")
    return ''


def get_country_code_from_request(request) -> str:
    """Return ISO 3166-1 alpha-2 country code from request IP via GeoIP2."""
    import ipaddress
    try:
        from django.contrib.gis.geoip2 import GeoIP2
        ip = (
            request.META.get('HTTP_X_REAL_IP') or
            request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or
            request.META.get('REMOTE_ADDR', '')
        )
        if not ip:
            return ''
        if ipaddress.ip_address(ip).is_private:
            return ''
        return GeoIP2().country_code(ip) or ''
    except Exception:
        return ''


def detect_content_language(title: str, description: str = '', fallback: str = '') -> str:
    """Detect content language from text. Returns ISO 639-1 code or fallback."""
    from langdetect import detect, LangDetectException
    SUPPORTED = {'en', 'ru', 'pt', 'es', 'fr', 'de'}
    text = (title + ' ' + (description or '')).strip()
    if not text:
        return fallback
    try:
        lang = detect(text)
        return lang if lang in SUPPORTED else fallback
    except LangDetectException:
        return fallback
