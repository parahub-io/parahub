"""
Sitemap URL feeds for member-created content: marketplace listings, events and
establishment pages.

Why one cross-app module instead of a feed per app: `/api/v1/items/` registers
`/{id}/` before anything a literal `sitemap-urls` route could claim, so the feed
would resolve as an item lookup for the id "sitemap-urls". Beyond that the three
feeds share one policy — no demo rows, no synthetic authors, locale-less
canonical paths — and that policy is easier to keep honest in one place. CMS and
transit keep their own feeds; their queries have nothing in common with these.

Every feed returns [{loc, lastmod?}] WITHOUT a locale prefix. The frontend source
(server/api/__sitemap__/urls.ts) emits one canonical entry per page and each page
carries its own hreflang cluster, so locales are never multiplied here.
"""


import logging

from django.db.models import Q
from django.utils import timezone

from core.models import ObjectPhoto
from geo.models import Establishment, Event
from identity.visibility import exclude_test_authors
from market.models import Item
from ninja import Router

logger = logging.getLogger(__name__)

router = Router(tags=["Sitemap"])


def _exclude_demo(qs):
    """Drop seeded demo rows.

    `__contains` rather than `attributes__demo=True`: a plain lookup evaluates to
    NULL on rows where the key is absent, and NOT NULL is NULL — which would
    exclude every row instead of none.
    """
    return (qs.exclude(attributes__contains={'demo': True})
              .exclude(attributes__has_key='__demo_seed'))


@router.get('/items/', auth=None)
def item_sitemap_urls(request):
    """Public marketplace listings. Public, no auth.

    `visibility=PUBLIC` is the author's own answer to "may search engines see
    this", so it is the whole gate here; `is_active` keeps paused and sold
    listings out of the feed. A listing that goes inactive after being indexed is
    not a stale entry — the page keeps rendering and flips its Offer JSON-LD to
    `Discontinued`, which is exactly what a marketplace should tell a crawler.
    """
    qs = _exclude_demo(
        Item.objects.filter(is_active=True, visibility=Item.Visibility.PUBLIC)
    )
    qs = exclude_test_authors(qs, field='owner')
    return [
        {'loc': f'/market/{item_id}', 'lastmod': updated.isoformat() if updated else None}
        for item_id, updated in qs.values_list('id', 'updated_at').iterator()
    ]


@router.get('/events/', auth=None)
def event_sitemap_urls(request):
    """Published events that have not ended yet. Public, no auth.

    Past events keep their page and stay indexable through in-app links — they
    just stop being advertised, because an Event rich result is only useful while
    the event is ahead. Events with no end time are judged by their start.
    """
    now = timezone.now()
    qs = _exclude_demo(
        Event.objects.filter(status=Event.Status.PUBLISHED).filter(
            Q(ends_at__gte=now) | Q(ends_at__isnull=True, starts_at__gte=now)
        )
    )
    qs = exclude_test_authors(qs, field='organizer')
    return [
        {'loc': f'/events/{event_id}', 'lastmod': updated.isoformat() if updated else None}
        for event_id, updated in qs.values_list('id', 'updated_at').iterator()
    ]


@router.get('/orgs/', auth=None)
def establishment_sitemap_urls(request):
    """Establishment pages that carry content of their own. Public, no auth.

    NOT every active establishment: the directory is seeded from public map data
    and most rows are a name and a point — thousands of near-empty pages that
    duplicate their upstream source, dilute the site's quality signal and spend
    crawl budget that transit stops (which do carry unique data) need.

    An establishment earns its entry by holding something a reader came for:
    a description, a photo, a verification, a member, a mini-site, a published
    post, or a live listing (offered by it or posted at it). The set grows by
    itself as real places claim their card, so this needs no periodic revisit.
    """
    qs = _exclude_demo(
        Establishment.objects.filter(is_active=True).filter(
            Q(is_verified=True)
            | (Q(description__isnull=False) & ~Q(description=''))
            # ObjectPhoto carries no object_type — the ULID is unique platform-wide.
            | Q(id__in=ObjectPhoto.objects.values('object_id'))
            | ~Q(photos=[])
            | Q(memberships__isnull=False)
            | Q(site__is_active=True)
            | Q(blog_posts__status='published')
            | Q(items__is_active=True, items__visibility=Item.Visibility.PUBLIC)
            | Q(posted_items__is_active=True, posted_items__visibility=Item.Visibility.PUBLIC)
        )
    )
    qs = exclude_test_authors(qs, field='owner')
    return [
        {'loc': f'/org/{slug}', 'lastmod': updated.isoformat() if updated else None}
        # distinct(): the earned test spans reverse relations, so a place with
        # three members would otherwise be listed three times.
        for slug, updated in qs.values_list('slug', 'updated_at').distinct().iterator()
    ]
