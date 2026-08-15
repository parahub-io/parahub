"""
Shared Router instance for all IoT endpoint modules.
"""

from ninja import Router

router = Router(tags=["IoT"])


def public_owner_fields(profile):
    """Owner attribution for anonymous map feeds: (visible name, profile CRI).

    The feeds serve one response to everyone, so the name follows the
    anonymous gate of Profile.name_visible: display_name only when the
    profile opted into name_public, the @handle otherwise. The CRI is the
    local_name — what /@{cri} resolves.
    """
    name = profile.display_name if (profile.name_public and profile.display_name) else profile.local_name
    return name, profile.local_name
