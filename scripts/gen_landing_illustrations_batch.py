"""
Batch v3: MODERN, NO-MASCOT watercolor landing illustrations — present-day scenes per landing.
Run inside Django shell context:
    /opt/parahub/venv/bin/python manage.py shell -c "exec(open('scripts/gen_landing_illustrations_batch.py').read())"

Set SELECT to a list of names to (re)generate a subset; empty = all.
Outputs <name>.png (full-res master) + <name>.webp (gallery) to frontend/public/images/landing-preview/.

Owner direction (2026-06-09, pivot from the Para-watercolor set): NO mascot; each scene set in the
present-day world (real modern cars, contemporary Portugal). Style = modern watercolor editorial
(pilot "A", owner-approved). Each scene keeps the landing's differentiator as the visual hook
(P2P energy arc, delegation chain, barter ring, dual key-seals, streetlamp node...). Meaning via
situation + symbols ONLY, never text (6 locales would garble any word).
"""
import io
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

from parahub.models import AISettings

MODEL = "gemini-3-pro-image-preview"  # Nano Banana Pro
OUT_DIR = Path("frontend/public/images/landing-preview")

SELECT: list[str] = []  # e.g. ["sos", "energia"] to regen a subset; [] = all

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

# Present-day, mascot-free scenes — differentiator as the visual hook.
SCENES = {
    "sos": (
        "A warm CARING neighbourhood scene at golden hour on a present-day Portuguese street where modern "
        "houses stand close side by side. An elderly woman stands at her own open doorway needing a hand. "
        "From the two or three immediately adjacent houses her neighbours hurry over — clearly LOCAL people "
        "who just stepped out from next door in casual at-home clothing (a cardigan, an apron, slippers), a "
        "couple of front doors still ajar behind them, caught mid-stride, moving quickly but with warm, "
        "concerned, caring faces. The nearest neighbour, already reaching her, gently rests a reassuring "
        "hand on her shoulder. A soft glowing pulse of light ripples outward from her doorway to the "
        "surrounding houses — an instant alert reaching the whole group at once. Houses standing right "
        "beside each other, neighbours stepping straight out of their own doors — help arriving in a "
        "moment. Golden reassuring light, warm palette — absolutely NO alarm, NO siren, NO red, NO danger, "
        "NO crime, NO travel luggage, NO backpacks, NO distant city skyline; only neighbours helping "
        "neighbours, fast and kind."
    ),
    "energia": (
        "Two adjacent modern Portuguese houses with rooftop solar panels in clear midday sun, clean and "
        "uncluttered. A luminous golden ribbon of energy arcs SIDEWAYS from one home's solar array straight "
        "across to the neighbouring house's window, where a single resident receives it warmly — energy "
        "travelling house-to-house, NOT upward. A few small golden coins drift back along the ribbon toward "
        "the producer standing on the first rooftop terrace. A tall grey high-voltage pylon stands dim and "
        "bypassed in the far background. One roof glows a soft healthy green. Keep it simple — just the two "
        "houses, the energy arc and two people; NO crowd, NO gathering of people below, NO busy street."
    ),
    "mesh": (
        "A present-day Portuguese village street at dusk. A technician on a small ladder mounts a sleek "
        "modern white outdoor WiFi node onto a municipal streetlamp. Soft luminous signal arcs hop from "
        "that lamppost to the next lamppost down the street and into the windows of houses, which glow "
        "warmly as they come online. A tiny warm orange spark glints at the node. A couple of modern cars "
        "parked along the street, contemporary houses, gentle hills behind — the village lighting up."
    ),
    "democracia": (
        "A single warm focal scene: a person relaxed on a comfortable sofa in a sunlit modern Portuguese "
        "living room, casually voting on a tablet with a coffee nearby — politically active from the couch, "
        "on their own time, with NO meeting and NO queue. From the tablet, soft luminous threads of light "
        "drift out through the open window and connect to a few other people each in their own comfortable "
        "place (a café table, a park bench, a balcony), all converging into ONE clearly recognizable "
        "TRANSPARENT GLASS BALLOT BOX with a voting slot on top, softly glowing as a shared civic symbol — "
        "folded paper ballots and a simple rising vote-tally clearly visible inside it (transparent and "
        "auditable, updating live). The threads flow into the box's slot. One thread carries several "
        "glowing vote-tokens at once — a neighbour entrusting their vote to someone they trust (liquid "
        "delegation). It is unmistakably a ballot box, NOT an abstract orb or formless blob. Calm, "
        "effortless, empowering. Absolutely NO queue, NO line of people waiting, NO assembly hall, NO crowd."
    ),
    "directorio": (
        "A lively present-day Portuguese shopping street with a row of modern local storefronts of EQUAL "
        "prominence (a bakery, a bike-repair shop, a café) with clean contemporary blank signage. A person "
        "holding a smartphone that shows a simple map warmly meets a shopkeeper in a doorway and shakes "
        "hands. Above the genuine shops float soft glowing check marks and small golden stars (verified, "
        "honest reviews). Modern casual clothing, a parked modern car, bright midday light."
    ),
    "eventos": (
        "A warm, intimate community event in a modern Portuguese setting at golden evening: a cosy table "
        "under strings of festival lights where a small friendly group of a few people gathers around an "
        "open laptop showing a smiling remote guest joining by video call — the clear focal point is this "
        "hybrid connection, with soft warm glows linking the in-person people to the guest on screen. A "
        "hint of a festa behind (a stall, some lights) kept soft and out of focus. Contemporary casual "
        "clothing. Focused on the small group and the screen; NOT a large sprawling crowd, NOT a packed square."
    ),
    "troca": (
        "A warm present-day setting — a modern courtyard or community swap market. Three or four "
        "contemporary people of varied ages stand in a closed RING, each handing a different everyday "
        "object to the next person clockwise — a potted houseplant, a cordless power drill, a stack of "
        "books, a bicycle — a continuous loop of giving where everyone both gives and receives. A soft "
        "glowing circular arrow traces the full ring (a found exchange cycle). There is NO money and NO "
        "coins anywhere. Modern casual clothing, warm light, friendly eye-contact around the circle."
    ),
    "contratos": (
        "A modern Portuguese café terrace / co-working table in warm light. TWO present-day people shake "
        "hands over a freshly signed paper agreement on the table, an open laptop beside it. On the "
        "document are TWO glowing golden wax seals, each shaped like a key (the two signatures). A thin "
        "luminous chain-link runs from the document outward to a small glowing orange sun low on the "
        "horizon (an immutable anchor of proof). A small softly glowing balance-scale rests on the table. "
        "The document is otherwise blank. Contemporary clothing, a real modern deal closed between people."
    ),
    "boleias": (
        "A present-day Portuguese street: a modern compact car (or small electric car) has pulled over "
        "beside a contemporary city bus stop; a friendly driver leans out and offers a lift to a person "
        "waiting, a warm everyday moment of neighbours sharing a ride directly — no taxi company, no "
        "middleman. Between the driver's hand and the passenger's hand a couple of small golden coins pass "
        "DIRECTLY hand-to-hand (a fair, modest, direct payment). Modern low-rise apartment buildings, a "
        "real present-day street with road markings, present-day clothing, one person glancing at a "
        "smartphone ride app. Diverse people of varied ages. Warm, optimistic, human."
    ),
    "condominios": (
        "A single modern Portuguese apartment building seen from its courtyard, clean and uncluttered, with "
        "a solar-panel array on the roof. A few residents on their own balconies and at open windows each "
        "look at a smartphone, voting from home; in the foreground one resident holds up a tablet showing a "
        "clear colourful budget pie-chart (coloured segments only, NO numbers, NO text) that softly glows, "
        "visible to all — a transparent shared budget. Soft luminous threads connect the residents' devices "
        "to the glowing budget. Warm daylight, calm — the building deciding together without an in-person "
        "meeting. Show the building and a few residents on balconies; NOT a big crowd packed in the "
        "courtyard, NO raised-hands assembly."
    ),
    "transporte": (
        "A present-day Portuguese bus stop with a sleek modern electric bus rounding the corner nearby. "
        "People wait calmly; one holds a smartphone showing a live map with a bright location pin marking "
        "the approaching bus's real position, exactly matching the bus that is actually arriving. A modern "
        "blank digital departure display on the shelter. Contemporary clothing, a real modern city street. "
        "Warm morning light — the calm of knowing exactly when your bus comes."
    ),
}


def build(scene: str) -> str:
    return f"{STYLE} SUBJECT: {scene} {PEOPLE} {BRAND} {COMP} {NEG}"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = genai.Client(api_key=AISettings.objects.first().google_api_key)
    names = SELECT or list(SCENES.keys())

    for name in names:
        print(f"\n=== {name} ===")
        resp = client.models.generate_content(
            model=MODEL,
            contents=[build(SCENES[name])],
            config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )
        ok = False
        for part in resp.parts:
            if getattr(part, "inline_data", None) and part.inline_data.data:
                img = Image.open(io.BytesIO(part.inline_data.data)).convert("RGB")
                img.save(OUT_DIR / f"{name}.png", "PNG")
                img.save(OUT_DIR / f"{name}.webp", "WEBP", quality=82, method=6)
                print(f"  saved {name}.png ({img.size[0]}x{img.size[1]})")
                ok = True
                break
        if not ok:
            print("  !! no image (safety filter?)")
            for part in resp.parts:
                if getattr(part, "text", None):
                    print("   ", part.text[:300])


main()
