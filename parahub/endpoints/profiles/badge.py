"""
Printable profile badge (PDF/PNG download).
"""


from ninja.errors import HttpError
from pydantic import BaseModel
import logging

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip

from .base import profile_router

logger = logging.getLogger(__name__)

class BadgeOptionsRequest(BaseModel):
    """Options for badge generation"""
    include_birth_date: bool = True
    include_pgp: bool = True

@profile_router.get("/me/badge/", auth=ProfileAuth())
@ratelimit(group='profiles:badge', key=user_or_ip, rate='30/m')
def download_my_badge(
    request,
    format: str = "single",
    include_birth_date: bool = True,
    include_pgp: bool = True
):
    """
    Generate and download Para-ID badge PDF for the authenticated user.

    Query params:
        format: "single" (54x86mm) or "batch" (9 cards on A4) - default: single
        include_birth_date: Include birth date if available (default: true)
        include_pgp: Include PGP fingerprint if available (default: true)

    Single mode: Returns a printable PDF badge (54x86mm) suitable for lanyard display.
    Batch mode: Returns A4 PDF with 9 identical badges and cut lines for economical printing.
    """
    from django.http import HttpResponse
    from parahub.services.badge_generator import BadgeGenerator

    try:
        profile = request.auth_profile

        # Generate PDF based on format
        if format == "batch":
            pdf_bytes = BadgeGenerator.generate_batch(
                profile,
                include_pgp=include_pgp,
            )
            filename = f"parahub-{profile.local_name}-batch.pdf"
        else:
            pdf_bytes = BadgeGenerator.generate(
                profile,
                include_birth_date=include_birth_date,
                include_pgp=include_pgp,
            )
            filename = f"parahub-{profile.local_name}.pdf"

        # Return as downloadable PDF
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    except Exception as e:
        logger.error(f"Error generating badge: {e}")
        raise HttpError(500, "Failed to generate badge")
