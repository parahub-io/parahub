#!/usr/bin/env python3
"""
Regenerate a Para mascot pose via Gemini 3 Pro Image Preview.

Uses sitting.png as a known-good canonical reference, applies a pose-specific
prompt, post-processes to transparent PNG matching sibling dimensions (705px
height), and writes to frontend/public/images/para-preview/<name>.png for
visual review on /design/mascot before overwriting production.

Usage:
    python3 scripts/regen_para_pose.py <pose_name>

After approval: cp para-preview/<name>.png para/<name>.png, then clear the
`candidates` array in frontend/pages/design/mascot.vue.

Add new pose prompts to POSE_PROMPTS following the pattern. See PK/mascot.md
iteration lessons for prompt constraints (AI drifts aggressive — explicitly
forbid furrowed brow / clenched stance).
"""
import os
import sys
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, '/opt/parahub')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'parahub.settings')
import django
django.setup()

from parahub.models import AISettings
from google import genai
from google.genai import types

REF = Path('/opt/parahub/frontend/public/images/para/sitting.png')
PREVIEW_DIR = Path('/opt/parahub/frontend/public/images/para-preview')
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

BASE_IDENTITY = (
    "Same character as the reference image — the yellow creature \"Para\" with "
    "round gold wire-frame glasses, terracotta scarf, bronze key medallion on a cord, "
    "@-shaped curly tail. The reference image shows TWO THIN ANTENNA STALKS WITH "
    "GLOWING AMBER TIPS — REMOVE THESE COMPLETELY. REPLACE with two SHORT, CHUBBY, "
    "ROUNDED kitten ears on top of the head: Pusheen-cat style or Stitch-style ears — "
    "VERY SHORT (ear height = approximately 1/5 to 1/4 of the head height, NEVER more "
    "than 1/3). Shape: rounded triangular base with CLEARLY ROUNDED-OFF SOFT TIPS, "
    "almost dome-shaped — NOT sharp points, NOT tall lynx tufts, NOT elongated rabbit "
    "ears, NOT pointed anime cat ears. The ears look CHUBBY and SOFT, like a baby "
    "kitten or plush toy ears. Outer ear same yellow as body, inner ear soft terracotta "
    "tint echoing the scarf. Same thin black ink outline. NO antenna stubs or stalks "
    "remain — only the kitten ears on top of head. Identical outlined 2D cartoon "
    "style: thin black ink outline, flat vibrant yellow body with cel-shading, same "
    "proportions (head:body ≈ 1:1.5, creature anatomy, not humanoid). "
)

# Critical: AI structurally cannot decouple cat-ears from cat-anatomy. Without
# this anchor block, every regen drifts the face toward feline (pointed snout,
# Y-mouth, almond eyes, paw hands). Repeat per session experiments 2026-05-26.
ANTI_CAT_FACE_ANCHOR = (
    "CRITICAL — FACE AND BODY MUST STAY IDENTICAL TO REFERENCE CREATURE: this is "
    "Para the yellow CREATURE with kitten-style ears, NOT a cat. The muzzle stays "
    "ROUND and CREATURE-LIKE (same neutral creature face as reference — round face, "
    "soft curved cheeks, small creature mouth). DO NOT introduce feline face anatomy: "
    "NO pointed cat snout, NO Y-shaped cat mouth, NO cat whiskers, NO feline cheek "
    "tufts, NO almond-eye narrowing. The body stays the SAME cozy rounded creature "
    "proportions (NOT streamlined cat body). Keep the @-shaped curly tail (NOT a cat "
    "tail). Keep the same hands and feet as reference (NOT paws). ONLY the ears are "
    "kitten-style; FACE specifically must look IDENTICAL to reference creature."
)

COMMON_CONSTRAINTS = (
    "Single character centered on pure white background (RGB 255,255,255). Full body "
    "front view. Same scale and framing as the reference. No text, no labels, no "
    "annotations. Warm and approachable register — calm confidence, NEVER angry, "
    "NEVER furrowed brow, NEVER clenched fists, NEVER combative."
)

# Each pose has TWO parts: BODY (existing pose, gesture, expression) and EARS
# (position + emotion signal per § Ear Vocabulary in PK/mascot.md). The ear
# position is the new emotional language layer — must be explicit per pose so
# AI doesn't default to generic upright.
POSE_PROMPTS = {
    'sitting': (
        "POSE: sitting cross-legged on the ground, both hands resting calmly on the "
        "knees or in the lap, slight head tilt forward, warm calm smile, eyes softly "
        "looking forward through glasses, brow completely relaxed. Shoulders relaxed, "
        "@-tail visible curling around to one side. Register: chill, idle, quietly "
        "present — like sitting on a porch in the afternoon.\n"
        "EARS: relaxed, slightly tilted BACK (not forward, not perked up). Soft, "
        "lowered relaxation. Signals calm/idle/at-rest. Both ears symmetric and "
        "slightly back-tilted, like a kitten lounging."
    ),
    'focused': (
        "POSE: standing upright, calm concentrated expression of someone reading "
        "attentively. Eyes softly focused looking slightly down as if reading. Brow "
        "relaxed or very slightly lifted in curiosity — NOT furrowed, NOT frowning. "
        "Mouth small and neutral, possibly with a tiny soft curve. Shoulders relaxed, "
        "stance grounded. Hands held softly in front at chest level as if holding an "
        "open book — relaxed finger posture, no fists. Register: quiet thoughtful "
        "concentration, like reading a letter.\n"
        "EARS: both perked slightly FORWARD and slightly NARROWED inward. Attentive "
        "focused posture, like a kitten studying something interesting. Symmetric."
    ),
    'building': (
        "POSE: standing, thoughtful constructive concentration of someone working on "
        "a small project. Eyes looking down at the hands with gentle attention. Brow "
        "relaxed or softly raised in interest — NOT furrowed, NOT gritted. Mouth small, "
        "neutral, with a tiny hint of a pleased smile as if quietly absorbed in the "
        "task. Holding a small wrench or simple tool loosely in one hand, the other "
        "hand held open or gesturing as if about to place something — relaxed fingers, "
        "NOT a fighting grip. Shoulders relaxed, stance grounded and natural. Register: "
        "warm craftsmanship, tinkering happily, absorbed and content — like fixing a "
        "bicycle on a Sunday morning, NOT struggling or fighting the tool.\n"
        "EARS: both perked FORWARD with a slight ASYMMETRIC tilt (one ear slightly "
        "more forward than the other). Attentive but relaxed tinkering posture."
    ),
    'default': (
        "POSE: standing upright in calm neutral stance. Soft warm closed-mouth smile, "
        "calm eyes looking forward through glasses, brow completely relaxed. One hand "
        "raised slightly with open palm (gentle greeting acknowledgment), the other "
        "hand held loosely at the side. Shoulders relaxed, stance grounded. Register: "
        "warm approachable peer presence, calm confidence.\n"
        "EARS: both UPRIGHT with a very SLIGHT FORWARD lean. Symmetric, neutral-"
        "attentive. Signals calm presence, attentive but not tense."
    ),
    'welcome': (
        "POSE: standing upright with one hand raised high in an OPEN WAVING gesture "
        "(palm facing viewer, fingers relaxed and spread — five HUMAN-style fingers, "
        "NOT cat paw pads), the other hand extended slightly outward palm-up in "
        "inviting posture (also human-style hand, NOT paw). Big warm welcoming smile, "
        "eyes soft and bright, brow lifted in friendly openness. Register: open, "
        "warm, inviting — like greeting a friend at the door.\n"
        "FACE: round creature face IDENTICAL to canonical sitting reference — NO "
        "visible triangular cat nose (creature face has no protruding nose), small "
        "soft simple SMILE (a single gentle curved line, NOT a Y-shaped cat mouth, "
        "NOT a triangle cat mouth, NOT showing teeth). The face must look like the "
        "reference creature, only the ears differ.\n"
        "EARS: both PERKED WIDE FORWARD, set apart in an open posture. Friendly and "
        "fully attentive. Signals open greeting, welcoming."
    ),
    'alert': (
        "POSE: standing upright, body slightly tense and attentive. One hand raised "
        "with palm out in a cautioning-stop gesture, the other hand at the side ready. "
        "Eyes wide open and focused forward — alert but NOT angry, NOT frightened. "
        "Mouth small and serious. Brow softly raised in concern (NOT furrowed). "
        "Register: aware, attentive, caring-warning — like saying 'pay attention' "
        "calmly, not screaming.\n"
        "EARS: both SHARPLY PERKED FORWARD and slightly tensed. Symmetric, very alert "
        "posture. Signals alarm/attention demanded. NOT flattened back (that would be "
        "fear) — perked forward (engaged alertness)."
    ),
    'caring': (
        "POSE: standing softly, one hand gently held to the chest near the heart, the "
        "other hand extended forward with palm up in a gentle offering gesture. Soft "
        "warm smile, eyes gentle and slightly tilted down with empathy. Brow softly "
        "relaxed. Head slightly tilted to one side in a caring listening posture. "
        "Register: warm empathy, mutual aid, gentle support — like comforting a "
        "friend.\n"
        "EARS: both relaxed, with ONE ear softly TILTED to the side (the side the "
        "head is tilted toward). Asymmetric in a gentle way. Signals attentive "
        "empathy, listening."
    ),
    'celebrating': (
        "POSE: standing with BOTH arms raised up high in joyful triumph, open hands "
        "with fingers spread. Big happy smile, eyes bright and closed/curved upward "
        "in joy, brow lifted in delight. Body posture open and expansive. Register: "
        "pure joy, completion, triumph — like crossing a finish line with friends.\n"
        "EARS: both PERKED HIGH and WIDE-SET, fully upright in joyful attention. "
        "Symmetric. Signals joy/triumph."
    ),
    'pointing': (
        "POSE: standing upright, one hand extended forward with the INDEX FINGER "
        "pointing clearly to the right (viewer's right). The other hand at the side or "
        "softly at hip. Eyes following the direction of the pointing finger. Soft "
        "neutral expression with slight smile. Body leaning very slightly toward the "
        "direction of the point. Register: helpful directing, tutorial guidance.\n"
        "EARS: both perked forward and slightly LEANING toward the right (the "
        "direction of the point). Symmetric forward but with directional bias. "
        "Signals directive attention, focus toward something."
    ),
    'puzzled': (
        "POSE: standing, both hands slightly raised palms-up at chest level in a "
        "questioning gesture. Head tilted to one side in confusion. Eyes slightly "
        "narrowed in thought, brow ONE side slightly lifted (the curious-quizzical "
        "look), mouth small and slightly twisted in confusion. NOT angry, NOT sad — "
        "just confused. Register: 'huh? where did it go?' — endearingly confused.\n"
        "EARS: ASYMMETRIC — ONE ear perked UP, the other ear tilted slightly BACK "
        "or to the side. Very visible asymmetric ear posture. Signals confusion, "
        "'huh?' — the classic kitten-confused-head-tilt look."
    ),
    'reading': (
        "POSE: standing or slightly seated, holding an open BOOK in both hands at "
        "chest level, eyes softly focused down on the book pages. Slight peaceful "
        "smile. Shoulders relaxed, head slightly tilted forward over the book. Brow "
        "completely relaxed. Register: quiet absorption, peaceful reading.\n"
        "EARS: both softly TILTED BACK and slightly DOWN. Relaxed, low-alert posture. "
        "Signals quiet absorption, undistracted focus on something close. Like a "
        "kitten lounging while focused."
    ),
    'searching': (
        "POSE: standing upright, one hand held flat above the eyes/brow like a visor "
        "shading the eyes (classic looking-into-distance pose), the other hand on hip "
        "or at side. Body slightly leaning forward, head tilted as if scanning the "
        "horizon. Eyes wide open in curious attentiveness. Soft neutral expression "
        "with slight focused smile. Register: curious scanning, lookout.\n"
        "EARS: both PERKED HIGH and slightly SPREAD, with a slight head tilt giving "
        "asymmetric appearance. Hyper-alert curious-scanning posture. Signals "
        "active searching/scanning."
    ),
    'shrug': (
        "POSE: standing upright with BOTH shoulders slightly raised and BOTH hands "
        "extended palms-up at sides in a classic 'I don't know' shrug gesture. Soft "
        "small mouth in a slight 'hmm' shape, eyes calm with brow softly raised in "
        "the universal 'not sure' look. Slight head tilt. Register: 'dunno', shrug — "
        "neither happy nor sad, just unsure.\n"
        "EARS: both relaxed in a FLAT/SLIGHTLY DROOPED sideways posture (NOT perked, "
        "NOT back). Splayed sideways like a kitten that doesn't care. Signals "
        "'dunno', noncommittal."
    ),
    'thumbs_up': (
        "POSE: standing upright, one hand extended forward with a clear THUMBS-UP "
        "gesture (closed fist with thumb pointing up clearly), the other hand at side "
        "or slightly forward in supporting gesture. Big warm confident closed-mouth "
        "smile, eyes bright with confidence. Brow relaxed. Register: confident "
        "affirmation, 'all good', encouraging.\n"
        "EARS: both CONFIDENTLY PERKED UPRIGHT, symmetric and slightly tilted forward. "
        "Confident attention posture. Signals affirmation, all-good."
    ),
}


def get_api_key():
    s = AISettings.objects.first()
    if not s or not s.google_api_key:
        sys.exit("ERROR: no Google API key in AISettings")
    return s.google_api_key


def make_transparent(img: Image.Image) -> Image.Image:
    img = img.convert('RGBA')
    w, h = img.size
    for corner in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        ImageDraw.floodfill(img, corner, (255, 255, 255, 0), thresh=30)
    data = list(img.getdata())
    border = 8
    new_data = []
    for i, px in enumerate(data):
        x = i % w
        y = i // w
        in_border = x < border or x >= w - border or y < border or y >= h - border
        if in_border and px[0] > 240 and px[1] > 240 and px[2] > 240 and px[3] > 0:
            new_data.append((255, 255, 255, 0))
        else:
            new_data.append(px)
    img.putdata(new_data)
    return img


def autocrop(img: Image.Image, pad: int = 8) -> Image.Image:
    bbox = img.getbbox()
    if not bbox:
        return img
    w, h = img.size
    return img.crop((
        max(0, bbox[0] - pad),
        max(0, bbox[1] - pad),
        min(w, bbox[2] + pad),
        min(h, bbox[3] + pad),
    ))


def resize_to_siblings(img: Image.Image, target_h: int = 705) -> Image.Image:
    ratio = target_h / img.height
    return img.resize((int(img.width * ratio), target_h), Image.LANCZOS)


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in POSE_PROMPTS:
        sys.exit(f"Usage: {sys.argv[0]} <{' | '.join(POSE_PROMPTS)}>")
    pose = sys.argv[1]
    prompt = f"{BASE_IDENTITY}\n\n{ANTI_CAT_FACE_ANCHOR}\n\n{POSE_PROMPTS[pose]}\n\n{COMMON_CONSTRAINTS}"

    api_key = get_api_key()
    client = genai.Client(api_key=api_key)
    ref_img = Image.open(REF)
    print(f"Pose:      {pose}")
    print(f"Reference: {REF}")
    print(f"Model:     gemini-3-pro-image-preview")
    print(f"Generating...")

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
        sys.exit("ERROR: no image returned")

    raw_path = Path(f'/tmp/{pose}_raw.png')
    raw_path.write_bytes(img_data)
    print(f"Raw: {raw_path} ({len(img_data):,}B)")

    raw = Image.open(raw_path)
    img = make_transparent(raw)
    img = autocrop(img, pad=8)
    img = resize_to_siblings(img, target_h=705)
    out = PREVIEW_DIR / f'{pose}.png'
    img.save(out, optimize=True)
    print(f"Preview: {out} ({img.size}, {out.stat().st_size:,}B)")
    print(f"View on: /design/mascot")


if __name__ == '__main__':
    main()
