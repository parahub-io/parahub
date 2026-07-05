"""
Shared Router instance for all IoT endpoint modules.
"""

from ninja import Router

router = Router(tags=["IoT"])
