"""
Pilot: bespoke landing illustration — Para in a topic-relevant activity scene.
Run inside Django shell context:
    /opt/parahub/venv/bin/python manage.py shell -c "exec(open('scripts/gen_landing_illustration.py').read())"

Generates TWO style variants for the `transporte` landing for side-by-side review:
  A) flat canonical brand style (matches the 14 app poses + favicon)
  B) Portuguese watercolor blog style (lush, but off-brand Para)
Outputs PNGs to frontend/public/images/landing-preview/.
"""
import io
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

from parahub.models import AISettings

MODEL = "gemini-3-pro-image-preview"  # Nano Banana Pro
OUT_DIR = Path("frontend/public/images/landing-preview")
REF_PATH = Path("frontend/public/images/para/sitting.webp")

# Identity-lock trait tokens — verbatim in every prompt so Para stays the same creature.
PARA = (
    "Para, a small confident YELLOW (#FFE216) creature mascot covered in short soft felt-like fur. "
    "NOT human, NOT humanoid, NOT a real cat: a ROUND creature face (no snout, no whiskers, no Y-mouth), "
    "thin gold round wire-frame glasses, calm warm brown eyes with a gentle knowing smile, "
    "two short rounded Pusheen-style kitten ears (yellow outer, soft terracotta inner), "
    "a short terracotta scarf, a small dark-bronze key-medallion on a cord, and a curly @-shaped tail. "
    "Bare feet, grounded stance, creature anatomy (no waist/hips/gender)."
)

# Shared scene for the transit landing — activity that visually explains "real-time public transport".
SCENE = (
    "Para stands at a modern city bus stop with a shelter and bench, looking up at a digital arrival "
    "sign that shows simple bus pictograms and a row of colored dots (NO numbers, NO readable text). "
    "One hand is raised pointing up toward the sign, ears perked forward with attentive curiosity, "
    "a calm friendly expression as if to say 'your bus is almost here'. A stylized friendly bus "
    "approaches in the background."
)

NEG = ("ONE single unified scene. NO panels, NO comic frames, NO split frames, NO character turnaround, "
       "NO character sheet, NO grid. NO text overlays, NO words, NO numbers, NO labels anywhere.")

PROMPT_A = (
    "Clean OUTLINED 2D cartoon brand illustration — thin black ink outline, flat vibrant colors with "
    "subtle cel-shading, modern editorial brand style (Notion / Figma marketing quality). "
    "Simple flat background in warm brand colors: soft cream and pale yellow with a hint of cyan-teal, "
    "minimal flat shapes for the bus stop and bus. NOT watercolor, NOT painted, NOT 3D, no photographic "
    "texture, no heavy gradients (only gentle cel-shading). "
    f"SUBJECT: {PARA} "
    f"ACTION & SETTING: {SCENE} "
    "COMPOSITION: wide landscape 16:9, Para left-of-center, generous clean negative space, eye level, "
    "soft cream background. "
    f"{NEG}"
)

PROMPT_B = (
    "Warm WATERCOLOR illustration with anime-influenced character expressiveness, Mediterranean "
    "Portuguese atmosphere — terracotta rooftops, stone archways, cobblestone street, warm southern "
    "afternoon light. Watercolor palette of golden yellows, deep indigo blues and warm earth tones, "
    "like azulejo tiles meeting sunset. Visible watercolor blooms and soft edges, hand-painted, subtle "
    "paper grain. Sunny, warm, full of life — a Portuguese town where technology serves people naturally; "
    "the mood is 'I want to live here'. "
    f"SUBJECT: {PARA} Render Para in the SAME warm watercolor medium with soft painted edges, while "
    "keeping the yellow body, round glasses, terracotta scarf, kitten ears and @-tail recognizable. "
    f"ACTION & SETTING: {SCENE} The bus stop sits on a sunny Portuguese street corner with terracotta "
    "rooftops and azulejo tiles; the bus rolls over cobblestones. "
    "COMPOSITION: wide panoramic 16:9, golden afternoon light, Para in the foreground left. "
    f"{NEG}"
)

VARIANTS = [("transporte-flat", PROMPT_A), ("transporte-watercolor", PROMPT_B)]


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    key = AISettings.objects.first().google_api_key
    client = genai.Client(api_key=key)
    ref_part = types.Part.from_bytes(data=REF_PATH.read_bytes(), mime_type="image/webp")

    for name, prompt in VARIANTS:
        print(f"\n=== generating {name} ===")
        resp = client.models.generate_content(
            model=MODEL,
            contents=[prompt, ref_part],
            config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )
        saved = False
        for part in resp.parts:
            if getattr(part, "inline_data", None) and part.inline_data.data:
                img = Image.open(io.BytesIO(part.inline_data.data)).convert("RGB")
                out = OUT_DIR / f"{name}.png"
                img.save(out, "PNG")
                # optimized webp for the page
                img.save(OUT_DIR / f"{name}.webp", "WEBP", quality=82, method=6)
                print(f"  saved {out}  ({img.size[0]}x{img.size[1]})")
                saved = True
                break
        if not saved:
            print(f"  !! no image returned (safety filter?) — text parts:")
            for part in resp.parts:
                if getattr(part, "text", None):
                    print("   ", part.text[:300])


main()
