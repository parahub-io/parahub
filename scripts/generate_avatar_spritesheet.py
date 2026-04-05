#!/usr/bin/env python3
"""
Generate avatar spritesheet using Google Gemini 3 Pro Image Preview.

Creates a complete 10-row × 8-frame spritesheet (80 frames total):
- Rows 1-8: Walk animations in 8 directions (S, SW, W, NW, N, NE, E, SE)
- Row 9:    Jump animation
- Row 10:   Dance animation

USAGE:
    python3 scripts/generate_avatar_spritesheet.py

    Options:
        --output-dir DIR    Output directory (default: /tmp/avatar-sprites)
        --copy-to-frontend  Copy final result to frontend/public/sprites/avatars/
        --avatar-style STR  Style description (default: casual young male)

REQUIREMENTS:
    - Google API key configured in AISettings model
    - pip install google-genai pillow

POST-PROCESSING (if AI output isn't perfect):
    1. Check generated image grid alignment:
       - Should be exactly 8 columns × 10 rows
       - Each frame should be equal size
       - Character should be consistent across all frames

    2. If frames are misaligned, manually adjust in image editor:
       - Ensure 48×48px per frame in final output
       - Use NEAREST neighbor resampling (no blur for pixel art)

    3. White background removal is automatic, but if artifacts remain:
       - Use image editor to clean up edges
       - Ensure transparency (RGBA mode)

    4. If character varies between frames:
       - Re-run generation (AI output is non-deterministic)
       - Or manually fix colors to match reference frame

    5. Frame bleeding fix in MapPresenceOverlay.vue:
       - Already implemented: MARGIN=2 crops edges
       - If still visible, increase MARGIN value

OUTPUT FILES:
    - complete_raw.png        - Raw AI output (for debugging)
    - complete_transparent.png - White background removed
    - complete_spritesheet_48x48.png - Final 384×480 spritesheet

SPRITESHEET LAYOUT:
    Row 0:  Walk South (towards viewer)
    Row 1:  Walk Southwest
    Row 2:  Walk West (facing left)
    Row 3:  Walk Northwest
    Row 4:  Walk North (away from viewer)
    Row 5:  Walk Northeast
    Row 6:  Walk East (facing right)
    Row 7:  Walk Southeast
    Row 8:  Jump animation
    Row 9:  Dance animation

NOTE: Row indices are 0-based in code but 1-based in comments/docs.
"""

import os
import sys
import argparse
import shutil
from pathlib import Path
from PIL import Image

# Django setup for accessing AISettings
sys.path.insert(0, '/opt/parahub')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'parahub.settings')
import django
django.setup()

from parahub.models import AISettings
from google import genai
from google.genai import types


def get_api_key():
    """Get Google API key from Django settings."""
    ai_settings = AISettings.objects.first()
    if not ai_settings or not ai_settings.google_api_key:
        print("ERROR: No Google API key found in AISettings")
        print("Configure it in Django admin: /admin/parahub/aisettings/")
        sys.exit(1)
    return ai_settings.google_api_key


def build_prompt(avatar_style: str) -> str:
    """Build the generation prompt for Gemini."""
    return f"""Create a COMPLETE pixel-art character spritesheet with 10 ROWS and 8 FRAMES per row.

CRITICAL LAYOUT STRUCTURE:
- EXACTLY 10 horizontal rows stacked vertically
- EXACTLY 8 frames per row arranged horizontally
- Total: 80 frames in a perfect grid (8 columns × 10 rows)
- All frames EXACTLY the same size
- Equal spacing between frames and rows

CRITICAL CHARACTER CONSISTENCY:
- THE SAME CHARACTER in ALL 80 frames
- IDENTICAL appearance: same colors, same outfit, same face, same proportions
- Character is a {avatar_style}
- Modern urban/street style
- Character must fill 70-80% of frame height
- LARGE and CLEARLY VISIBLE in every single frame

ROW ASSIGNMENTS (8 frames each):
Row 1:  Walk SOUTH (towards viewer) - 8 frame walking cycle
Row 2:  Walk SOUTHWEST - 8 frame walking cycle
Row 3:  Walk WEST (to the right) - 8 frame walking cycle
Row 4:  Walk NORTHWEST - 8 frame walking cycle
Row 5:  Walk NORTH (away from viewer) - 8 frame walking cycle
Row 6:  Walk NORTHEAST - 8 frame walking cycle
Row 7:  Walk EAST (to the left) - 8 frame walking cycle
Row 8:  Walk SOUTHEAST - 8 frame walking cycle
Row 9:  JUMP (vertical jump, no direction) - 8 frame jump sequence
Row 10: DANCE (energetic dance) - 8 frame dance sequence

WALKING ANIMATION (Rows 1-8, 8 frames each):
Frame 1: Standing neutral (feet together)
Frame 2: Foot lifting off ground
Frame 3: Mid-stride (one foot forward)
Frame 4: Foot landing
Frame 5: Standing neutral (mid-cycle)
Frame 6: Other foot lifting
Frame 7: Mid-stride (other foot forward)
Frame 8: Foot landing (ready to loop)

JUMP ANIMATION (Row 9, 8 frames):
Frame 1: Crouching (preparing)
Frame 2: Rising (legs extending)
Frame 3: Leaving ground
Frame 4: Peak of jump (arms up)
Frame 5: Starting to fall
Frame 6: Falling
Frame 7: Landing (knees bent)
Frame 8: Standing up

DANCE ANIMATION (Row 10, 8 frames):
Frame 1: Starting pose
Frame 2: Arms out to sides
Frame 3: Arms up, knee lifted
Frame 4: Arms wide
Frame 5: Arms crossed
Frame 6: Bouncing motion
Frame 7: Arms out, other knee up
Frame 8: Return to start (loop-ready)

STYLE REQUIREMENTS:
- 16-bit retro pixel art (SNES/Genesis quality)
- Clean, sharp pixel edges (NO anti-aliasing, NO blur)
- Vibrant colors with good contrast
- SOLID WHITE BACKGROUND (RGB: 255,255,255)
- NO TEXT, NO LABELS, NO ANNOTATIONS anywhere
- Professional game-ready quality

CONSISTENCY CHECKLIST:
✓ Same character model in all 80 frames
✓ Same colors throughout (hair, shirt, pants, shoes)
✓ Same proportions (head size, body size)
✓ Same drawing style across all rows
✓ Perfect 10×8 grid alignment
✓ Large character filling 70-80% of frame height

REMEMBER: This is ONE CHARACTER doing different animations/directions.
Character appearance must be IDENTICAL across all 80 frames!

Output: A perfect 10-row × 8-column spritesheet grid on pure white background."""


def remove_white_background(img: Image.Image) -> Image.Image:
    """Remove white/near-white background, making it transparent."""
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    data = img.getdata()
    new_data = []
    transparent_count = 0

    for pixel in data:
        # Near-white pixels become transparent
        if pixel[0] > 240 and pixel[1] > 240 and pixel[2] > 240:
            new_data.append((255, 255, 255, 0))
            transparent_count += 1
        else:
            new_data.append(pixel)

    img.putdata(new_data)
    pct = transparent_count / len(data) * 100
    print(f"  Removed {transparent_count:,} white pixels ({pct:.1f}%)")
    return img


def generate_spritesheet(output_dir: Path, avatar_style: str) -> Path:
    """Generate spritesheet using Gemini API."""
    api_key = get_api_key()
    client = genai.Client(api_key=api_key)

    prompt = build_prompt(avatar_style)

    print("=" * 70)
    print("🎨 AVATAR SPRITESHEET GENERATOR")
    print("=" * 70)
    print(f"Output:    {output_dir}")
    print(f"Style:     {avatar_style}")
    print(f"Grid:      8 columns × 10 rows = 80 frames")
    print(f"Frame:     48×48 pixels")
    print(f"Model:     gemini-3-pro-image-preview")
    print("=" * 70)

    print(f"\n🚀 Generating spritesheet...")

    try:
        response = client.models.generate_content(
            model="gemini-3-pro-image-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=['IMAGE'],
                image_config=types.ImageConfig(
                    aspect_ratio="4:5",  # Slightly taller than wide (8×10 grid)
                    image_size="2K"      # 2048px for better quality
                )
            )
        )

        for part in response.parts:
            if part.text is not None:
                print(f"💬 AI: {part.text}")

            elif part.inline_data is not None:
                # Save raw output
                img = part.as_image()
                raw_file = output_dir / "complete_raw.png"
                img.save(raw_file)
                print(f"✅ Raw image saved: {raw_file}")

                # Load with PIL for processing
                pil_img = Image.open(raw_file)
                print(f"  Size: {pil_img.size} ({pil_img.mode})")

                # Remove white background
                print("\n🔍 Removing white background...")
                pil_img = remove_white_background(pil_img)

                transparent_file = output_dir / "complete_transparent.png"
                pil_img.save(transparent_file)
                print(f"💾 Transparent: {transparent_file}")

                # Resize to final 384×480 (48px per frame)
                print(f"\n📐 Resizing to 384×480 (48×48 per frame)...")
                final = pil_img.resize((384, 480), Image.Resampling.NEAREST)

                final_file = output_dir / "complete_spritesheet_48x48.png"
                final.save(final_file)

                print(f"✅ Final spritesheet: {final_file}")
                print(f"  Size: {final.size}")
                print(f"  Grid: 8 columns × 10 rows")
                print(f"  Per frame: 48×48px")

                return final_file

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("❌ No image generated")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Generate avatar spritesheet using Google Gemini"
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='/tmp/avatar-sprites',
        help='Output directory (default: /tmp/avatar-sprites)'
    )
    parser.add_argument(
        '--copy-to-frontend',
        action='store_true',
        help='Copy result to frontend/public/sprites/avatars/'
    )
    parser.add_argument(
        '--avatar-style',
        type=str,
        default='casual young male: jeans + t-shirt or hoodie',
        help='Style description for the avatar'
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate
    final_file = generate_spritesheet(output_dir, args.avatar_style)

    # Copy to frontend if requested
    if args.copy_to_frontend:
        frontend_dir = Path('/opt/parahub/frontend/public/sprites/avatars')
        frontend_dir.mkdir(parents=True, exist_ok=True)

        dest_file = frontend_dir / 'male_casual_v1.png'
        shutil.copy(final_file, dest_file)
        print(f"\n📁 Copied to: {dest_file}")

    print("\n" + "=" * 70)
    print("🎉 GENERATION COMPLETE!")
    print("=" * 70)
    print(f"Files in {output_dir}:")
    print(f"  - complete_raw.png           (raw AI output)")
    print(f"  - complete_transparent.png   (white bg removed)")
    print(f"  - complete_spritesheet_48x48.png (final)")
    print("=" * 70)

    if not args.copy_to_frontend:
        print("\nTo deploy:")
        print(f"  cp {final_file} frontend/public/sprites/avatars/male_casual_v1.png")
        print("  /opt/parahub/0restart")


if __name__ == '__main__':
    main()
