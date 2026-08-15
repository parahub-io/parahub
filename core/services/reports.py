"""Report target resolution for ContentReport.

Curated registry of reportable models. Resolution happens server-side at
report creation so moderation keeps the author and a content excerpt even
after the reported object is edited or deleted.
"""

from django.apps import apps


def _profile_excerpt(profile):
    return profile.display_name or profile.local_name


# app_label.Model -> (author extractor, excerpt extractor)
# Extractors receive the model instance; author may resolve to None
# (e.g. an unclaimed establishment imported from OSM).
REPORTABLE_TYPES = {
    'market.Item': (lambda o: o.owner, lambda o: o.title),
    'identity.Profile': (lambda o: o, _profile_excerpt),
    'geo.Establishment': (lambda o: o.owner, lambda o: o.name),
    'geo.Event': (lambda o: o.organizer, lambda o: o.title),
    'geo.WorldObject': (lambda o: o.owner, lambda o: o.full_address or str(o)),
    'cms.Post': (lambda o: o.author, lambda o: o.title),
    'core.ObjectComment': (lambda o: o.author, lambda o: o.text),
    'core.ObjectPhoto': (lambda o: o.uploaded_by, lambda o: o.caption),
    'core.ObjectVideo': (lambda o: o.uploaded_by, lambda o: o.title),
    'ads.AdCampaign': (lambda o: o.advertiser, lambda o: o.name),
}


def resolve_report_target(object_id: str):
    """Find the reported object across reportable models.

    Returns (object_type, reported_profile, excerpt) or None when the ULID
    does not match any reportable object.
    """
    for label, (get_author, get_excerpt) in REPORTABLE_TYPES.items():
        model = apps.get_model(label)
        obj = model.objects.filter(pk=object_id).first()
        if obj is None:
            continue
        try:
            author = get_author(obj)
        except Exception:
            author = None
        try:
            excerpt = (get_excerpt(obj) or '')[:500]
        except Exception:
            excerpt = ''
        return obj._meta.model_name, author, excerpt
    return None
