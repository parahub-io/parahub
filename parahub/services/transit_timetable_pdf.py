"""
Branded (Parahub) transit timetable PDF — the printable analogue of the route
timetable. One A4 page per direction: the line's stop list (with intermodal-
interchange markers) on the left, and a SEASONAL departure table on the right —
hour rows × one column per service pattern (weekday / Saturday / Sunday, split by
season where the schedule differs), mirroring how operators print their sheets.

The seasonal columns are built upstream (`_route_timetable_seasonal`) by grouping
services with identical schedules; this module only renders. It is Django-free:
it takes plain dicts so it stays unit-testable and the endpoint owns all DB access.

Usage:
    from parahub.services.transit_timetable_pdf import generate_timetable_pdf
    pdf_bytes = generate_timetable_pdf(short_name=..., directions=[...], ...)
"""

import io
import logging
import os
from datetime import date as date_cls

import qrcode
from reportlab.lib.pagesizes import A4, mm
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

# Unicode TTFs — required: Helvetica (PDF base-14) has no Cyrillic, so a `lang=ru`
# sheet would render blank. DejaVu covers Latin + Cyrillic + accented PT/ES/FR/DE.
_FONT_DIR = "/usr/share/fonts/truetype/dejavu"
FONT_REGULAR = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FONT_MONO = "Courier"
try:
    pdfmetrics.registerFont(TTFont("PHSans", os.path.join(_FONT_DIR, "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("PHSans-Bold", os.path.join(_FONT_DIR, "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("PHMono", os.path.join(_FONT_DIR, "DejaVuSansMono.ttf")))
    FONT_REGULAR, FONT_BOLD, FONT_MONO = "PHSans", "PHSans-Bold", "PHMono"
except Exception as e:  # pragma: no cover — fonts ship with the OS image
    logger.warning("Timetable PDF: DejaVu fonts unavailable (%s); Cyrillic will not render.", e)

LOGO_PATH = "/opt/parahub/parahub/static/logo.png"

# Page geometry
PAGE_W, PAGE_H = A4
MARGIN = 16 * mm
COL_L_W = 44 * mm          # stop-list column width
GUTTER = 6 * mm
FOOTER_H = 18 * mm
VARIANT_COLOR = HexColor("#0EA5E9")

INK = HexColor("#111827")
MUTED = HexColor("#6B7280")
HAIR = HexColor("#E5E7EB")

# Default route colour by GTFS route_type when the feed ships none — mirror of the
# frontend useTransitHelpers.defaultColorForType so the PDF badge matches the chip.
_DEFAULT_COLOR_BY_TYPE = {
    0: "00A550", 1: "0033A0", 2: "6D6E71", 3: "EFF216",
    4: "0077C8", 7: "8B4513", 11: "00A550",
}

# Compact, language-neutral interchange letters (legend localises them).
_MODE_LETTER = {
    "metro": "M", "rail": "R", "tram": "T", "ferry": "F",
    "funicular": "Fu", "bus": "B", "air": "A",
}

LABELS = {
    "en": {"stops": "Stops", "departures": "Departures", "no_service": "No service",
           "outbound": "Outbound", "inbound": "Inbound", "special": "Special service",
           "days": "days",
           "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
           "modes": {"metro": "Metro", "rail": "Rail", "tram": "Tram", "ferry": "Ferry",
                     "funicular": "Funicular", "bus": "Bus", "air": "Air"},
           "daytypes": {"weekday": "Weekdays", "sat": "Saturdays",
                        "sun": "Sundays & holidays", "all": "Daily"},
           "seasons": {"winter": "Winter", "summer": "Summer", "spring": "Spring",
                       "autumn": "Autumn", "august": "August",
                       "school_holidays": "School holidays", "christmas": "Christmas",
                       "new_year": "New Year", "christmas_new_year": "Christmas & New Year",
                       "easter": "Easter", "holidays": "Holidays"}},
    "pt": {"stops": "Paragens", "departures": "Partidas", "no_service": "Sem serviço",
           "outbound": "Ida", "inbound": "Volta", "special": "Serviço especial",
           "days": "dias",
           "weekdays": ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"],
           "modes": {"metro": "Metro", "rail": "Comboio", "tram": "Elétrico", "ferry": "Barco",
                     "funicular": "Funicular", "bus": "Autocarro", "air": "Avião"},
           "daytypes": {"weekday": "Dias úteis", "sat": "Sábados",
                        "sun": "Domingos e feriados", "all": "Todos os dias"},
           "seasons": {"winter": "Inverno", "summer": "Verão", "spring": "Primavera",
                       "autumn": "Outono", "august": "Agosto",
                       "school_holidays": "Férias escolares", "christmas": "Natal",
                       "new_year": "Ano Novo", "christmas_new_year": "Natal e Ano Novo",
                       "easter": "Páscoa", "holidays": "Feriados"}},
    "es": {"stops": "Paradas", "departures": "Salidas", "no_service": "Sin servicio",
           "outbound": "Ida", "inbound": "Vuelta", "special": "Servicio especial",
           "days": "días",
           "weekdays": ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"],
           "modes": {"metro": "Metro", "rail": "Tren", "tram": "Tranvía", "ferry": "Ferry",
                     "funicular": "Funicular", "bus": "Autobús", "air": "Avión"},
           "daytypes": {"weekday": "Días laborables", "sat": "Sábados",
                        "sun": "Domingos y festivos", "all": "Todos los días"},
           "seasons": {"winter": "Invierno", "summer": "Verano", "spring": "Primavera",
                       "autumn": "Otoño", "august": "Agosto",
                       "school_holidays": "Vac. escolares", "christmas": "Navidad",
                       "new_year": "Año Nuevo", "christmas_new_year": "Navidad y Año Nuevo",
                       "easter": "Pascua", "holidays": "Festivos"}},
    "fr": {"stops": "Arrêts", "departures": "Départs", "no_service": "Pas de service",
           "outbound": "Aller", "inbound": "Retour", "special": "Service spécial",
           "days": "jours",
           "weekdays": ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"],
           "modes": {"metro": "Métro", "rail": "Train", "tram": "Tram", "ferry": "Ferry",
                     "funicular": "Funiculaire", "bus": "Bus", "air": "Avion"},
           "daytypes": {"weekday": "Jours ouvrables", "sat": "Samedis",
                        "sun": "Dim. et fériés", "all": "Tous les jours"},
           "seasons": {"winter": "Hiver", "summer": "Été", "spring": "Printemps",
                       "autumn": "Automne", "august": "Août",
                       "school_holidays": "Vac. scolaires", "christmas": "Noël",
                       "new_year": "Nouvel An", "christmas_new_year": "Noël et Nouvel An",
                       "easter": "Pâques", "holidays": "Fériés"}},
    "de": {"stops": "Haltestellen", "departures": "Abfahrten", "no_service": "Kein Verkehr",
           "outbound": "Hinfahrt", "inbound": "Rückfahrt", "special": "Sonderverkehr",
           "days": "Tage",
           "weekdays": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
           "modes": {"metro": "U-Bahn", "rail": "Bahn", "tram": "Tram", "ferry": "Fähre",
                     "funicular": "Standseilbahn", "bus": "Bus", "air": "Flug"},
           "daytypes": {"weekday": "Werktags", "sat": "Samstags",
                        "sun": "Sonn- u. feiertags", "all": "Täglich"},
           "seasons": {"winter": "Winter", "summer": "Sommer", "spring": "Frühling",
                       "autumn": "Herbst", "august": "August",
                       "school_holidays": "Schulferien", "christmas": "Weihnachten",
                       "new_year": "Neujahr", "christmas_new_year": "Weihnachten & Neujahr",
                       "easter": "Ostern", "holidays": "Feiertage"}},
    "ru": {"stops": "Остановки", "departures": "Отправления", "no_service": "Нет рейсов",
           "outbound": "Туда", "inbound": "Обратно", "special": "Особый режим",
           "days": "дн.",
           "weekdays": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
           "modes": {"metro": "Метро", "rail": "Поезд", "tram": "Трамвай", "ferry": "Паром",
                     "funicular": "Фуникулёр", "bus": "Автобус", "air": "Самолёт"},
           "daytypes": {"weekday": "Будни", "sat": "Суббота",
                        "sun": "Воскр. и праздники", "all": "Ежедневно"},
           "seasons": {"winter": "Зима", "summer": "Лето", "spring": "Весна",
                       "autumn": "Осень", "august": "Август",
                       "school_holidays": "Школьные каникулы", "christmas": "Рождество",
                       "new_year": "Новый год", "christmas_new_year": "Рождество и Новый год",
                       "easter": "Пасха", "holidays": "Праздники"}},
}


def _labels(lang):
    return LABELS.get((lang or "en")[:2], LABELS["en"])


def _hex(value, default):
    v = (value or "").strip().lstrip("#")
    if len(v) == 6:
        try:
            return HexColor("#" + v)
        except Exception:
            pass
    return default


def _text_color_for(bg_hex):
    """Black or white for contrast against a 'RRGGBB' background (luminance rule,
    mirrors useTransitHelpers.textColorFor)."""
    v = (bg_hex or "").strip().lstrip("#")
    if len(v) != 6:
        return white
    try:
        r, g, b = int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
    except Exception:
        return white
    return black if (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.5 else white


def _fmt_date(date_iso):
    try:
        return date_cls.fromisoformat(date_iso).strftime("%d/%m/%Y")
    except Exception:
        return date_iso or ""


def _season_text(L, col):
    """Localized season hint for a column (canon key → i18n, else raw feed token)."""
    parts = []
    for raw, key in zip(col.get("seasons", []), col.get("season_keys", [])):
        parts.append(L["seasons"].get(key, raw) if key else raw)
    return " · ".join(p for p in parts if p)


def _truncate(c, text, font, size, max_w):
    if c.stringWidth(text, font, size) <= max_w:
        return text
    while text and c.stringWidth(text + "…", font, size) > max_w:
        text = text[:-1]
    return text + "…"


def generate_timetable_pdf(*, short_name, long_name, route_type, route_color,
                           route_text_color, agency_name, directions, specials,
                           variants, period, page_url, lang="en"):
    """Render the seasonal timetable sheet.

    directions: [{"arrow": "→"/"←", "headsign": str,
                  "stops": [{"name": str, "modes": [str]}],
                  "columns": [{"day_type": str, "seasons": [str], "season_keys": [str|None],
                               "show_seasons": bool, "departures": [{"t": "HH:MM", "v": int}]}]}]
    specials:   [{"seasons": [str], "season_keys": [str|None], "n_dates": int}]
    variants:   [{"index": int, "long_name": str}]
    period:     [min_iso, max_iso] | None
    """
    L = _labels(lang)
    resolved_color = route_color or _DEFAULT_COLOR_BY_TYPE.get(route_type if route_type is not None else 3, "EFF216")
    badge_bg = _hex(resolved_color, HexColor("#EFF216"))
    badge_fg = _hex(route_text_color, None) or _text_color_for(resolved_color)
    period_str = ""
    if period and len(period) == 2:
        a, b = _fmt_date(period[0]), _fmt_date(period[1])
        period_str = f"{a} – {b}" if a != b else a

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setAuthor("Parahub")
    c.setTitle(f"{short_name} — {long_name}")
    c.setSubject("Timetable")

    pages = [d for d in directions if d.get("stops") or d.get("columns")] or [{"stops": [], "columns": []}]
    qr_img = _qr_image(page_url)
    for d in pages:
        _draw_header(c, L, short_name, long_name, badge_bg, badge_fg, agency_name, period_str, d)
        _draw_stops(c, L, d.get("stops") or [])
        y = _draw_seasonal_table(c, L, d.get("columns") or [])
        _draw_footnotes(c, L, specials, variants, y)
        _draw_footer(c, L, page_url, qr_img, badge_bg)
        c.showPage()

    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def _qr_image(url):
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=0)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return ImageReader(buf)


def _draw_header(c, L, short_name, long_name, badge_bg, badge_fg, agency_name, period_str, direction):
    top = PAGE_H - MARGIN

    logo_sz = 8 * mm
    if os.path.exists(LOGO_PATH):
        try:
            c.drawImage(ImageReader(LOGO_PATH), MARGIN, top - logo_sz, width=logo_sz,
                        height=logo_sz, preserveAspectRatio=True, mask="auto")
        except Exception as e:
            logger.warning("Timetable PDF logo: %s", e)
    c.setFont(FONT_BOLD, 13)
    c.setFillColor(INK)
    c.drawString(MARGIN + logo_sz + 3 * mm, top - logo_sz + 2.2 * mm, "PARAHUB")

    badge_label = (short_name or "").strip() or "—"
    badge_h, pad = 9 * mm, 3 * mm
    bw = max(c.stringWidth(badge_label, FONT_BOLD, 15) + 2 * pad, 11 * mm)
    bx, by = PAGE_W - MARGIN - bw, top - badge_h + 0.5 * mm
    c.setFillColor(badge_bg)
    c.roundRect(bx, by, bw, badge_h, 2 * mm, fill=1, stroke=0)
    c.setFillColor(badge_fg)
    c.setFont(FONT_BOLD, 15)
    c.drawCentredString(bx + bw / 2, by + badge_h / 2 - 5, badge_label)

    rule_y = top - 11 * mm
    c.setStrokeColor(badge_bg)
    c.setLineWidth(1.4)
    c.line(MARGIN, rule_y, PAGE_W - MARGIN, rule_y)

    c.setFillColor(INK)
    c.setFont(FONT_BOLD, 13)
    c.drawString(MARGIN, rule_y - 6 * mm, _truncate(c, long_name or "", FONT_BOLD, 13, PAGE_W - 2 * MARGIN))

    meta = " · ".join([p for p in [agency_name, period_str] if p])
    c.setFillColor(MUTED)
    c.setFont(FONT_REGULAR, 8.5)
    c.drawString(MARGIN, rule_y - 10 * mm, meta)

    arrow = direction.get("arrow", "")
    headsign = direction.get("headsign", "") or (L["inbound"] if arrow == "←" else L["outbound"])
    c.setFillColor(INK)
    c.setFont(FONT_BOLD, 10.5)
    c.drawString(MARGIN, rule_y - 15 * mm, f"{arrow}  {_truncate(c, headsign, FONT_BOLD, 10.5, PAGE_W - 2 * MARGIN - 10)}")


def _body_top():
    return PAGE_H - MARGIN - 38 * mm


def _body_bottom():
    return MARGIN + FOOTER_H


def _section_heading(c, x, y, w, text):
    c.setFillColor(INK)
    c.setFont(FONT_BOLD, 9)
    c.drawString(x, y, text.upper())
    c.setStrokeColor(HAIR)
    c.setLineWidth(0.6)
    c.line(x, y - 2.5 * mm, x + w, y - 2.5 * mm)
    return y - 6 * mm


def _draw_stops(c, L, stops):
    x = MARGIN
    y = _section_heading(c, x, _body_top(), COL_L_W, f"{L['stops']}  ({len(stops)})")
    if not stops:
        return
    avail = y - _body_bottom()
    line_h = min(4.4 * mm, max(2.8 * mm, avail / max(len(stops), 1)))
    size = max(5.8, min(8.0, line_h / mm * 1.9))
    used_modes = set()
    idx_w = c.stringWidth(f"{len(stops)}", FONT_BOLD, size) + 2.0 * mm
    for i, s in enumerate(stops, 1):
        if y < _body_bottom():
            break
        c.setFillColor(MUTED)
        c.setFont(FONT_BOLD, size)
        c.drawRightString(x + idx_w - 1.5 * mm, y, f"{i}")
        modes = [m for m in (s.get("modes") or []) if m in _MODE_LETTER]
        used_modes.update(modes)
        tag = ("  " + " ".join(_MODE_LETTER[m] for m in modes)) if modes else ""
        tag_w = c.stringWidth(tag, FONT_BOLD, size) if tag else 0
        name = _truncate(c, s.get("name", ""), FONT_REGULAR, size, COL_L_W - idx_w - tag_w)
        c.setFillColor(INK)
        c.setFont(FONT_REGULAR, size)
        c.drawString(x + idx_w, y, name)
        if tag:
            c.setFillColor(MUTED)
            c.setFont(FONT_BOLD, size)
            c.drawString(x + idx_w + c.stringWidth(name, FONT_REGULAR, size), y, tag)
        y -= line_h
    if used_modes:
        y -= 1.5 * mm
        c.setFillColor(MUTED)
        c.setFont(FONT_REGULAR, 6.0)
        legend = "  ".join(f"{_MODE_LETTER[m]}={L['modes'][m]}" for m in _MODE_LETTER if m in used_modes)
        c.drawString(x, max(y, _body_bottom()), _truncate(c, legend, FONT_REGULAR, 6.0, COL_L_W))


def _wrap_minutes(c, tokens, w, font, size, gap):
    """Pack (mm, v) tokens into lines fitting width w. Returns list[list[(mm,v)]]."""
    lines, cur, cur_w = [], [], 0.0
    for mm_str, v in tokens:
        tw = c.stringWidth(mm_str, font, size) + (c.stringWidth(str(v), FONT_BOLD, size * 0.7) if v else 0)
        if cur and cur_w + tw > w:
            lines.append(cur)
            cur, cur_w = [], 0.0
        cur.append((mm_str, v))
        cur_w += tw + gap
    if cur:
        lines.append(cur)
    return lines or [[]]


def _draw_seasonal_table(c, L, columns):
    """Hour rows × season columns. Returns the y where the table ended."""
    x = MARGIN + COL_L_W + GUTTER
    width = PAGE_W - MARGIN - x
    y_head = _body_top()
    c.setFillColor(INK)
    c.setFont(FONT_BOLD, 9)
    c.drawString(x, y_head, L["departures"].upper())

    cols = [col for col in columns if col.get("departures")]
    if not cols:
        c.setFillColor(MUTED)
        c.setFont(FONT_REGULAR, 9)
        c.drawString(x, y_head - 7 * mm, L["no_service"])
        return y_head - 10 * mm

    hour_w = 8.5 * mm
    n = len(cols)
    col_w = (width - hour_w) / n
    size = 7.6 if n <= 4 else 6.8
    gap = 1.8 * mm
    line_h = size / mm * 1.5 * mm

    # Column headers (day-type + season hint), 3 lines tall
    hy = y_head - 5 * mm
    head_size = 7.8 if n <= 4 else 7.0
    for i, col in enumerate(cols):
        cx = x + hour_w + i * col_w
        c.setFillColor(INK)
        # Auto-fit the day-type label to the column width (long localized labels
        # like "Воскр. и праздники" / "Domingos e feriados" must not get clipped).
        dt_label = L["daytypes"].get(col["day_type"], col["day_type"])
        hsz = head_size
        while hsz > 5.6 and c.stringWidth(dt_label, FONT_BOLD, hsz) > col_w - 1.5 * mm:
            hsz -= 0.2
        c.setFont(FONT_BOLD, hsz)
        c.drawString(cx, hy, _truncate(c, dt_label, FONT_BOLD, hsz, col_w - 1.5 * mm))
        if col.get("show_seasons"):
            season = _season_text(L, col)
            c.setFillColor(MUTED)
            c.setFont(FONT_REGULAR, 6.2)
            # season hint may wrap to 2 lines
            words = season.split(" · ")
            ln, cur = [], ""
            for wd in words:
                trial = (cur + " · " + wd) if cur else wd
                if c.stringWidth(trial, FONT_REGULAR, 6.2) > col_w - 1.5 * mm and cur:
                    ln.append(cur)
                    cur = wd
                else:
                    cur = trial
            if cur:
                ln.append(cur)
            for k, t in enumerate(ln[:2]):
                c.drawString(cx, hy - 3.0 * mm - k * 2.6 * mm, _truncate(c, t, FONT_REGULAR, 6.2, col_w - 1.5 * mm))

    head_bottom = hy - 9 * mm
    c.setStrokeColor(HAIR)
    c.setLineWidth(0.6)
    c.line(x, head_bottom, x + width, head_bottom)

    # Per-column hour → [(mm, v)]
    by_hour = []
    hours = set()
    for col in cols:
        m = {}
        for dep in col["departures"]:
            m.setdefault(dep["t"][:2], []).append((dep["t"][3:5], dep.get("v", 0)))
            hours.add(dep["t"][:2])
        by_hour.append(m)

    y = head_bottom - 4 * mm
    for hour in sorted(hours):
        wrapped = [_wrap_minutes(c, by_hour[i].get(hour, []), col_w - 1.5 * mm, FONT_MONO, size, gap)
                   for i in range(n)]
        rows = max((len(w) for w in wrapped), default=1)
        row_h = rows * line_h + 0.8 * mm
        if y - row_h < _body_bottom():
            break
        c.setFillColor(INK)
        c.setFont(FONT_BOLD, size)
        c.drawString(x, y, hour)
        for i in range(n):
            cx = x + hour_w + i * col_w
            ly = y
            for line in wrapped[i]:
                px = cx
                for mm_str, v in line:
                    c.setFillColor(INK)
                    c.setFont(FONT_MONO, size)
                    c.drawString(px, ly, mm_str)
                    tw = c.stringWidth(mm_str, FONT_MONO, size)
                    if v:
                        c.setFillColor(VARIANT_COLOR)
                        c.setFont(FONT_BOLD, size * 0.7)
                        c.drawString(px + tw + 0.3 * mm, ly + size * 0.32, str(v))
                        tw += c.stringWidth(str(v), FONT_BOLD, size * 0.7)
                    px += tw + gap
                ly -= line_h
        y -= row_h
    return y


def _draw_footnotes(c, L, specials, variants, y):
    x = MARGIN + COL_L_W + GUTTER
    width = PAGE_W - MARGIN - x
    y -= 2 * mm
    if (specials or variants) and y > _body_bottom():
        c.setStrokeColor(HAIR)
        c.setLineWidth(0.5)
        c.line(x, y, x + width, y)
        y -= 4 * mm
    for v in (variants or []):
        if y < _body_bottom():
            break
        c.setFillColor(VARIANT_COLOR)
        c.setFont(FONT_BOLD, 6.5)
        c.drawString(x, y + 1.2, str(v["index"]))
        c.setFillColor(MUTED)
        c.setFont(FONT_REGULAR, 7.5)
        c.drawString(x + 3 * mm, y, _truncate(c, v.get("long_name", ""), FONT_REGULAR, 7.5, width - 3 * mm))
        y -= 3.6 * mm
    for sp in (specials or []):
        if y < _body_bottom():
            break
        season = _season_text(L, sp) or L["daytypes"].get(sp.get("day_type"), "")
        txt = f"{L['special']}: {season} ({sp.get('n_dates', 0)} {L['days']})"
        c.setFillColor(MUTED)
        c.setFont(FONT_REGULAR, 7.5)
        c.drawString(x, y, _truncate(c, txt, FONT_REGULAR, 7.5, width))
        y -= 3.6 * mm


def _draw_footer(c, L, page_url, qr_img, bar_color):
    bar_y = MARGIN + FOOTER_H - 1 * mm
    c.setStrokeColor(bar_color)
    c.setLineWidth(1.4)
    c.line(MARGIN, bar_y, PAGE_W - MARGIN - 16 * mm, bar_y)

    qr_sz = 14 * mm
    c.drawImage(qr_img, PAGE_W - MARGIN - qr_sz, MARGIN, width=qr_sz, height=qr_sz)

    c.setFillColor(INK)
    c.setFont(FONT_BOLD, 8.5)
    c.drawString(MARGIN, bar_y - 5 * mm, "parahub.io")
    c.setFillColor(MUTED)
    c.setFont(FONT_REGULAR, 7.5)
    c.drawString(MARGIN, bar_y - 9 * mm, _truncate(c, page_url, FONT_REGULAR, 7.5, PAGE_W - 2 * MARGIN - qr_sz - 6 * mm))
