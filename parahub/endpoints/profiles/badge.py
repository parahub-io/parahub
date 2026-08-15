"""
Printable profile badge (PDF download + PNG preview).
"""


from ninja.errors import HttpError
import logging

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip

from .base import profile_router

logger = logging.getLogger(__name__)


@profile_router.get("/me/badge/", auth=ProfileAuth())
@ratelimit(group='profiles:badge', key=user_or_ip, rate='30/m')
def download_my_badge(request, format: str = "single"):
    """
    Generate and download Para-ID badge for the authenticated user.

    Query params:
        format: "single" (54x86mm PDF), "batch" (9 cards on A4 PDF),
                or "png" (single badge rendered as PNG, for on-screen preview)

    Single mode: Returns a printable PDF badge (54x86mm) suitable for lanyard display.
    Batch mode: Returns A4 PDF with 9 identical badges and cut lines for economical printing.
    PNG mode: Returns an inline image identical to the single PDF.
    """
    from django.http import HttpResponse
    from parahub.services.badge_generator import BadgeGenerator

    try:
        profile = request.auth_profile

        if format == "png":
            png_bytes = BadgeGenerator.render_png(profile)
            response = HttpResponse(png_bytes, content_type='image/png')
            response['Content-Disposition'] = 'inline'
            return response

        if format == "batch":
            pdf_bytes = BadgeGenerator.generate_batch(profile)
            filename = f"parahub-{profile.local_name}-batch.pdf"
        else:
            pdf_bytes = BadgeGenerator.generate(profile)
            filename = f"parahub-{profile.local_name}.pdf"

        # Return as downloadable PDF
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    except Exception as e:
        logger.error(f"Error generating badge: {e}")
        raise HttpError(500, "Failed to generate badge")
