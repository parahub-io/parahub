"""
Sitemap URL feeds for transit routes and stops.
"""


import logging
from collections import defaultdict
from django.core.cache import cache

from geo.models import Stop, Route


from .base import router
from .helpers import LINE_CANONICAL_ORDER, _physical_pole_clusters, line_key_fields

logger = logging.getLogger(__name__)

@router.get("/transit/sitemap-urls/", auth=None)
def transit_sitemap_urls(request):
    """Locale-agnostic public route URLs for sitemap.xml. Public, no auth.

    One URL per public LINE: path-variants (percursos) collapse to their
    canonical (lowest path_type) representative via the same line_key_fields /
    LINE_CANONICAL_ORDER SSOT as search & discover, so the minor feeders that
    rel=canonical away on the route page never enter the sitemap as duplicates.

    Returns [{loc}] WITHOUT a locale prefix; @nuxtjs/sitemap multiplies each
    path across the locales and adds the hreflang alternates. lastmod is omitted
    on purpose — Route carries no per-record timestamp, only the feed's coarse
    import time. Routes with no Place / no slug can't form a URL and are skipped.
    """
    rows = (
        Route.objects.filter(place__isnull=False)
        .exclude(slug="")
        .exclude(place__slug="")
        # path_type asc → the canonical variant of each line is the first row
        # seen for its key (ties broken by source_id), matching search collapse.
        .order_by(*LINE_CANONICAL_ORDER)
        .values_list("id", "agency_id", "line_id", "short_name", "slug", "place__slug")
    )
    seen: set = set()
    urls = []
    for rid, agency_id, line_id, short_name, slug, place_slug in rows:
        key = line_key_fields(rid, agency_id, line_id, short_name)
        if key in seen:
            continue
        seen.add(key)
        urls.append({"loc": f"/transit/route/{place_slug}/{slug}"})
    return urls

@router.get("/transit/stop-sitemap-urls/", auth=None)
def transit_stop_sitemap_urls(request):
    """Locale-agnostic public STOP URLs for sitemap.xml. Public, no auth.

    Stop pages carry NO crawlable inbound links — route lists and /transit search
    open them via JS navigateTo (<button @click>), not <a>, and the only <a>/NuxtLink
    to a stop is the sibling-pole link ON another stop page. So the sitemap is the
    ONLY discovery path into the stop graph: every distinct boarding point must be
    listed here or it stays unindexed.

    One URL per physical boarding point:
      - ungrouped stops → one each (no group → no sibling links → sitemap-only);
      - grouped stops → physical pole clusters, partitioned by the SAME
        _physical_pole_clusters merge the stop page applies, so co-located
        cross-operator poles that render an IDENTICAL merged page collapse to one
        representative, while a group's distinct poles (opposite directions,
        interchanges — each its own page, reachable via the on-page sibling links)
        each keep their URL.
    Representative = lowest id among a cluster's url-able members (deterministic and
    stable across imports); a cluster with no url-able member can't form a URL and
    is skipped.

    Returns [{loc}] WITHOUT a locale prefix; @nuxtjs/sitemap multiplies each across
    locales and adds the hreflang alternates. lastmod is omitted on purpose — Stop
    carries no per-record timestamp, only the feed's coarse import time.

    Cached (1 h): the result feeds 6 per-locale sitemaps × N chunk files, so each
    sitemap crawl re-requests it dozens of times — without the cache every request
    re-scans ~56k grouped rows and re-clusters every group.
    """
    cache_key = "transit:sitemap:stop_urls:v1"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    urls = []

    # Ungrouped boarding points — one URL each (no sibling links of their own).
    for place_slug, slug in (
        Stop.objects.filter(group__isnull=True, place__isnull=False, location_type__lte=1)
        .exclude(slug="").exclude(place__slug="")
        .values_list("place__slug", "slug")
        .iterator()
    ):
        urls.append({"loc": f"/transit/stop/{place_slug}/{slug}"})

    # Grouped boarding points — cluster each group's members exactly as the stop
    # page does, then emit one url-able representative per physical pole cluster.
    by_group = defaultdict(list)
    for s in (
        Stop.objects.filter(group__isnull=False, location_type__lte=1)
        .select_related("place")
        .only("id", "agency_id", "location", "slug", "group_id", "place__slug")
        .iterator()
    ):
        by_group[s.group_id].append(s)
    for members in by_group.values():
        for cluster in _physical_pole_clusters(members):
            urlable = [m for m in cluster if m.slug and m.place_id and m.place.slug]
            if not urlable:
                continue
            rep = min(urlable, key=lambda m: m.id)
            urls.append({"loc": f"/transit/stop/{rep.place.slug}/{rep.slug}"})

    cache.set(cache_key, urls, 3600)
    return urls
