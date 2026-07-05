"""
One-off Web-of-Trust docs illustration — modern, NO-MASCOT watercolor, present-day scene.
Reuses the owner-approved landing style anchor (see scripts/gen_landing_illustrations_batch.py
and PK/landings-system.md). WoT is a Nuxt docs page, NOT a static landing, so it lives outside
the landings pipeline — this standalone keeps the 11-landing batch (and its sitemaps) untouched.

Run inside Django shell context (needs AISettings.google_api_key):
    /opt/parahub/venv/bin/python manage.py shell -c "exec(open('scripts/gen_wot_illustration.py').read())"

Writes a review master + webp to frontend/public/images/docs-preview/. After owner approval,
optimize + move to frontend/public/images/docs/wot.webp and reference it in docs/wot.vue.
"""
import io
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

from parahub.models import AISettings

MODEL = "gemini-3-pro-image-preview"  # Nano Banana Pro
OUT_DIR = Path("frontend/public/images/docs-preview")

# --- style anchor, verbatim from the landing batch generator (single shared language) ---
STYLE = (
    "Warm contemporary WATERCOLOR editorial illustration — hand-painted with soft blooms, gentle edges "
    "and subtle paper grain, a modern fresh palette, present-day setting (NOT historical, NOT a rustic "
    "village, NOT old-timey). Painterly but clearly today's world."
)
PEOPLE = (
    "PEOPLE: ordinary present-day people of varied ages and backgrounds in natural contemporary clothing, "
    "warm and human. NO mascot, NO cartoon animal character, NO yellow creature anywhere."
)
BRAND = "Weave in the brand palette where natural: warm golden yellow (#FFE216), cyan-teal (#0891B2), deep indigo."
COMP = "Wide panoramic 16:9 composition, a clear storytelling scene with breathing room, warm afternoon light."
NEG = (
    "NO text, NO words, NO numbers, NO letters, NO logos, NO readable signage, NO brand names anywhere. "
    "ONE single unified scene, no panels, no frames, no split screens."
)

# --- WoT scene (variant A: "Vouched in") — differentiator = in-person web of trust + 3 confirmations ---
# Re-roll: count "three" via three distinct countable cords (not sparkles), denser background web, no booth.
SCENE = (
    "A warm TRUST-BUILDING neighbourhood scene at golden hour in a present-day Portuguese courtyard or small "
    "square. In the foreground a NEWCOMER stands at the centre, gently glowing, while exactly THREE individual "
    "neighbours of varied ages — and ONLY three — stand around them, each personally vouching for the newcomer: "
    "the first shakes the newcomer's hand, the second rests a warm hand on their shoulder, the third gestures a "
    "warm introduction. From EACH of these three neighbours ONE clearly visible, distinct, bright luminous "
    "golden CORD of light runs to the newcomer — three separate, countable golden threads converging on the "
    "same person, unmistakable (three personal confirmations). Behind this group the rest of the square is "
    "densely laced with a clearly visible glowing WEB of finer golden trust-threads linking many other people — "
    "at a cafe terrace, on balconies, walking — a living network and constellation of trust spanning the whole "
    "neighbourhood. Real in-person human meeting, modern casual clothing, a parked modern car, warm afternoon "
    "light. NO money, NO coins. Keep the focus on the newcomer and the three bright cords converging on them, "
    "with the denser faint web of connections behind; NOT a packed crowd."
)


def build(scene: str) -> str:
    return f"{STYLE} SUBJECT: {scene} {PEOPLE} {BRAND} {COMP} {NEG}"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = genai.Client(api_key=AISettings.objects.first().google_api_key)
    print("=== wot ===")
    resp = client.models.generate_content(
        model=MODEL,
        contents=[build(SCENE)],
        config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
    )
    for part in resp.parts:
        if getattr(part, "inline_data", None) and part.inline_data.data:
            img = Image.open(io.BytesIO(part.inline_data.data)).convert("RGB")
            img.save(OUT_DIR / "wot.png", "PNG")
            img.save(OUT_DIR / "wot.webp", "WEBP", quality=82, method=6)
            print(f"  saved wot.png ({img.size[0]}x{img.size[1]})")
            return
    print("  !! no image (safety filter?)")
    for part in resp.parts:
        if getattr(part, "text", None):
            print("   ", part.text[:300])


main()
