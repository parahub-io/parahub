"""
Para-ID Badge Generator - PDF generation for printable member badges

Generates a 54x86mm vertical badge suitable for lanyard display.
Document-grid layout (left-ragged, Cartão de Cidadão labeling convention):
name block under the header, ID photo on the left with a labeled field
column beside it, QR code + PGP fingerprint in the bottom machine zone.

Features:
- SVG logo in header
- Humanist face (Liberation Sans) for human fields, OCR-B for machine data
- Labeled bilingual pt/en fields, including the WoT verification count
- Community "WEB OF TRUST" seal at real carimbo scale (40mm), stamped as a
  top ink layer over the photo corner for verified profiles (3+)
- Color-coded by profile type (Personal/Pseudonymous)
- Batch mode: 9 cards on A4 for economical printing

Usage:
    from parahub.services.badge_generator import BadgeGenerator

    # Single badge (54x86mm)
    pdf_bytes = BadgeGenerator.generate(profile)

    # Batch: 9 badges on A4 with cut lines
    pdf_bytes = BadgeGenerator.generate_batch(profile)
"""

import io
import logging
import os
from datetime import date
from typing import Optional

import qrcode
from reportlab.lib.pagesizes import mm, A4
from reportlab.lib.colors import black, white, HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

# Register OCR-B font (EU document style, free clone by Matthew Skala)
# Source: apt install fonts-ocr-b, converted to TTF via fontforge
FONTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'fonts')
OCRB_FONT_PATH = os.path.join(FONTS_DIR, 'OCRB.ttf')

try:
    pdfmetrics.registerFont(TTFont('OCRB', OCRB_FONT_PATH))
    OCRB_AVAILABLE = True
except Exception as e:
    logger.warning(f"Could not load OCRB font: {e}. Falling back to Helvetica.")
    OCRB_AVAILABLE = False

# Fallback for text OCR-B cannot draw: the free clone carries ~140 basic-Latin
# glyphs — no Portuguese diacritics (ç, ã), no Cyrillic — and reportlab drops
# missing glyphs SILENTLY, deleting letters (or whole names) from the PDF.
# DejaVu Sans Mono keeps the monospaced document look and covers both.
FALLBACK_FONT_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'
FALLBACK_BOLD_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf'
FALLBACK_AVAILABLE = False
try:
    pdfmetrics.registerFont(TTFont('BadgeMono', FALLBACK_FONT_PATH))
    pdfmetrics.registerFont(TTFont('BadgeMono-Bold', FALLBACK_BOLD_PATH))
    FALLBACK_AVAILABLE = True
except Exception as e:
    logger.warning(f"Could not load fallback mono font: {e}")

# Humanist face for HUMAN fields (name, initials, labels). Machine data
# (handle, dates, count, fingerprint) stays OCR-B: real documents set the
# holder's name in a humanist sans and reserve OCR type for machine strips —
# OCR-B on human fields is what makes a card read as a sci-fi prop.
# Liberation Sans: metric Arial clone, full Latin Extended + Cyrillic.
HUMAN_FONT_PATHS = {
    'BadgeSans': '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    'BadgeSans-Bold': '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
    'BadgeSans-Italic': '/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf',
    # Wider-coverage fallback for scripts Liberation lacks
    'BadgeSansWide': '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    'BadgeSansWide-Bold': '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
}
HUMAN_AVAILABLE = False
HUMAN_CHARS: set = set()
try:
    for _name, _path in HUMAN_FONT_PATHS.items():
        pdfmetrics.registerFont(TTFont(_name, _path))
    HUMAN_AVAILABLE = True
    from fontTools.ttLib import TTFont as _FTHuman
    HUMAN_CHARS = set(_FTHuman(HUMAN_FONT_PATHS['BadgeSans']).getBestCmap().keys())
except Exception as e:
    logger.warning(f"Could not load humanist fonts: {e}")

# Codepoints OCR-B actually has, for per-string coverage checks
OCRB_CHARS: set = set()
if OCRB_AVAILABLE:
    try:
        from fontTools.ttLib import TTFont as _FTFont
        OCRB_CHARS = set(_FTFont(OCRB_FONT_PATH).getBestCmap().keys())
    except Exception as e:
        logger.warning(f"Could not read OCRB cmap: {e}")
        OCRB_AVAILABLE = False

# Badge dimensions (vertical ID-1 format)
BADGE_WIDTH = 54 * mm
BADGE_HEIGHT = 86 * mm

# Colors by profile type.
# Print palette matches the association stamp (scripts/gen_stamp.py): brand
# primary #FFE216 is too pale on paper, so print artifacts share #E6CA00.
PROFILE_COLORS = {
    'PERSONAL': HexColor('#E6CA00'),      # Print yellow - default
    'PSEUDONYMOUS': HexColor('#6B7280'),  # Gray - pseudonymous
}
PRIMARY_COLOR = PROFILE_COLORS['PERSONAL']  # Default fallback
TEXT_COLOR = black
MUTED_COLOR = HexColor('#666666')
# Near-solid, not light gray: label-size strokes are only a few printer dots
# wide, so consumer inkjets dither anything lighter into broken, illegible
# strokes. Hierarchy against 6pt values comes from size, as on real ID cards.
LABEL_COLOR = HexColor('#444444')
BG_COLOR = white
WOT_COLOR = HexColor('#4E4EC8')  # Brand indigo - same ink as the association stamp

# Logo path (PNG version for PDF embedding)
LOGO_PATH = '/opt/parahub/parahub/static/logo.png'

# WEB OF TRUST seal, generated by scripts/gen_wot_seal.py (carimbo frame
# family, no legal content — public asset, unlike the carimbo)
WOT_SEAL_PATH = '/opt/parahub/parahub/static/wot-seal.png'

# Document grid, Bilhete de Identidade arrangement: photo on the RIGHT with
# the stamp over its lower corner (the classic BI had exactly that — photo
# right, official mark overlapping it), labeled field column on the left.
# All vertical positions are given as distance from the card's TOP edge (t)
# and converted via _ty().
MARGIN_X = 4 * mm
PHOTO_W = 18 * mm
PHOTO_H = 24 * mm       # 3:4 ratio for ID photo
PHOTO_X = BADGE_WIDTH - MARGIN_X - PHOTO_W
PHOTO_TOP = 25.5        # mm from top
FIELDS_X = MARGIN_X     # field column, left of the photo
QR_SIZE = 15 * mm
# 4pt is the practical floor for consumer-inkjet plain paper: below it the
# stroke drops under ~3 printer dots and frays or fills in. Values stay 6pt —
# two clear tiers.
LABEL_SIZE = 4.0
LABEL_EN_SIZE = 3.5
VALUE_SIZE = 6

# The seal at real carimbo scale (40mm — same as the workshop stamp): a real
# stamp on a 54x86 card cannot avoid the content, so it goes where ink is
# least harmful — knot core over the photo's lower corner and the free zone
# below it, ring arcs over watermark, bleeding off the right card edge like
# a hand-placed stamp. Every machine-read element (QR, fingerprint, field
# values) stays outside the ink.
SEAL_SIZE = 40 * mm
SEAL_CX = 40            # mm from left
SEAL_CY = 55            # mm from top
SEAL_ROTATION = -12
SEAL_ALPHA = 0.5

# Batch mode constants (A4: 210x297mm, 3x3 grid)
A4_WIDTH, A4_HEIGHT = A4  # 595.27 x 841.89 points (210x297mm)
BATCH_COLS = 3
BATCH_ROWS = 3
# Center the 3x3 grid on A4
# Total cards width: 54mm * 3 = 162mm, A4 width: 210mm, margin: (210-162)/2 = 24mm
# Total cards height: 86mm * 3 = 258mm, A4 height: 297mm, margin: (297-258)/2 = 19.5mm
BATCH_MARGIN_X = 24 * mm
BATCH_MARGIN_Y = 19.5 * mm
# Cut guides. The only tool this sheet meets is a member's scissors, so every
# card edge gets a guide and every guide spans the whole sheet: a cut is
# aligned at the paper edge, long before the blade reaches anything to follow.
# One ink, two treatments — solid where the line crosses bare margin, dashed
# where it crosses the card block, because the grid has no gutter and a line
# there IS the shared edge of two cards (half of its width survives the cut on
# the card itself, so it stays a dashed hairline). #CCCCCC vanished on the
# yellow header/footer bars the seams run through.
CUT_LINE_COLOR = HexColor('#6E6E6E')
CUT_LINE_WIDTH = 0.4


def _ty(t_mm: float) -> float:
    """Convert 'mm from the top edge' to a PDF y coordinate."""
    return BADGE_HEIGHT - t_mm * mm


class BadgeGenerator:
    """
    Generates printable Para-ID badges in PDF format.
    """

    @staticmethod
    def generate(profile) -> bytes:
        """
        Generate a single PDF badge for the given profile (54x86mm).

        Args:
            profile: Profile model instance

        Returns:
            PDF file as bytes
        """
        buffer = io.BytesIO()

        # Create PDF canvas with proper page size
        c = canvas.Canvas(buffer, pagesize=(BADGE_WIDTH, BADGE_HEIGHT))

        # Set PDF metadata to hint at actual size printing
        c.setAuthor("Parahub")
        c.setTitle(f"Para-ID Badge - {profile.display_name or profile.local_name}")
        c.setSubject("54x86mm ID Badge - Print at actual size (no scaling)")

        # Draw single badge at origin (0, 0)
        BadgeGenerator._draw_single_badge(c, profile)

        c.save()
        buffer.seek(0)
        return buffer.getvalue()

    @staticmethod
    def render_png(profile, dpi: int = 150) -> bytes:
        """
        Render the single badge as a PNG (for on-screen preview).

        Uses poppler's pdftoppm so the preview is pixel-identical to the
        printable PDF instead of a second hand-drawn implementation.
        """
        import subprocess
        import tempfile

        pdf_bytes = BadgeGenerator.generate(profile)
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = os.path.join(tmp_dir, 'badge.pdf')
            out_root = os.path.join(tmp_dir, 'badge')
            with open(pdf_path, 'wb') as f:
                f.write(pdf_bytes)
            subprocess.run(
                ['pdftoppm', '-png', '-singlefile', '-r', str(dpi), pdf_path, out_root],
                check=True, timeout=30,
            )
            with open(out_root + '.png', 'rb') as f:
                return f.read()

    @staticmethod
    def generate_batch(profile) -> bytes:
        """
        Generate A4 PDF with 9 badges (3x3 grid) for economical printing.

        The badges are arranged in a 3x3 grid centered on A4 paper.
        Cut lines are drawn between cards for easy cutting with scissors.

        Args:
            profile: Profile model instance

        Returns:
            PDF file as bytes (A4 size)
        """
        buffer = io.BytesIO()

        # Create A4 canvas
        c = canvas.Canvas(buffer, pagesize=A4)

        # Set PDF metadata
        c.setAuthor("Parahub")
        c.setTitle(f"Para-ID Batch - {profile.display_name or profile.local_name}")
        c.setSubject("9x Para-ID badges on A4 - Print at actual size (no scaling)")

        # Draw 3x3 grid of badges
        for row in range(BATCH_ROWS):
            for col in range(BATCH_COLS):
                # Calculate position (PDF Y is from bottom)
                x_off = BATCH_MARGIN_X + col * BADGE_WIDTH
                # Row 0 is top, but PDF Y starts from bottom
                y_off = A4_HEIGHT - BATCH_MARGIN_Y - (row + 1) * BADGE_HEIGHT

                # Save state, translate, draw, restore
                c.saveState()
                c.translate(x_off, y_off)
                BadgeGenerator._draw_single_badge(c, profile)
                c.restoreState()

        # Draw cut lines
        BadgeGenerator._draw_cut_lines(c)

        c.save()
        buffer.seek(0)
        return buffer.getvalue()

    @staticmethod
    def _draw_cut_lines(c: canvas.Canvas):
        """Draw cut guides for every card edge on the A4 batch page.

        Four horizontal and four vertical guides — the block's outer edges
        included, so the trim cuts are guided too — each running from paper
        edge to paper edge.
        """
        block_x0 = BATCH_MARGIN_X
        block_x1 = BATCH_MARGIN_X + BATCH_COLS * BADGE_WIDTH
        block_y1 = A4_HEIGHT - BATCH_MARGIN_Y
        block_y0 = block_y1 - BATCH_ROWS * BADGE_HEIGHT

        xs = [block_x0 + col * BADGE_WIDTH for col in range(BATCH_COLS + 1)]
        ys = [block_y1 - row * BADGE_HEIGHT for row in range(BATCH_ROWS + 1)]

        c.setStrokeColor(CUT_LINE_COLOR)
        c.setLineWidth(CUT_LINE_WIDTH)

        # Margins: solid, out to the paper edge — the part scissors line up on
        for y in ys:
            c.line(0, y, block_x0, y)
            c.line(block_x1, y, A4_WIDTH, y)
        for x in xs:
            c.line(x, 0, x, block_y0)
            c.line(x, block_y1, x, A4_HEIGHT)

        # Across the card block: dashed, half the ink on printed artwork
        c.setDash([2.5, 2.5])
        for y in ys:
            c.line(block_x0, y, block_x1, y)
        for x in xs:
            c.line(x, block_y0, x, block_y1)

        c.setDash([])  # Reset to solid

    @staticmethod
    def _wot_count(profile) -> int:
        """Active peer verification count for the profile."""
        from identity.models import Verification
        return Verification.objects.filter(
            verified_profile=profile,
            is_active=True
        ).count()

    @staticmethod
    def _association_level(profile):
        """Statutory membership category in the governing association
        (FUNDADOR / EFETIVO / APOIANTE), or None.

        PERSONAL cards only: founders are a handful of people, so the
        category on a pseudonymous card would narrow the holder's identity.
        An unset membership_level prints nothing — a data gap is not a
        category.
        """
        if getattr(profile, 'profile_type', 'PERSONAL') != 'PERSONAL':
            return None
        try:
            from constance import config
            from geo.models import EstablishmentMembership
            level = EstablishmentMembership.objects.filter(
                profile=profile,
                establishment__slug=config.GOVERNING_ASSOCIATION_SLUG,
            ).values_list('membership_level', flat=True).first()
            return level.upper() if level else None
        except Exception as e:
            logger.warning(f"Could not resolve association level for badge: {e}")
            return None

    @staticmethod
    def _draw_single_badge(c: canvas.Canvas, profile):
        """
        Draw a complete badge at the current canvas origin.

        This method assumes the canvas coordinate system has been translated
        so that (0, 0) is at the bottom-left corner of where the badge should be.
        """
        # Get profile type color
        profile_type = getattr(profile, 'profile_type', 'PERSONAL')
        header_color = PROFILE_COLORS.get(profile_type, PRIMARY_COLOR)

        wot_count = BadgeGenerator._wot_count(profile)
        is_wot_verified = getattr(profile, 'is_verified_wot', False) or wot_count >= 3
        association_level = BadgeGenerator._association_level(profile)

        # Document grid (top to bottom):
        # - Header bar with logo + document-type designation: 10mm
        # - Name block: labeled name (humanist) + handle (OCR-B), full width
        # - Photo zone 18x24mm RIGHT + labeled field column LEFT
        #   (verifications / member since / issued / PGP fingerprint)
        # - 15mm QR bottom-left
        # - Footer: parahub.io
        # - WoT seal (3+): 40mm carimbo-scale ink stamped last, over everything
        BadgeGenerator._draw_background(c)
        BadgeGenerator._draw_calcada_pattern(c)
        BadgeGenerator._draw_header(c, header_color, profile_type)
        BadgeGenerator._draw_name(c, profile)
        BadgeGenerator._draw_avatar(c, profile, header_color)
        BadgeGenerator._draw_fields(c, profile, wot_count, is_wot_verified,
                                    association_level)
        BadgeGenerator._draw_pgp(c, profile)
        BadgeGenerator._draw_qr_code(c, profile)
        BadgeGenerator._draw_footer(c, header_color)
        if is_wot_verified:
            BadgeGenerator._draw_wot_seal(c)

    @staticmethod
    def _draw_background(c: canvas.Canvas):
        """Draw badge background with rounded corners and calçada portuguesa pattern."""
        corner_radius = 3 * mm  # Standard ID card radius

        # White background with rounded corners
        c.setFillColor(BG_COLOR)
        c.roundRect(0, 0, BADGE_WIDTH, BADGE_HEIGHT, corner_radius, fill=1, stroke=0)


        # Light border with rounded corners
        c.setStrokeColor(HexColor('#E5E5E5'))
        c.setLineWidth(0.5)
        c.roundRect(0.5 * mm, 0.5 * mm, BADGE_WIDTH - 1 * mm, BADGE_HEIGHT - 1 * mm, corner_radius, fill=0, stroke=1)

    @staticmethod
    def _draw_calcada_pattern(c: canvas.Canvas):
        """Draw calçada portuguesa 'Mar Largo' wave pattern as subtle watermark.

        The Mar Largo (Wide Sea) pattern consists of flowing wave curves,
        inspired by Portuguese cobblestone pavement art found on the
        Copacabana boardwalk and throughout Portugal.
        """
        import math

        # Clip to the card shape: waves are drawn past the edges for seamless
        # phase, and on the A4 batch page nothing else crops them
        c.saveState()
        clip = c.beginPath()
        clip.roundRect(0, 0, BADGE_WIDTH, BADGE_HEIGHT, 3 * mm)
        c.clipPath(clip, fill=0, stroke=0)

        # Very subtle gray for watermark effect
        pattern_color = HexColor('#F0F0F0')
        c.setStrokeColor(pattern_color)
        c.setLineWidth(0.4)

        # Wave parameters
        wave_height = 3 * mm  # Amplitude of waves
        wave_length = 12 * mm  # Wavelength
        row_spacing = 6 * mm  # Vertical spacing between wave rows

        # Draw waves from bottom to top, avoiding header and footer
        start_y = 6 * mm  # Above footer
        end_y = BADGE_HEIGHT - 12 * mm  # Below header

        row = 0
        y = start_y
        while y < end_y:
            # Alternate wave phase for each row (creates interlocking pattern)
            phase_offset = (row % 2) * (wave_length / 2)

            # Draw one wave row using bezier curves
            p = c.beginPath()
            x = -wave_length + phase_offset
            p.moveTo(x, y)

            while x < BADGE_WIDTH + wave_length:
                # Control points for smooth sine-like wave
                cp1_x = x + wave_length / 4
                cp1_y = y + wave_height
                cp2_x = x + wave_length / 2
                cp2_y = y + wave_height
                end_x = x + wave_length / 2
                end_y_pt = y

                # First half of wave (going up)
                p.curveTo(cp1_x, cp1_y, cp2_x, cp2_y, end_x, y + wave_height / 2)

                # Second half of wave (going down)
                cp1_x = x + wave_length * 3 / 4
                cp1_y = y
                cp2_x = x + wave_length
                cp2_y = y
                p.curveTo(cp1_x, cp1_y - wave_height / 2, cp2_x, y, x + wave_length, y)

                x += wave_length

            c.drawPath(p, fill=0, stroke=1)
            y += row_spacing
            row += 1

        c.restoreState()

    @staticmethod
    def _draw_header(c: canvas.Canvas, header_color, profile_type: str):
        """Draw header bar with logo and profile type indicator."""
        header_height = 10 * mm
        corner_radius = 3 * mm
        font_name = 'OCRB' if OCRB_AVAILABLE else 'Helvetica-Bold'

        # Colored header bar with rounded top corners
        # Draw using path to have only top corners rounded
        c.setFillColor(header_color)
        p = c.beginPath()
        # Start bottom-left
        p.moveTo(0, BADGE_HEIGHT - header_height)
        # Line to bottom-right
        p.lineTo(BADGE_WIDTH, BADGE_HEIGHT - header_height)
        # Line to top-right (before curve)
        p.lineTo(BADGE_WIDTH, BADGE_HEIGHT - corner_radius)
        # Arc top-right corner
        p.arcTo(BADGE_WIDTH - corner_radius * 2, BADGE_HEIGHT - corner_radius * 2,
                BADGE_WIDTH, BADGE_HEIGHT, 0, 90)
        # Line to top-left (before curve)
        p.lineTo(corner_radius, BADGE_HEIGHT)
        # Arc top-left corner
        p.arcTo(0, BADGE_HEIGHT - corner_radius * 2,
                corner_radius * 2, BADGE_HEIGHT, 90, 90)
        # Close path
        p.close()
        c.drawPath(p, fill=1, stroke=0)

        # Draw PNG logo on the left
        logo_size = 7 * mm
        logo_x = 3 * mm
        logo_y = BADGE_HEIGHT - header_height + (header_height - logo_size) / 2

        try:
            if os.path.exists(LOGO_PATH):
                img_reader = ImageReader(LOGO_PATH)
                c.drawImage(img_reader, logo_x, logo_y, width=logo_size, height=logo_size,
                           preserveAspectRatio=True, mask='auto')
        except Exception as e:
            logger.warning(f"Could not load logo: {e}")

        # PARAHUB text (centered, after logo space), lifted to make room for
        # the document-type designation underneath
        c.setFillColor(black)
        c.setFont(font_name, 12)
        text = "PARAHUB"
        text_width = c.stringWidth(text, font_name, 12)
        # Center text in remaining space (after logo)
        text_area_start = logo_x + logo_size + 2 * mm
        text_area_width = BADGE_WIDTH - text_area_start - 3 * mm
        x = text_area_start + (text_area_width - text_width) / 2
        y = BADGE_HEIGHT - header_height / 2 - 2
        c.drawString(x, y, text)

        # Document-type designation: every document states what it is —
        # and a member card that says so cannot be read as a government ID
        designation = "CARTÃO DE MEMBRO · MEMBER CARD"
        des_font = 'BadgeSans' if HUMAN_AVAILABLE else 'Helvetica'
        des_size, des_charspace = 3.5, 0.5
        des_width = (c.stringWidth(designation, des_font, des_size)
                     + des_charspace * (len(designation) - 1))
        t = c.beginText()
        t.setFont(des_font, des_size)
        t.setCharSpace(des_charspace)
        t.setTextOrigin(text_area_start + (text_area_width - des_width) / 2,
                        BADGE_HEIGHT - header_height + 1.6 * mm)
        t.textOut(designation)
        # Tc is content-stream state, NOT scoped to the text object: without
        # this reset every later drawString on the page inherits +0.5pt/char
        # and renders wider than stringWidth computed
        t.setCharSpace(0)
        c.drawText(t)

        # Profile type label on the right (small)
        if profile_type != 'PERSONAL':
            type_labels = {
                'PSEUDONYMOUS': 'ANON',
            }
            type_label = type_labels.get(profile_type, '')
            if type_label:
                label_font = 'BadgeSans' if HUMAN_AVAILABLE else 'Helvetica'
                c.setFont(label_font, 5)
                c.setFillColor(black)
                label_width = c.stringWidth(type_label, label_font, 5)
                c.drawString(BADGE_WIDTH - label_width - 2 * mm, BADGE_HEIGHT - 4 * mm, type_label)

    @staticmethod
    def _draw_field_label(c: canvas.Canvas, x: float, t_mm: float,
                          label_pt: str, label_en: str):
        """Two-line bilingual field label (pt over italic en), left-aligned —
        the Cartão de Cidadão convention: the reader, not the holder, picks
        the language."""
        pt_font = 'BadgeSans' if HUMAN_AVAILABLE else 'Helvetica'
        en_font = 'BadgeSans-Italic' if HUMAN_AVAILABLE else 'Helvetica-Oblique'
        c.setFillColor(LABEL_COLOR)
        c.setFont(pt_font, LABEL_SIZE)
        c.drawString(x, _ty(t_mm), label_pt)
        c.setFont(en_font, LABEL_EN_SIZE)
        c.drawString(x, _ty(t_mm + 1.5), label_en)

    @staticmethod
    def _draw_avatar(c: canvas.Canvas, profile, header_color):
        """Draw avatar/photo area, top-right (Bilhete de Identidade style).

        If id_photo exists, draw the actual photo with a hairline frame.
        Otherwise, draw colored circle with initials (fallback).
        Color matches header (profile type).
        """
        from django.conf import settings

        photo_y = _ty(PHOTO_TOP) - PHOTO_H

        # Try to use id_photo if available (verification is advisory, not required)
        id_photo_used = False
        if hasattr(profile, 'id_photo') and profile.id_photo:
            try:
                # Get the file path
                photo_path = os.path.join(settings.MEDIA_ROOT, profile.id_photo.name)
                if os.path.exists(photo_path):
                    # Cover-crop to the 3:4 window like a real ID card: letterboxing
                    # (preserveAspectRatio) rendered a square upload at 18x18 of the
                    # 18x24 zone, visibly shrinking the face
                    from PIL import Image as PILImage
                    from PIL import ImageOps
                    img = PILImage.open(photo_path)
                    img = ImageOps.exif_transpose(img)  # phone photos carry rotation in EXIF
                    target = PHOTO_W / PHOTO_H
                    w, h = img.size
                    if w / h > target:
                        # Too wide: crop the sides, faces are centered
                        new_w = round(h * target)
                        x0 = (w - new_w) // 2
                        img = img.crop((x0, 0, x0 + new_w, h))
                    elif w / h < target:
                        # Too tall: keep the top, faces sit high in a portrait
                        img = img.crop((0, 0, w, round(w / target)))
                    buf = io.BytesIO()
                    img.convert('RGB').save(buf, format='JPEG', quality=92)
                    buf.seek(0)
                    c.drawImage(ImageReader(buf), PHOTO_X, photo_y,
                                width=PHOTO_W, height=PHOTO_H)
                    # Hairline frame like a glued-in document photo
                    c.setStrokeColor(HexColor('#D5D5D5'))
                    c.setLineWidth(0.4)
                    c.rect(PHOTO_X, photo_y, PHOTO_W, PHOTO_H, fill=0, stroke=1)
                    id_photo_used = True
            except Exception as e:
                logger.warning(f"Failed to load id_photo for badge: {e}")

        # Fallback: colored circle with initials (color matches profile type),
        # centered in the photo zone
        if not id_photo_used:
            avatar_diameter = 18 * mm
            center_x = PHOTO_X + PHOTO_W / 2
            center_y = photo_y + PHOTO_H / 2

            # Circle with profile type color
            c.setFillColor(header_color)
            c.circle(center_x, center_y, avatar_diameter / 2, fill=1, stroke=0)

            # Initials (2 letters) — human field, humanist face
            initials = BadgeGenerator._get_initials(profile.display_name, profile.local_name)
            font_name = BadgeGenerator._human_font(initials, bold=True)
            c.setFillColor(black)
            c.setFont(font_name, 13)
            text_width = c.stringWidth(initials, font_name, 13)
            c.drawString(center_x - text_width / 2, center_y - 4.5, initials)

    @staticmethod
    def _text_font(text: str, bold: bool = False) -> str:
        """Pick a machine-data font that can draw every character.

        OCR-B when it covers the text; DejaVu Sans Mono for accented and
        non-Latin strings OCR-B would silently drop.
        """
        if OCRB_AVAILABLE and all(ord(ch) in OCRB_CHARS for ch in text):
            return 'OCRB'
        if FALLBACK_AVAILABLE:
            return 'BadgeMono-Bold' if bold else 'BadgeMono'
        return 'Helvetica-Bold' if bold else 'Helvetica'

    @staticmethod
    def _human_font(text: str, bold: bool = False) -> str:
        """Pick a humanist font that can draw every character.

        Liberation Sans covers Latin Extended + Cyrillic; DejaVu Sans covers
        Greek, Armenian, Georgian and more (reportlab drops missing glyphs
        silently, so coverage is checked per string).
        """
        if HUMAN_AVAILABLE:
            if all(ord(ch) in HUMAN_CHARS for ch in text):
                return 'BadgeSans-Bold' if bold else 'BadgeSans'
            return 'BadgeSansWide-Bold' if bold else 'BadgeSansWide'
        return 'Helvetica-Bold' if bold else 'Helvetica'

    @staticmethod
    def _get_initials(display_name: str, local_name: str) -> str:
        """Extract initials from name (2 letters)."""
        name = display_name or local_name or "?"

        # Split by spaces, dots, underscores
        import re
        parts = re.split(r'[\s._-]+', name)
        parts = [p for p in parts if p]  # Remove empty

        if len(parts) >= 2:
            return f"{parts[0][0]}{parts[1][0]}".upper()
        elif len(parts) == 1 and len(parts[0]) >= 2:
            return parts[0][:2].upper()
        elif len(parts) == 1:
            return parts[0][0].upper()
        return "?"

    _seal_reader = None

    @classmethod
    def _get_seal_reader(cls):
        """The seal master is 2000px; embedding it verbatim put ~360KB into
        every badge PDF. Downsample once to 800px (~500dpi at the 40mm print
        size) and cache the reader across calls."""
        if cls._seal_reader is None:
            from PIL import Image as PILImage
            img = PILImage.open(WOT_SEAL_PATH)
            img = img.resize((800, 800), PILImage.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)
            cls._seal_reader = ImageReader(buf)
        return cls._seal_reader

    @staticmethod
    def _draw_wot_seal(c: canvas.Canvas):
        """Round community seal for WoT-verified profiles (3+ peer verifications).

        The asset shares the carimbo's frame and typography (generated by
        scripts/gen_wot_seal.py, same machinery as scripts/gen_stamp.py) so the
        two stamps read as one family — but it is deliberately NOT the carimbo:
        no NIPC, no legal name. It marks peer verification, not an act of the
        association, and the QR code remains the only real proof.

        Stamped at real carimbo scale (40mm) as the LAST draw call: real ink
        sits on top of everything printed, covers the photo's lower corner
        (ink bridging photo and card is the classic anti-swap mark — the old
        Bilhete de Identidade carried its official mark over the photo the
        same way) and bleeds off the right edge like a hand-placed stamp.
        """
        if not os.path.exists(WOT_SEAL_PATH):
            logger.warning(
                f"WoT seal asset missing at {WOT_SEAL_PATH} — "
                "run scripts/gen_wot_seal.py"
            )
            return

        c.saveState()
        # Clip to the card shape: the stamp bleeds off the card edge, and on
        # the A4 batch page it must not cross into the neighbouring card
        clip = c.beginPath()
        clip.roundRect(0, 0, BADGE_WIDTH, BADGE_HEIGHT, 3 * mm)
        c.clipPath(clip, fill=0, stroke=0)

        c.translate(SEAL_CX * mm, _ty(SEAL_CY))
        c.rotate(SEAL_ROTATION)
        # Stamp-ink feel: translucent so the print shows through the ink
        c.setFillAlpha(SEAL_ALPHA)
        c.drawImage(BadgeGenerator._get_seal_reader(),
                    -SEAL_SIZE / 2, -SEAL_SIZE / 2,
                    width=SEAL_SIZE, height=SEAL_SIZE, mask='auto')
        c.restoreState()

    @staticmethod
    def _draw_name(c: canvas.Canvas, profile):
        """Labeled name block under the header, full width: passport data
        pages open with the holder's name, and the top of the reading order
        is what gives it primacy over the machine elements below."""
        BadgeGenerator._draw_field_label(c, MARGIN_X, 13.4, "NOME", "NAME")

        # Name in a humanist face — the single strongest 'document, not
        # sci-fi prop' cue on the card
        name = profile.display_name or profile.local_name or "Anonymous"
        font_name = BadgeGenerator._human_font(name, bold=True)
        max_width = BADGE_WIDTH - 2 * MARGIN_X

        font_size = 11.5
        while c.stringWidth(name, font_name, font_size) > max_width and font_size > 8:
            font_size -= 0.5
        while c.stringWidth(name, font_name, font_size) > max_width and len(name) > 3:
            name = name[:-4] + "..."

        c.setFont(font_name, font_size)
        c.setFillColor(TEXT_COLOR)
        c.drawString(MARGIN_X, _ty(19.2), name)

        # HNA below the name (machine string, OCR-B). local_name allows up to
        # 100 chars while ~30 fit at 6.5pt: shrink to fit first, truncate only
        # past the 5pt readability floor
        hna = getattr(profile, 'hna', None) or f"{profile.local_name}@parahub.io"
        font_name_regular = BadgeGenerator._text_font(hna)

        hna_size = 6.5
        while c.stringWidth(hna, font_name_regular, hna_size) > max_width and hna_size > 5:
            hna_size -= 0.5
        while c.stringWidth(hna, font_name_regular, hna_size) > max_width and len(hna) > 3:
            hna = hna[:-4] + "..."

        c.setFont(font_name_regular, hna_size)
        c.setFillColor(MUTED_COLOR)
        c.drawString(MARGIN_X, _ty(22.6), hna)

    @staticmethod
    def _draw_fields(c: canvas.Canvas, profile, wot_count: int, is_verified: bool,
                     association_level=None):
        """Labeled field column right of the photo: verification count,
        member-since year, issue date.

        The verification count is a labeled document field on purpose — the
        old 3-of-5 dot gauge read as a citizen-score meter, which is the
        opposite of what a web of trust is. A number under a bilingual label
        states a fact without ranking anyone.
        """
        font_name = 'OCRB' if OCRB_AVAILABLE else 'Helvetica'
        value_font = 'OCRB' if OCRB_AVAILABLE else 'Helvetica'

        fields = []
        # Verification count: indigo (the seal's ink) once the seal threshold
        # is met, muted gray below it — the gray count is the only status cue
        # on unverified cards, which is what keeps the seal meaningful
        count_color = WOT_COLOR if is_verified else MUTED_COLOR
        fields.append((("VERIFICAÇÕES", "VERIFICATIONS"), str(wot_count), count_color))

        created_at = getattr(profile, 'created_at', None)
        if created_at:
            fields.append((("MEMBRO DESDE", "MEMBER SINCE"), str(created_at.year), MUTED_COLOR))
        fields.append((("EMITIDO", "ISSUED"), date.today().isoformat(), MUTED_COLOR))

        t = 27.5
        for (label_pt, label_en), value, color in fields:
            BadgeGenerator._draw_field_label(c, FIELDS_X, t, label_pt, label_en)
            c.setFont(value_font, VALUE_SIZE)
            c.setFillColor(color)
            c.drawString(FIELDS_X, _ty(t + 4.6), value)
            t += 8.0

        # Association membership category shares the first row with the
        # verification count — the Cartão de Cidadão convention of several
        # fields per row, and the first row is the only zone whose right
        # half clears both the photo and the seal ink. A statutory fact in
        # muted ink, not a status cue: the header keeps its profile-type
        # color, no separate "VIP" treatment.
        if association_level:
            assoc_x = 18 * mm
            BadgeGenerator._draw_field_label(c, assoc_x, 27.5,
                                             "ASSOCIAÇÃO", "ASSOCIATION")
            c.setFont(value_font, VALUE_SIZE)
            c.setFillColor(MUTED_COLOR)
            c.drawString(assoc_x, _ty(27.5 + 4.6), association_level)

    @staticmethod
    def _draw_pgp(c: canvas.Canvas, profile):
        """PGP fingerprint suffix as a labeled field continuing the left column.
        Two lines of 2x4 hex groups — the last 64 bits, a deliberate pointer
        to the key rather than a verification primitive (64-bit IDs are
        forgeable with effort): full-fingerprint verification happens against
        the live profile the QR resolves to. Two short lines stay clear of
        the seal ink and compare easily by eye. Always printed when a key
        exists — absence of a key is a fact, not a setting.
        """
        fp = getattr(profile, 'pgp_fingerprint', None)
        if not fp or len(fp) < 16:
            return

        BadgeGenerator._draw_field_label(c, MARGIN_X, 51.5,
                                         "IMPRESSÃO PGP", "PGP FINGERPRINT")
        short_fp = fp[-16:]
        groups = [short_fp[i:i+4] for i in range(0, 16, 4)]
        font_name = 'OCRB' if OCRB_AVAILABLE else 'Helvetica'
        c.setFont(font_name, VALUE_SIZE)
        c.setFillColor(MUTED_COLOR)
        c.drawString(MARGIN_X, _ty(56.1), ' '.join(groups[:2]))
        c.drawString(MARGIN_X, _ty(59.3), ' '.join(groups[2:]))

    @staticmethod
    def _draw_qr_code(c: canvas.Canvas, profile):
        """QR code linking to the public profile — bottom-left corner, small,
        the way machine-readable marks sit on documents. The name owns the
        card; the QR stays the proof, not the centrepiece."""
        qr_x = MARGIN_X
        qr_y = _ty(62) - QR_SIZE

        # Generate QR code
        profile_url = f"https://parahub.io/@{profile.local_name}"
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=3,  # near the spec's 4-module quiet zone; the watermark
                       # waves run close to the QR edge, so don't rely on
                       # the white card alone
        )
        qr.add_data(profile_url)
        qr.make(fit=True)

        # Create image
        qr_img = qr.make_image(fill_color="black", back_color="white")

        # Convert to ImageReader
        img_buffer = io.BytesIO()
        qr_img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        img_reader = ImageReader(img_buffer)

        # Draw QR code
        c.drawImage(img_reader, qr_x, qr_y, width=QR_SIZE, height=QR_SIZE)

    @staticmethod
    def _draw_footer(c: canvas.Canvas, footer_color):
        """Draw footer with thin colored bar and domain."""
        footer_height = 4 * mm
        corner_radius = 3 * mm

        # Footer bar with rounded bottom corners (mirrors the header path —
        # nothing clips in PDF, a plain rect would stick out of the card shape)
        c.setFillColor(footer_color)
        p = c.beginPath()
        p.moveTo(0, footer_height)
        p.lineTo(BADGE_WIDTH, footer_height)
        p.lineTo(BADGE_WIDTH, corner_radius)
        # Arc bottom-right corner
        p.arcTo(BADGE_WIDTH - corner_radius * 2, 0,
                BADGE_WIDTH, corner_radius * 2, 0, -90)
        p.lineTo(corner_radius, 0)
        # Arc bottom-left corner
        p.arcTo(0, 0, corner_radius * 2, corner_radius * 2, -90, -90)
        p.close()
        c.drawPath(p, fill=1, stroke=0)

        # Domain text on footer
        font_name = 'OCRB' if OCRB_AVAILABLE else 'Helvetica'
        c.setFont(font_name, 5)
        c.setFillColor(black)
        text = "parahub.io"
        text_width = c.stringWidth(text, font_name, 5)
        c.drawString((BADGE_WIDTH - text_width) / 2, 1 * mm, text)
