"""US EPA Air Quality Index from PM2.5 (µg/m³).

Single source of truth for the AQI number + category slug shared by the map
snapshot and the station panel. Colors live on the frontend (design tokens);
here we only classify. Breakpoints: EPA 2024 PM2.5 table (24 h, µg/m³).
"""

# (pm_lo, pm_hi, aqi_lo, aqi_hi, category slug)
_PM25_BREAKPOINTS = [
    (0.0, 9.0, 0, 50, 'good'),
    (9.1, 35.4, 51, 100, 'moderate'),
    (35.5, 55.4, 101, 150, 'unhealthy_sensitive'),
    (55.5, 125.4, 151, 200, 'unhealthy'),
    (125.5, 225.4, 201, 300, 'very_unhealthy'),
    (225.5, 500.4, 301, 500, 'hazardous'),
]


def us_aqi_pm25(pm25):
    """Return ``(aqi:int, category:str)`` for a PM2.5 concentration, or
    ``(None, None)`` if ``pm25`` is missing or out of range."""
    if pm25 is None:
        return None, None
    try:
        c = float(pm25)
    except (TypeError, ValueError):
        return None, None
    if c < 0:
        return None, None
    # Truncate to 1 decimal, as the EPA method specifies.
    c = int(c * 10) / 10.0
    for pm_lo, pm_hi, aqi_lo, aqi_hi, slug in _PM25_BREAKPOINTS:
        if pm_lo <= c <= pm_hi:
            aqi = round((aqi_hi - aqi_lo) / (pm_hi - pm_lo) * (c - pm_lo) + aqi_lo)
            return aqi, slug
    # Above the top breakpoint: clamp to the ceiling.
    return 500, 'hazardous'
