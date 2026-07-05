"""
Governance API endpoints for Parahub
Routes polls subrouter from governance.api
"""

from ninja import Router
import logging

logger = logging.getLogger(__name__)

# Create governance router
governance_router = Router()

# Import and mount polls router (new system with Liquid Democracy)
from governance.api import polls_router
governance_router.add_router("/polls", polls_router)

# Civic opinion polls (territory-scoped, pseudonymous — PK/civic-polls-system.md)
from governance.civic_api import civic_router
governance_router.add_router("/civic", civic_router)
