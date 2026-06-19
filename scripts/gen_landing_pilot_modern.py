"""
Pilot: MODERN, NO-MASCOT landing illustration — one landing (boleias) in 3 styles, to pick a direction.
Run: /opt/parahub/venv/bin/python manage.py shell -c "exec(open('scripts/gen_landing_pilot_modern.py').read())"

Owner pivot 2026-06-09: drop Para from landing illustrations, set scenes in the present-day world
(real modern cars, contemporary Portugal). This pilot tests medium/style before the full 11-batch.
Outputs pilot-modern-<style>.webp/.png to frontend/public/images/landing-preview/.
"""
import io
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

from parahub.models import AISettings

MODEL = "gemini-3-pro-image-preview"  # Nano Banana Pro
OUT_DIR = Path("frontend/public/images/landing-preview")

# boleias = community rideshare, stop-to-stop, no commission, neighbours sharing a ride.
SUBJECT = (
    "A present-day Portuguese street scene illustrating community rideshare between neighbours: a modern "
    "current-model compact car (or small electric car) has pulled over beside a real contemporary city bus "
    "stop; a friendly driver leans out and offers a lift to a person waiting, a warm everyday moment of "
    "neighbours sharing a ride directly — no taxi company, no middleman. Contemporary Portugal: modern "
    "low-rise apartment buildings, a real present-day street with road markings, present-day casual "
    "clothing, one person glancing at a smartphone ride app. Diverse ordinary people of varied ages. Warm, "
    "optimistic, human, inviting."
)

BRAND = "Weave in the brand palette where natural: warm golden yellow (#FFE216), cyan-teal (#0891B2), deep indigo."
NEG = "NO text, NO words, NO numbers, NO letters, NO logos, NO readable signage, NO brand names anywhere. ONE single unified scene, no panels or frames."
COMP = "Wide panoramic 16:9 composition, clear focal subject with breathing room, warm afternoon light."

STYLES = {
    "watercolor": (
        "Warm contemporary WATERCOLOR editorial illustration — hand-painted with soft blooms, gentle edges "
        "and subtle paper grain, a modern fresh palette, present-day setting (NOT historical, NOT a rustic "
        "village). Painterly but clearly today's world."
    ),
    "flat": (
        "Clean modern FLAT VECTOR illustration in the style of premium tech-company marketing pages "
        "(Stripe / Notion / Figma): bold confident flat color shapes, smooth subtle gradients, simple "
        "geometric forms, crisp and minimal, friendly and contemporary, generous negative space, a polished "
        "digital-product look."
    ),
    "realistic": (
        "Soft SEMI-REALISTIC editorial illustration with warm cinematic lighting and believable modern "
        "people and a real modern car — painterly but grounded realism, the quality of Airbnb or Dropbox "
        "editorial artwork, contemporary and natural."
    ),
}


def build(style: str) -> str:
    return f"{STYLES[style]} SUBJECT: {SUBJECT} {BRAND} {COMP} {NEG}"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = genai.Client(api_key=AISettings.objects.first().google_api_key)
    for style in STYLES:
        print(f"\n=== pilot-modern-{style} ===")
        resp = client.models.generate_content(
            model=MODEL,
            contents=[build(style)],
            config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )
        ok = False
        for part in resp.parts:
            if getattr(part, "inline_data", None) and part.inline_data.data:
                img = Image.open(io.BytesIO(part.inline_data.data)).convert("RGB")
                img.save(OUT_DIR / f"pilot-modern-{style}.png", "PNG")
                img.save(OUT_DIR / f"pilot-modern-{style}.webp", "WEBP", quality=85, method=6)
                print(f"  saved pilot-modern-{style}.png ({img.size[0]}x{img.size[1]})")
                ok = True
                break
        if not ok:
            print("  !! no image (safety filter?)")
            for part in resp.parts:
                if getattr(part, "text", None):
                    print("   ", part.text[:300])


main()
