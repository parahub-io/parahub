#!/usr/bin/env python3
"""
Phase 3 of cat-ears rollout: regenerate character sheets in PK/mascot/.

Two sheets, both multi-figure layouts (NOT single-character poses — so we skip
the transparency/autocrop/resize pipeline used by regen_para_pose.py):

  primary.png    — front + 3/4 + icon (3 figures on white)
  supplement.png — back view + medallion close-up (multi-figure)

Output: PK/mascot/{primary,supplement}-new.png — owner-approved replacement
of originals during Phase 6 rollout.
"""
import os
import sys
from pathlib import Path
from PIL import Image

sys.path.insert(0, '/opt/parahub')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'parahub.settings')
import django
django.setup()

from parahub.models import AISettings
from google import genai
from google.genai import types

MASCOT_DIR = Path('/opt/parahub/PK/mascot')

EAR_OVERRIDE = (
    "CRITICAL CHANGE FROM REFERENCE — only the head-top elements: "
    "the reference shows TWO THIN ANTENNA STALKS WITH GLOWING AMBER TIPS on top of "
    "the head of EVERY figure shown in the image. REMOVE THESE COMPLETELY from "
    "every figure. REPLACE with two SHORT, CHUBBY, ROUNDED kitten ears: "
    "Pusheen-cat style — short (ear height ≈ 1/4 to 1/5 of head height), "
    "rounded triangular base with CLEARLY ROUNDED-OFF SOFT TIPS (not sharp), "
    "outer ear same yellow as body, inner ear soft terracotta tint echoing the "
    "scarf, same thin black ink outline. NO antenna stubs remain, only kitten "
    "ears.\n\n"
    "FACE AND BODY MUST STAY IDENTICAL TO REFERENCE CREATURE: this is Para the "
    "yellow CREATURE with kitten ears, NOT a cat. Round muzzle, creature face "
    "(NOT pointed cat snout, NO whiskers, NO Y-mouth, NO almond eyes). Keep "
    "@-shaped curly tail. Keep round glasses, terracotta scarf, bronze key "
    "medallion. ONLY the head-top elements (antennae → kitten ears) change "
    "across all figures."
)

SHEETS = {
    'primary': (
        "Reproduce the reference character sheet EXACTLY: same composition (three "
        "figures side by side on white background), same poses (front view on left, "
        "three-quarter view in middle showing the @-tail, small icon-size character "
        "on right), same outlined 2D cartoon art style (thin black ink outline, "
        "flat yellow body, cel-shading), same proportions, same layout. ALL "
        "elements (glasses, scarf, medallion, hands, tail, body, expressions) "
        "must remain identical to reference — except the head-top elements per "
        "the constraint below."
    ),
    'supplement': (
        "Reproduce the reference character sheet EXACTLY: same composition (figures "
        "on white background showing back view with @-tail visible curling on the "
        "side, plus close-up front view with medallion detail), same outlined 2D "
        "cartoon art style, same proportions. Keep the bottom labels (FULL BACK VIEW "
        "and CLOSE-UP FRONT VIEW) intact. For the BACK VIEW figure, show the kitten "
        "ears from behind — the OUTER SIDE of the ears is visible (yellow with thin "
        "outline, NOT showing the terracotta inner). For the CLOSE-UP FRONT VIEW "
        "figure, show kitten ears from the front (terracotta inner visible). ALL "
        "other elements (scarf, medallion, body, tail, expressions) identical to "
        "reference."
    ),
}


def get_api_key():
    s = AISettings.objects.first()
    if not s or not s.google_api_key:
        sys.exit("ERROR: no Google API key in AISettings")
    return s.google_api_key


def main():
    targets = sys.argv[1:] if len(sys.argv) > 1 else list(SHEETS.keys())
    for t in targets:
        if t not in SHEETS:
            sys.exit(f"Unknown sheet: {t}. Available: {list(SHEETS.keys())}")

    client = genai.Client(api_key=get_api_key())
    for sheet in targets:
        ref_path = MASCOT_DIR / f'{sheet}.png'
        out_path = MASCOT_DIR / f'{sheet}-new.png'
        print(f"\n=== {sheet} ===")
        print(f"Ref: {ref_path}")
        prompt = f"{SHEETS[sheet]}\n\n{EAR_OVERRIDE}"
        ref_img = Image.open(ref_path)
        response = client.models.generate_content(
            model='gemini-3-pro-image-preview',
            contents=[ref_img, prompt],
            config=types.GenerateContentConfig(response_modalities=['IMAGE', 'TEXT']),
        )
        img_data = None
        for part in response.parts:
            if part.text:
                print(f"AI: {part.text}")
            if part.inline_data:
                img_data = part.inline_data.data
                break
        if not img_data:
            print(f"ERROR: no image returned for {sheet}")
            continue
        out_path.write_bytes(img_data)
        print(f"Wrote: {out_path} ({len(img_data):,}B)")


if __name__ == '__main__':
    main()
