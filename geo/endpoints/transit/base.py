"""
Shared Router instance for all transit endpoint modules.
"""

from ninja import Router

router = Router(tags=["Geo / Transit"])
