"""
Sitemap URL feed over published CMS content.
"""


import logging



from ..models import Post, SitePage

from .base import router
from .helpers import _exclude_demo_pages, _exclude_demo_posts

logger = logging.getLogger(__name__)

@router.get('/sitemap-urls/', auth=None)
def sitemap_urls(request):
    """Return dynamic URLs for sitemap.xml generation. Public, no auth.
    Excludes all demo/test content — only real content enters search indexes.
    """
    urls = []

    # Published blog posts (exclude demo/test)
    posts = _exclude_demo_posts(
        Post.objects.filter(status='published')
    ).select_related('author', 'establishment').only(
        'slug', 'updated_at', 'published_at',
        'author__local_name', 'author__id',
        'establishment__slug', 'establishment__id',
    )
    for p in posts:
        if p.establishment:
            loc = f'/org/{p.establishment.slug}/blog/{p.slug}'
        elif p.author:
            loc = f'/u/{p.author.local_name}/blog/{p.slug}'
        else:
            loc = f'/blog/{p.slug}'
        urls.append({
            'loc': loc,
            'lastmod': (p.updated_at or p.published_at).isoformat() if (p.updated_at or p.published_at) else None,
        })

    # Published site pages (exclude demo/test)
    site_pages = _exclude_demo_pages(
        SitePage.objects.filter(is_published=True, site__is_active=True)
    ).select_related('site__establishment', 'site__profile')
    for sp in site_pages:
        site = sp.site
        if site.establishment:
            loc = f'/org/{site.establishment.slug}/{sp.slug}'
        elif site.profile:
            loc = f'/u/{site.profile.local_name}/{sp.slug}'
        else:
            continue
        urls.append({
            'loc': loc,
            'lastmod': sp.updated_at.isoformat() if sp.updated_at else None,
        })

    # Org blog indexes (only establishments with non-demo published posts)
    est_slugs = (
        _exclude_demo_posts(Post.objects.filter(status='published', establishment__isnull=False))
        .values_list('establishment__slug', flat=True).distinct()
    )
    for slug in est_slugs:
        urls.append({'loc': f'/org/{slug}/blog'})

    # User blog indexes (only profiles with non-demo published posts)
    author_names = (
        _exclude_demo_posts(Post.objects.filter(status='published', establishment__isnull=True, author__isnull=False))
        .values_list('author__local_name', flat=True).distinct()
    )
    for name in author_names:
        urls.append({'loc': f'/u/{name}/blog'})

    return urls
