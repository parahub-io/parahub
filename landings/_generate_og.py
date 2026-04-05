#!/usr/bin/env python3
"""
Generate OG images (1200x630) for all Parahub landing pages.
Output: /opt/parahub/landings/{name}/output/og.png
"""

import math
import os
from PIL import Image, ImageDraw, ImageFont

# Config
WIDTH, HEIGHT = 1200, 630
BG_COLOR = (23, 23, 23)        # #171717
YELLOW = (255, 226, 22)         # #FFE216
WHITE = (255, 255, 255)
GREY = (100, 100, 100)
BASE_DIR = "/opt/parahub/landings"

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

LANDINGS = [
    ("boleias",     "Boleias comunitárias",       0),
    ("condo",       "Gestão de condomínio",        1),
    ("contratos",   "Contratos digitais",          2),
    ("democracia",  "Democracia líquida",          3),
    ("directorio",  "Directório comunitário",      4),
    ("energy",      "Energia solar P2P",           5),
    ("eventos",     "Eventos comunitários",        6),
    ("sos",         "ParaSOS",                     7),
    ("transporte",  "Transportes em tempo real",   8),
    ("troca",       "Troca directa",               9),
]


def draw_gradient_bg(draw: ImageDraw.Draw):
    """Dark background with subtle radial-ish gradient (lighter center)."""
    for y in range(HEIGHT):
        # Vertical gradient: slightly lighter in the middle band
        dist_from_center = abs(y - HEIGHT / 2) / (HEIGHT / 2)
        brightness = int(23 + 12 * (1 - dist_from_center ** 2))
        draw.line([(0, y), (WIDTH, y)], fill=(brightness, brightness, brightness))


def draw_accent_variant(draw: ImageDraw.Draw, variant: int):
    """Draw a distinctive yellow accent shape based on variant index."""
    v = variant % 10

    if v == 0:
        # Top-left corner bracket
        draw.line([(60, 80), (60, 160)], fill=YELLOW, width=4)
        draw.line([(60, 80), (160, 80)], fill=YELLOW, width=4)
        # Bottom-right corner bracket
        draw.line([(WIDTH - 60, HEIGHT - 80), (WIDTH - 60, HEIGHT - 160)], fill=YELLOW, width=4)
        draw.line([(WIDTH - 60, HEIGHT - 80), (WIDTH - 160, HEIGHT - 80)], fill=YELLOW, width=4)

    elif v == 1:
        # Horizontal line across top area
        y_pos = 120
        draw.line([(100, y_pos), (WIDTH - 100, y_pos)], fill=YELLOW, width=3)
        # Small diamond at center of line
        cx = WIDTH // 2
        for dx in range(-8, 9):
            dy = 8 - abs(dx)
            draw.point((cx + dx, y_pos - dy), fill=YELLOW)
            draw.point((cx + dx, y_pos + dy), fill=YELLOW)

    elif v == 2:
        # Diagonal slash from bottom-left to top-right (subtle)
        for i in range(4):
            draw.line([(80 + i, HEIGHT - 100), (200 + i, 100)], fill=(*YELLOW, 180), width=1)
        for i in range(4):
            draw.line([(WIDTH - 200 + i, HEIGHT - 100), (WIDTH - 80 + i, 100)], fill=(*YELLOW, 180), width=1)

    elif v == 3:
        # Three horizontal bars, left-aligned
        for i, length in enumerate([200, 150, 100]):
            y = 100 + i * 20
            draw.line([(80, y), (80 + length, y)], fill=YELLOW, width=3)

    elif v == 4:
        # Circle outline (top-right area)
        cx, cy, r = WIDTH - 150, 150, 60
        for angle in range(360):
            rad = math.radians(angle)
            x = cx + r * math.cos(rad)
            y = cy + r * math.sin(rad)
            draw.ellipse([x - 1, y - 1, x + 1, y + 1], fill=YELLOW)

    elif v == 5:
        # Sun rays pattern (top area, centered)
        cx, cy = WIDTH // 2, 90
        for angle in range(0, 360, 30):
            rad = math.radians(angle)
            x1 = cx + 20 * math.cos(rad)
            y1 = cy + 20 * math.sin(rad)
            x2 = cx + 50 * math.cos(rad)
            y2 = cy + 50 * math.sin(rad)
            draw.line([(x1, y1), (x2, y2)], fill=YELLOW, width=2)

    elif v == 6:
        # Grid of dots (bottom-left)
        for row in range(4):
            for col in range(4):
                x = 80 + col * 18
                y = HEIGHT - 160 + row * 18
                draw.ellipse([x - 3, y - 3, x + 3, y + 3], fill=YELLOW)

    elif v == 7:
        # Bold cross / plus (center-top) — emergency/SOS feel
        cx, cy = WIDTH // 2, 110
        draw.rectangle([cx - 30, cy - 6, cx + 30, cy + 6], fill=YELLOW)
        draw.rectangle([cx - 6, cy - 30, cx + 6, cy + 30], fill=YELLOW)

    elif v == 8:
        # Arrow pointing right (motion feel)
        cx, cy = WIDTH // 2, 100
        draw.line([(cx - 80, cy), (cx + 60, cy)], fill=YELLOW, width=3)
        draw.line([(cx + 40, cy - 20), (cx + 60, cy)], fill=YELLOW, width=3)
        draw.line([(cx + 40, cy + 20), (cx + 60, cy)], fill=YELLOW, width=3)

    elif v == 9:
        # Two interlocking angle brackets (exchange feel)
        draw.line([(WIDTH // 2 - 60, 90), (WIDTH // 2 - 30, 110), (WIDTH // 2 - 60, 130)], fill=YELLOW, width=3)
        draw.line([(WIDTH // 2 + 60, 90), (WIDTH // 2 + 30, 110), (WIDTH // 2 + 60, 130)], fill=YELLOW, width=3)


def draw_bottom_bar(draw: ImageDraw.Draw):
    """Subtle yellow accent line near bottom."""
    y = HEIGHT - 70
    draw.line([(WIDTH // 2 - 60, y), (WIDTH // 2 + 60, y)], fill=YELLOW, width=2)


def generate_og(name: str, title: str, variant: int):
    """Generate a single OG image."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (*BG_COLOR, 255))
    draw = ImageDraw.Draw(img)

    # Background gradient
    draw_gradient_bg(draw)

    # Yellow accent shape (distinctive per landing)
    draw_accent_variant(draw, variant)

    # Title text
    title_font_size = 56 if len(title) <= 22 else 48
    title_font = ImageFont.truetype(FONT_BOLD, title_font_size)

    # Center title vertically (slightly above true center)
    bbox = draw.textbbox((0, 0), title, font=title_font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (WIDTH - tw) // 2
    ty = (HEIGHT - th) // 2 - 20

    # Subtle text shadow
    draw.text((tx + 2, ty + 2), title, fill=(10, 10, 10), font=title_font)
    draw.text((tx, ty), title, fill=WHITE, font=title_font)

    # "parahub.io" branding at bottom
    brand_font = ImageFont.truetype(FONT_REGULAR, 22)
    brand_text = "parahub.io"
    bbox_b = draw.textbbox((0, 0), brand_text, font=brand_font)
    bw = bbox_b[2] - bbox_b[0]
    bx = (WIDTH - bw) // 2
    by = HEIGHT - 52

    # Bottom accent line
    draw_bottom_bar(draw)

    draw.text((bx, by), brand_text, fill=GREY, font=brand_font)

    # Yellow dot before branding
    dot_x = bx - 16
    dot_y = by + 10
    draw.ellipse([dot_x - 4, dot_y - 4, dot_x + 4, dot_y + 4], fill=YELLOW)

    # Save
    output_dir = os.path.join(BASE_DIR, name, "output")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "og.png")
    img.convert("RGB").save(output_path, "PNG", optimize=True)
    print(f"  {output_path} ({os.path.getsize(output_path) // 1024} KB)")


def main():
    print(f"Generating OG images ({WIDTH}x{HEIGHT})...")
    for name, title, variant in LANDINGS:
        generate_og(name, title, variant)
    print("Done.")


if __name__ == "__main__":
    main()
