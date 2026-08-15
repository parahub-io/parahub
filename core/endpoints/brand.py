"""Brand asset endpoints — staff-only delivery of the association's identity marks.

The document stamp is the association's issuing mark, so it is deliberately not
served from `frontend/public/`: a print-quality master on a guessable URL makes
faking a PARAHUB — Associação document a right-click. Files live under
`media/private/brand/` (nginx `internal`) and are handed out here behind a staff
check, the same X-Accel-Redirect pattern as private profile photos.

Regenerate them with `python3 scripts/gen_stamp.py`; nothing here writes.
"""
import logging
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from ninja import Router
from ninja.errors import HttpError

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip

logger = logging.getLogger(__name__)

router = Router(tags=["Brand"])

BRAND_DIR = Path(settings.MEDIA_ROOT) / "private" / "brand"

# Whitelists, so the path can never be steered by the request
STAMP_VARIANTS = {"brand", "mono", "black"}
STAMP_FORMATS = {
    "svg": "image/svg+xml",
    "png": "image/png",
    "pdf": "application/pdf",
}


@router.get("/stamp/{variant}.{fmt}", auth=ProfileAuth())
@ratelimit(group="brand:stamp", key=user_or_ip, rate="120/m")
def get_stamp(request, variant: str, fmt: str):
    """Serve one document-stamp file. Staff only."""
    profile = request.auth_profile
    if not profile.account.is_staff:
        raise HttpError(403, "Staff only")

    if variant not in STAMP_VARIANTS or fmt not in STAMP_FORMATS:
        raise HttpError(404, "No such stamp")

    name = f"stamp-{variant}.{fmt}"
    if not (BRAND_DIR / name).is_file():
        raise HttpError(
            404, f"{name} is missing — run `python3 scripts/gen_stamp.py` to build it"
        )

    response = HttpResponse(content_type=STAMP_FORMATS[fmt])
    response["X-Accel-Redirect"] = f"/media/private/brand/{name}"
    response["Content-Disposition"] = f'inline; filename="{name}"'
    response["Cache-Control"] = "no-store"
    return response
