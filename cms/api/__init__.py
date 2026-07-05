"""
CMS endpoints — split by concern from the former single api.py.
Importing the endpoint modules registers their routes on the shared router.
"""

from .base import router
from . import posts, files, sites, pages, domains, sitemap, webhook  # noqa: E402,F401

# Re-exports for cms/tests.py (direct handler calls + schema imports).
from .posts import (  # noqa: F401
    MAX_POST_CONTENT_SIZE, PostCreateIn, PostUpdateIn,
    create_post, update_post, delete_post, list_posts, get_post, posts_rss,
)
from .sites import SiteUpdateIn, resolve_site, update_profile_site  # noqa: F401
from .pages import (  # noqa: F401
    SitePageCreateIn, SitePageUpdateIn,
    create_site_page, update_site_page, delete_site_page,
    list_site_pages, get_site_page_by_slug,
)
from .domains import CustomDomainIn, set_custom_domain  # noqa: F401

__all__ = ['router']
