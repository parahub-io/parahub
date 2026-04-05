"""
Para-ID Badge Generator - PDF generation for printable member badges

Generates a 54x86mm vertical badge suitable for lanyard display.
Contains: logo, avatar (initials), name, WoT status, QR code, ID, PGP fingerprint.

Features:
- SVG logo in header
- WoT verification badge with member count
- Color-coded by profile type (Personal/Organization/Pseudonymous)
- Member since date
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

# Badge dimensions (vertical ID-1 format)
BADGE_WIDTH = 54 * mm
BADGE_HEIGHT = 86 * mm

# Colors by profile type
PROFILE_COLORS = {
    'PERSONAL': HexColor('#FACC15'),      # Yellow - default
    'PSEUDONYMOUS': HexColor('#6B7280'),  # Gray - pseudonymous
}
PRIMARY_COLOR = PROFILE_COLORS['PERSONAL']  # Default fallback
TEXT_COLOR = black
MUTED_COLOR = HexColor('#666666')
BG_COLOR = white
WOT_COLOR = HexColor('#1E3A8A')  # Dark blue (Portuguese document style)
WOT_UNVERIFIED_COLOR = HexColor('#9CA3AF')  # Gray for unverified

# Logo path (PNG version for PDF embedding)
LOGO_PATH = '/opt/parahub/parahub/static/logo.png'

# Batch mode constants (A4: 210x297mm, 3x3 grid)
A4_WIDTH, A4_HEIGHT = A4  # 595.27 x 841.89 points (210x297mm)
BATCH_COLS = 3
BATCH_ROWS = 3
# Center the 3x3 grid on A4
# Total cards width: 54mm * 3 = 162mm, A4 width: 210mm, margin: (210-162)/2 = 24mm
# Total cards height: 86mm * 3 = 258mm, A4 height: 297mm, margin: (297-258)/2 = 19.5mm
BATCH_MARGIN_X = 24 * mm
BATCH_MARGIN_Y = 19.5 * mm
CUT_LINE_COLOR = HexColor('#CCCCCC')


class BadgeGenerator:
    """
    Generates printable Para-ID badges in PDF format.
    """

    @staticmethod
    def generate(
        profile,
        include_birth_date: bool = True,
        include_pgp: bool = True,
    ) -> bytes:
        """
        Generate a single PDF badge for the given profile (54x86mm).

        Args:
            profile: Profile model instance
            include_birth_date: Whether to include birth date (if available)
            include_pgp: Whether to include PGP fingerprint (if available)

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
        BadgeGenerator._draw_single_badge(c, profile, include_pgp)

        c.save()
        buffer.seek(0)
        return buffer.getvalue()

    @staticmethod
    def generate_batch(
        profile,
        include_pgp: bool = True,
    ) -> bytes:
        """
        Generate A4 PDF with 9 badges (3x3 grid) for economical printing.

        The badges are arranged in a 3x3 grid centered on A4 paper.
        Cut lines are drawn between cards for easy cutting with scissors.

        Args:
            profile: Profile model instance
            include_pgp: Whether to include PGP fingerprint (if available)

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
                BadgeGenerator._draw_single_badge(c, profile, include_pgp)
                c.restoreState()

        # Draw cut lines
        BadgeGenerator._draw_cut_lines(c)

        c.save()
        buffer.seek(0)
        return buffer.getvalue()

    @staticmethod
    def _draw_cut_lines(c: canvas.Canvas):
        """Draw thin cut lines between badges on A4 batch page."""
        c.setStrokeColor(CUT_LINE_COLOR)
        c.setLineWidth(0.3)
        c.setDash([3, 3])  # Dashed line for easier cutting

        # Vertical lines (between columns)
        for col in range(1, BATCH_COLS):
            x = BATCH_MARGIN_X + col * BADGE_WIDTH
            y_start = BATCH_MARGIN_Y
            y_end = A4_HEIGHT - BATCH_MARGIN_Y
            c.line(x, y_start, x, y_end)

        # Horizontal lines (between rows)
        for row in range(1, BATCH_ROWS):
            y = A4_HEIGHT - BATCH_MARGIN_Y - row * BADGE_HEIGHT
            x_start = BATCH_MARGIN_X
            x_end = BATCH_MARGIN_X + BATCH_COLS * BADGE_WIDTH
            c.line(x_start, y, x_end, y)

        c.setDash([])  # Reset to solid

    @staticmethod
    def _draw_single_badge(c: canvas.Canvas, profile, include_pgp: bool = True):
        """
        Draw a complete badge at the current canvas origin.

        This method assumes the canvas coordinate system has been translated
        so that (0, 0) is at the bottom-left corner of where the badge should be.
        """
        from identity.models import Verification

        # Get profile type color
        profile_type = getattr(profile, 'profile_type', 'PERSONAL')
        header_color = PROFILE_COLORS.get(profile_type, PRIMARY_COLOR)

        # Get WoT verification count
        wot_count = Verification.objects.filter(
            verified_profile=profile,
            is_active=True
        ).count()
        is_wot_verified = getattr(profile, 'is_verified_wot', False)

        # Layout (from top to bottom):
        # - Header bar with logo: 10mm
        # - Avatar: 18mm diameter, centered
        # - WoT badge: verification status
        # - Name: below avatar
        # - QR code: 20mm, centered
        # - Info lines: ID, member since, PGP
        # - Footer: parahub.io

        BadgeGenerator._draw_background(c)
        BadgeGenerator._draw_header(c, header_color, profile_type)
        BadgeGenerator._draw_avatar(c, profile, header_color)
        BadgeGenerator._draw_wot_badge(c, is_wot_verified, wot_count)
        BadgeGenerator._draw_name(c, profile)
        BadgeGenerator._draw_qr_code(c, profile)
        BadgeGenerator._draw_separator(c)
        BadgeGenerator._draw_info(c, profile, include_pgp)
        BadgeGenerator._draw_footer(c, header_color)

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

        # PARAHUB text (centered, after logo space)
        c.setFillColor(black)
        c.setFont(font_name, 12)
        text = "PARAHUB"
        text_width = c.stringWidth(text, font_name, 12)
        # Center text in remaining space (after logo)
        text_area_start = logo_x + logo_size + 2 * mm
        text_area_width = BADGE_WIDTH - text_area_start - 3 * mm
        x = text_area_start + (text_area_width - text_width) / 2
        y = BADGE_HEIGHT - header_height / 2 - 4
        c.drawString(x, y, text)

        # Profile type label on the right (small)
        if profile_type != 'PERSONAL':
            type_labels = {
                'PSEUDONYMOUS': 'ANON',
            }
            type_label = type_labels.get(profile_type, '')
            if type_label:
                c.setFont('Helvetica', 5)
                c.setFillColor(black)
                label_width = c.stringWidth(type_label, 'Helvetica', 5)
                c.drawString(BADGE_WIDTH - label_width - 2 * mm, BADGE_HEIGHT - 4 * mm, type_label)

    @staticmethod
    def _draw_avatar(c: canvas.Canvas, profile, header_color):
        """Draw avatar/photo area.

        If id_photo exists, draw the actual photo.
        Otherwise, draw colored circle with initials (fallback).
        Color matches header (profile type).
        """
        from django.conf import settings

        photo_width = 18 * mm
        photo_height = 24 * mm  # 3:4 ratio for ID photo
        photo_y = BADGE_HEIGHT - 12 * mm - photo_height  # Below header
        center_x = BADGE_WIDTH / 2

        # Try to use id_photo if available (verification is advisory, not required)
        id_photo_used = False
        if hasattr(profile, 'id_photo') and profile.id_photo:
            try:
                # Get the file path
                photo_path = os.path.join(settings.MEDIA_ROOT, profile.id_photo.name)
                if os.path.exists(photo_path):
                    # Load and draw the photo centered
                    img_reader = ImageReader(photo_path)
                    x = center_x - photo_width / 2
                    # Draw with aspect ratio, anchored at center-middle
                    c.drawImage(img_reader, x, photo_y, width=photo_width, height=photo_height,
                               preserveAspectRatio=True, anchor='c', mask='auto')
                    id_photo_used = True
            except Exception as e:
                logger.warning(f"Failed to load id_photo for badge: {e}")

        # Fallback: colored circle with initials (color matches profile type)
        if not id_photo_used:
            avatar_diameter = 18 * mm
            avatar_y = BADGE_HEIGHT - 12 * mm - avatar_diameter
            center_y = avatar_y + avatar_diameter / 2
            font_name = 'OCRB' if OCRB_AVAILABLE else 'Helvetica-Bold'

            # Circle with profile type color
            c.setFillColor(header_color)
            c.circle(center_x, center_y, avatar_diameter / 2, fill=1, stroke=0)

            # Initials (2 letters)
            initials = BadgeGenerator._get_initials(profile.display_name, profile.local_name)
            c.setFillColor(black)
            c.setFont(font_name, 14)
            text_width = c.stringWidth(initials, font_name, 14)
            c.drawString(center_x - text_width / 2, center_y - 5, initials)

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

    @staticmethod
    def _draw_wot_badge(c: canvas.Canvas, is_verified: bool, wot_count: int):
        """Draw WoT verification indicator using graphical dots (Portuguese document style).

        Format: ●●●○○ for 0-5 verifications, ●●●●● +N for 6+
        Dark blue color matching official document aesthetics.
        Draws actual circles instead of Unicode characters for font compatibility.
        """
        badge_y = BADGE_HEIGHT - 39 * mm  # Below photo area (36mm) + 3mm gap
        center_x = BADGE_WIDTH / 2

        # Determine colors based on verification status
        if is_verified or wot_count >= 3:
            filled_color = WOT_COLOR
            empty_color = HexColor('#C5D4E8')  # Light blue for empty dots
        else:
            filled_color = WOT_UNVERIFIED_COLOR
            empty_color = HexColor('#E5E5E5')  # Light gray for empty dots

        # Dot parameters
        dot_radius = 1.2 * mm
        dot_spacing = 3.2 * mm  # Center-to-center distance
        max_dots = 5

        # Calculate total width
        if wot_count <= max_dots:
            total_width = max_dots * dot_spacing - dot_spacing + dot_radius * 2
        else:
            # 5 dots + space + number
            font_name = 'Helvetica-Bold'
            font_size = 8
            number_text = f"+{wot_count - max_dots}"
            number_width = c.stringWidth(number_text, font_name, font_size)
            total_width = max_dots * dot_spacing + 1.5 * mm + number_width

        start_x = center_x - total_width / 2 + dot_radius

        # Draw dots
        for i in range(max_dots):
            x = start_x + i * dot_spacing
            y = badge_y

            if i < wot_count:
                # Filled dot
                c.setFillColor(filled_color)
                c.circle(x, y, dot_radius, fill=1, stroke=0)
            else:
                # Empty dot (ring)
                c.setStrokeColor(empty_color)
                c.setLineWidth(0.4)
                c.setFillColor(BG_COLOR)
                c.circle(x, y, dot_radius, fill=1, stroke=1)

        # If count > 5, add number after dots
        if wot_count > max_dots:
            font_name = 'Helvetica-Bold'
            font_size = 8
            c.setFont(font_name, font_size)
            c.setFillColor(filled_color)
            number_text = f"+{wot_count - max_dots}"
            number_x = start_x + max_dots * dot_spacing + 0.5 * mm
            c.drawString(number_x, badge_y - 2.5, number_text)

    @staticmethod
    def _draw_name(c: canvas.Canvas, profile):
        """Draw display name and HNA."""
        font_name = 'OCRB' if OCRB_AVAILABLE else 'Helvetica-Bold'
        font_name_regular = 'OCRB' if OCRB_AVAILABLE else 'Helvetica'

        # Display name (main) - positioned below WoT badge
        name = profile.display_name or profile.local_name or "Anonymous"
        y_name = BADGE_HEIGHT - 44 * mm  # Below WoT dots (39mm) + 5mm gap

        font_size = 11
        c.setFont(font_name, font_size)
        max_width = BADGE_WIDTH - 6 * mm

        while c.stringWidth(name, font_name, font_size) > max_width and len(name) > 3:
            name = name[:-4] + "..."

        text_width = c.stringWidth(name, font_name, font_size)
        x = (BADGE_WIDTH - text_width) / 2
        c.setFillColor(TEXT_COLOR)
        c.drawString(x, y_name, name)

        # HNA (smaller, muted, below name)
        hna = getattr(profile, 'hna', None) or f"{profile.local_name}@parahub.io"
        y_hna = BADGE_HEIGHT - 48 * mm  # Below name (44mm) + 4mm gap

        c.setFont(font_name_regular, 7)
        c.setFillColor(MUTED_COLOR)
        text_width = c.stringWidth(hna, font_name_regular, 7)
        x = (BADGE_WIDTH - text_width) / 2
        c.drawString(x, y_hna, hna)

    @staticmethod
    def _draw_qr_code(c: canvas.Canvas, profile):
        """Draw QR code linking to public profile."""
        qr_size = 18 * mm
        qr_y = BADGE_HEIGHT - 68 * mm  # Below HNA (48mm) + 2mm gap + 18mm QR = top at 50mm

        x = (BADGE_WIDTH - qr_size) / 2

        # Generate QR code
        profile_url = f"https://parahub.io/u/{profile.local_name}"
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=1,
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
        c.drawImage(img_reader, x, qr_y, width=qr_size, height=qr_size)

    @staticmethod
    def _draw_separator(c: canvas.Canvas):
        """Draw a thin separator line between QR code and info section."""
        separator_y = BADGE_HEIGHT - 69.5 * mm  # Just below QR (68mm)
        margin = 8 * mm

        c.setStrokeColor(HexColor('#E5E5E5'))
        c.setLineWidth(0.3)
        c.line(margin, separator_y, BADGE_WIDTH - margin, separator_y)

    @staticmethod
    def _draw_info(c: canvas.Canvas, profile, include_pgp: bool):
        """Draw profile info (ID, member since, PGP) using OCR-B font (EU document style)."""
        y_start = BADGE_HEIGHT - 72 * mm  # Below separator (69.5mm) + 2.5mm gap
        line_height = 3.2 * mm
        font_size = 6  # Slightly larger for OCR-B readability

        # Use OCR-B if available, fallback to Helvetica
        font_name = 'OCRB' if OCRB_AVAILABLE else 'Helvetica'
        c.setFont(font_name, font_size)
        c.setFillColor(MUTED_COLOR)

        lines = []

        # Two dates on one line: registration year | issue date
        # Format: "2025 | 10.12.2025" (member since | document issued)
        created_at = getattr(profile, 'created_at', None)
        issue_date = date.today().strftime('%d.%m.%Y')

        if created_at:
            member_year = created_at.year
            lines.append(f"{member_year}  /  {issue_date}")
        else:
            lines.append(issue_date)

        # PGP fingerprint (last 16 chars, grouped by 4)
        if include_pgp:
            fp = getattr(profile, 'pgp_fingerprint', None)
            if fp and len(fp) >= 16:
                short_fp = fp[-16:]
                formatted_fp = ' '.join([short_fp[i:i+4] for i in range(0, 16, 4)])
                lines.append(f"PGP: {formatted_fp}")

        # Draw lines centered
        for i, line in enumerate(lines):
            text_width = c.stringWidth(line, font_name, font_size)
            x = (BADGE_WIDTH - text_width) / 2
            y = y_start - (i * line_height)
            c.drawString(x, y, line)

    @staticmethod
    def _draw_footer(c: canvas.Canvas, footer_color):
        """Draw footer with thin colored bar and domain."""
        footer_height = 4 * mm

        # Simple rectangle footer (corners will be clipped by background anyway)
        c.setFillColor(footer_color)
        c.rect(0, 0, BADGE_WIDTH, footer_height, fill=1, stroke=0)

        # Domain text on footer
        font_name = 'OCRB' if OCRB_AVAILABLE else 'Helvetica'
        c.setFont(font_name, 5)
        c.setFillColor(black)
        text = "parahub.io"
        text_width = c.stringWidth(text, font_name, 5)
        c.drawString((BADGE_WIDTH - text_width) / 2, 1 * mm, text)
