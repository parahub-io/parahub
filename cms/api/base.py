"""
Shared Router instance for all CMS endpoint modules.
"""

from ninja import Router

router = Router(tags=["CMS"])
