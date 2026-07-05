"""
Profile endpoints — split by concern from the former single profiles.py.
Importing the endpoint modules registers their routes on the shared router.
"""

from .base import profile_router
from . import core, pgp, psych, notes, photos, badge  # noqa: E402,F401

# Re-exports for identity/tests.py (direct handler calls + schema imports).
from .core import (  # noqa: F401
    create_profile, get_public_profile, update_my_preferences,
    search_profiles, get_manageable_profiles, get_my_profile,
)
from .schemas import ProfileCreateRequest, ProfileUpdateRequest  # noqa: F401

__all__ = ['profile_router']
