"""
Deployment slot detection from ASGI scope.

Maps uvicorn listening port to deployment slot name so that
feed:system notifications (e.g. new_version) are only forwarded
to WebSocket clients connected to the matching slot.
"""

# Port → deployment slot mapping
# prod=8000, dev1=8001, dev2=8003, dev3=8004
_PORT_SLOT_MAP = {8000: 'prod', 8001: 'dev1', 8003: 'dev2', 8004: 'dev3'}


def get_deploy_slot(scope: dict) -> str:
    """Derive deployment slot from ASGI scope server port."""
    port = (scope.get('server') or (None, None))[1]
    return _PORT_SLOT_MAP.get(port, 'prod')
