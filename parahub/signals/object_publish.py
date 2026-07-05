"""
post_save signal handler for broadcasting object updates via WebSocket.

Connects to all public models from _TYPE_REGISTRY (excludes IoT which has
its own broadcast path from Traccar webhook in iot/services.py).
"""

import logging
from datetime import date, datetime
from decimal import Decimal

from django.db.models.expressions import Combinable
from django.db.models.signals import post_save

logger = logging.getLogger(__name__)

# Models to connect signals to (excludes iot_device — has own broadcast)
_SIGNAL_MODELS = {
    'item':          'market.Item',
    'profile':       'identity.Profile',
    'establishment': 'geo.Establishment',
    'event':         'geo.Event',
    'poll':          'governance.Poll',
}

# Whitelist of safe public fields to broadcast per object_type.
# Only these fields are included in the changes payload.
_BROADCAST_FIELDS = {
    'item': ['title', 'description', 'is_active', 'type', 'version'],
    'profile': ['display_name', 'reputation_score', 'is_verified_wot'],
    'establishment': ['name', 'description', 'is_active', 'is_verified',
                      'rating_avg', 'rating_count', 'logo_url'],
    'event': ['title', 'description', 'status', 'starts_at', 'ends_at',
              'participants_count'],
    'poll': ['title', 'status'],
}

# Reverse map: Model class → object_type (populated in connect_signals)
_MODEL_TO_TYPE: dict = {}


def _serialize_value(val):
    """Serialize a field value to JSON-safe type."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, date):
        return val.isoformat()
    if isinstance(val, Decimal):
        return str(val)
    return val


def _object_post_save(sender, instance, created, raw, **kwargs):
    """Broadcast whitelisted field changes to WS subscribers."""
    if raw or created:
        return

    # Allow skipping broadcast (e.g. bulk updates)
    if getattr(instance, '_skip_ws', False):
        return

    object_type = _MODEL_TO_TYPE.get(sender)
    if not object_type:
        return

    fields = _BROADCAST_FIELDS.get(object_type, [])
    if not fields:
        return

    # If update_fields is specified, only broadcast intersecting fields
    update_fields = kwargs.get('update_fields')
    if update_fields is not None:
        fields = [f for f in fields if f in update_fields]
        if not fields:
            return

    changes = {}
    # Fields still holding an unresolved F()-expression on the in-memory instance.
    # This signal fires inside Model.save(), before any refresh_from_db(), so e.g.
    # Item.save()'s `self.version = F('version') + 1` is a CombinedExpression here —
    # not JSON-serializable. Left in the payload it would make orjson.dumps throw and
    # drop the whole broadcast. Collect them and read the materialized values back.
    deferred = []
    for field in fields:
        val = getattr(instance, field, None)
        if isinstance(val, Combinable):
            deferred.append(field)
        else:
            changes[field] = _serialize_value(val)

    if deferred:
        # Same transaction as the UPDATE → read-your-writes returns the new values.
        fresh = sender.objects.filter(pk=instance.pk).values(*deferred).first()
        if fresh:
            for field in deferred:
                changes[field] = _serialize_value(fresh[field])

    if not changes:
        return

    from parahub.services.ws_publish import ws_publish
    ws_publish(f'object:{instance.id}', {
        'type': 'object.updated',
        'id': str(instance.id),
        'object_type': object_type,
        'changes': changes,
    })


def connect_signals():
    """Connect post_save signals for all broadcastable models. Called from ParahubConfig.ready()."""
    from django.apps import apps

    for object_type, model_path in _SIGNAL_MODELS.items():
        try:
            Model = apps.get_model(*model_path.split('.'))
            _MODEL_TO_TYPE[Model] = object_type
            post_save.connect(
                _object_post_save,
                sender=Model,
                dispatch_uid=f'object_publish_{object_type}',
            )
            logger.debug(f"Connected object_publish signal for {model_path}")
        except LookupError:
            logger.warning(f"Model {model_path} not found, skipping signal connection")
