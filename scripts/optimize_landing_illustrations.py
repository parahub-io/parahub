"""
Optimize the chosen watercolor landing scenes into web-ready WebP.
Source: frontend/public/images/landing-preview/<sub>.png
Dest:   landings/_assets/illustrations/<sub>.webp  (committed; generator copies into each output/)

Run: /opt/parahub/venv/bin/python scripts/optimize_landing_illustrations.py
"""
from pathlib import Path
from PIL import Image

SRC = Path("frontend/public/images/landing-preview")
DST = Path("landings/_assets/illustrations")
TARGET_W = 1200
QUALITY = 72

SUBS = [
    "sos", "energia", "mesh", "democracia", "directorio", "eventos",
    "troca", "contratos", "boleias", "condominios", "transporte",
]


def main():
    DST.mkdir(parents=True, exist_ok=True)
    total = 0
    for sub in SUBS:
        src = SRC / f"{sub}.png"
        if not src.exists():
            print(f"  !! missing {src}")
            continue
        img = Image.open(src).convert("RGB")
        if img.width > TARGET_W:
            h = round(img.height * TARGET_W / img.width)
            img = img.resize((TARGET_W, h), Image.LANCZOS)
        out = DST / f"{sub}.webp"
        img.save(out, "WEBP", quality=QUALITY, method=6)
        kb = out.stat().st_size / 1024
        total += kb
        print(f"  {sub:14} {img.size[0]}x{img.size[1]}  {kb:.0f} KB")
    print(f"  total: {total:.0f} KB across {len(SUBS)}")


main()
