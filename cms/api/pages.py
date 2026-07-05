"""
Mini-site pages: CRUD for establishment and profile sites.
"""


from typing import List, Optional
from datetime import datetime
import logging

from ninja import Schema
from ninja.errors import HttpError

from django.shortcuts import get_object_or_404

from parahub.auth import ProfileAuth, OptionalProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from identity.models import Profile
from geo.permissions import get_establishment_for_action, SIGNING_ROLES
from ..models import SitePage

from .base import router
from .helpers import _require_profile_owner
from .sites import _get_site_for_est, _get_site_for_profile

logger = logging.getLogger(__name__)

MAX_PAGE_CONTENT_SIZE = 200_000

MAX_PAGES_PER_SITE = 50

class SitePageOut(Schema):
    id: str
    object_type: str = 'site_page'
    title: str
    slug: str
    content: str
    content_html: str
    order: int
    show_in_nav: bool
    is_published: bool
    is_homepage: bool = False
    created_at: datetime
    updated_at: datetime

class SitePageCreateIn(Schema):
    title: str
    slug: str = ''
    content: str = ''
    order: int = 0
    show_in_nav: bool = True
    is_published: bool = True
    is_homepage: bool = False

class SitePageUpdateIn(Schema):
    title: Optional[str] = None
    slug: Optional[str] = None
    content: Optional[str] = None
    order: Optional[int] = None
    show_in_nav: Optional[bool] = None
    is_published: Optional[bool] = None
    is_homepage: Optional[bool] = None

def _page_to_out(page: SitePage) -> SitePageOut:
    return SitePageOut(
        id=page.id,
        title=page.title,
        slug=page.slug,
        content=page.content,
        content_html=page.content_html,
        order=page.order,
        show_in_nav=page.show_in_nav,
        is_published=page.is_published,
        is_homepage=page.is_homepage,
        created_at=page.created_at,
        updated_at=page.updated_at,
    )

@router.get('/sites/by-establishment/{establishment_id}/pages/', response=List[SitePageOut], auth=OptionalProfileAuth())
def list_site_pages(request, establishment_id: str):
    """List pages for a site. Owners see all, public sees published only."""
    site = _get_site_for_est(establishment_id, auto_create=False)
    qs = site.pages.all().order_by('order')
    show_all = False
    if request.auth and site.establishment:
        try:
            get_establishment_for_action(site.establishment.id, request.auth, SIGNING_ROLES)
            show_all = True
        except Exception:
            pass
    if not show_all:
        qs = qs.filter(is_published=True)
    return [_page_to_out(p) for p in qs]

@router.get('/sites/by-establishment/{establishment_id}/pages/{page_id}/', response=SitePageOut, auth=None)
def get_site_page(request, establishment_id: str, page_id: str):
    """Get a single page by ID."""
    site = _get_site_for_est(establishment_id)
    page = get_object_or_404(site.pages, id=page_id)
    if not page.is_published:
        raise HttpError(404, "Page not found")
    return _page_to_out(page)

@router.get('/sites/by-establishment/{establishment_id}/pages/by-slug/{slug}/', response=SitePageOut, auth=None)
def get_site_page_by_slug(request, establishment_id: str, slug: str):
    """Get a page by slug (for rendering)."""
    site = _get_site_for_est(establishment_id)
    page = site.pages.filter(slug=slug, is_published=True).first()
    if not page:
        raise HttpError(404, "Page not found")
    return _page_to_out(page)

@router.post('/sites/by-establishment/{establishment_id}/pages/', response=SitePageOut, auth=ProfileAuth())
@ratelimit(group='cms:create_page', key=user_or_ip, rate='30/h')
def create_site_page(request, establishment_id: str, payload: SitePageCreateIn):
    """Create a custom page. OWNER/ADMIN only."""
    profile: Profile = request.auth
    get_establishment_for_action(establishment_id, profile, SIGNING_ROLES)

    if len(payload.content) > MAX_PAGE_CONTENT_SIZE:
        raise HttpError(400, f"Content too large (max {MAX_PAGE_CONTENT_SIZE // 1000}KB)")

    site = _get_site_for_est(establishment_id)

    if site.pages.count() >= MAX_PAGES_PER_SITE:
        raise HttpError(400, f"Maximum {MAX_PAGES_PER_SITE} pages per site")

    page = SitePage(
        site=site,
        title=payload.title.strip()[:200],
        slug=payload.slug.strip()[:200] if payload.slug else '',
        content=payload.content,
        order=payload.order,
        show_in_nav=payload.show_in_nav,
        is_published=payload.is_published,
        is_homepage=payload.is_homepage,
    )
    page.save()
    return _page_to_out(page)

@router.patch('/sites/by-establishment/{establishment_id}/pages/{page_id}/', response=SitePageOut, auth=ProfileAuth())
@ratelimit(group='cms:update_page', key=user_or_ip, rate='60/h')
def update_site_page(request, establishment_id: str, page_id: str, payload: SitePageUpdateIn):
    """Update a page. OWNER/ADMIN only."""
    profile: Profile = request.auth
    get_establishment_for_action(establishment_id, profile, SIGNING_ROLES)

    if payload.content is not None and len(payload.content) > MAX_PAGE_CONTENT_SIZE:
        raise HttpError(400, f"Content too large (max {MAX_PAGE_CONTENT_SIZE // 1000}KB)")

    site = _get_site_for_est(establishment_id)
    page = get_object_or_404(site.pages, id=page_id)

    if payload.title is not None:
        page.title = payload.title.strip()[:200]
    if payload.slug is not None:
        new_slug = payload.slug.strip()[:200]
        if new_slug and new_slug != page.slug:
            if site.pages.filter(slug=new_slug).exclude(id=page.id).exists():
                raise HttpError(400, f"Slug '{new_slug}' already taken")
            page.slug = new_slug
    if payload.content is not None:
        page.content = payload.content
    if payload.order is not None:
        page.order = payload.order
    if payload.show_in_nav is not None:
        page.show_in_nav = payload.show_in_nav
    if payload.is_published is not None:
        page.is_published = payload.is_published
    if payload.is_homepage is not None:
        page.is_homepage = payload.is_homepage

    page.save()
    return _page_to_out(page)

@router.delete('/sites/by-establishment/{establishment_id}/pages/{page_id}/', auth=ProfileAuth())
@ratelimit(group='cms:delete_page', key=user_or_ip, rate='60/h')
def delete_site_page(request, establishment_id: str, page_id: str):
    """Delete a page. OWNER/ADMIN only."""
    profile: Profile = request.auth
    get_establishment_for_action(establishment_id, profile, SIGNING_ROLES)

    site = _get_site_for_est(establishment_id)
    page = get_object_or_404(site.pages, id=page_id)
    page.delete()
    return {'ok': True}

@router.get('/sites/by-profile/{profile_name}/pages/', response=List[SitePageOut], auth=OptionalProfileAuth())
def list_profile_site_pages(request, profile_name: str):
    """List pages for a profile site. Owner sees all, public sees published only."""
    site = _get_site_for_profile(profile_name, auto_create=False)
    qs = site.pages.all().order_by('order')
    if not (request.auth and (request.auth.local_name == profile_name or request.auth.account.is_superuser)):
        qs = qs.filter(is_published=True)
    return [_page_to_out(p) for p in qs]

@router.get('/sites/by-profile/{profile_name}/pages/by-slug/{slug}/', response=SitePageOut, auth=None)
def get_profile_site_page_by_slug(request, profile_name: str, slug: str):
    """Get a page by slug (for rendering)."""
    site = _get_site_for_profile(profile_name)
    page = site.pages.filter(slug=slug, is_published=True).first()
    if not page:
        raise HttpError(404, "Page not found")
    return _page_to_out(page)

@router.post('/sites/by-profile/{profile_name}/pages/', response=SitePageOut, auth=ProfileAuth())
@ratelimit(group='cms:create_page', key=user_or_ip, rate='30/h')
def create_profile_site_page(request, profile_name: str, payload: SitePageCreateIn):
    """Create a custom page. Profile owner only."""
    _require_profile_owner(request, profile_name)

    if len(payload.content) > MAX_PAGE_CONTENT_SIZE:
        raise HttpError(400, f"Content too large (max {MAX_PAGE_CONTENT_SIZE // 1000}KB)")

    site = _get_site_for_profile(profile_name)

    if site.pages.count() >= MAX_PAGES_PER_SITE:
        raise HttpError(400, f"Maximum {MAX_PAGES_PER_SITE} pages per site")

    page = SitePage(
        site=site,
        title=payload.title.strip()[:200],
        slug=payload.slug.strip()[:200] if payload.slug else '',
        content=payload.content,
        order=payload.order,
        show_in_nav=payload.show_in_nav,
        is_published=payload.is_published,
        is_homepage=payload.is_homepage,
    )
    page.save()
    return _page_to_out(page)

@router.patch('/sites/by-profile/{profile_name}/pages/{page_id}/', response=SitePageOut, auth=ProfileAuth())
@ratelimit(group='cms:update_page', key=user_or_ip, rate='60/h')
def update_profile_site_page(request, profile_name: str, page_id: str, payload: SitePageUpdateIn):
    """Update a page. Profile owner only."""
    _require_profile_owner(request, profile_name)

    if payload.content is not None and len(payload.content) > MAX_PAGE_CONTENT_SIZE:
        raise HttpError(400, f"Content too large (max {MAX_PAGE_CONTENT_SIZE // 1000}KB)")

    site = _get_site_for_profile(profile_name)
    page = get_object_or_404(site.pages, id=page_id)

    if payload.title is not None:
        page.title = payload.title.strip()[:200]
    if payload.slug is not None:
        new_slug = payload.slug.strip()[:200]
        if new_slug and new_slug != page.slug:
            if site.pages.filter(slug=new_slug).exclude(id=page.id).exists():
                raise HttpError(400, f"Slug '{new_slug}' already taken")
            page.slug = new_slug
    if payload.content is not None:
        page.content = payload.content
    if payload.order is not None:
        page.order = payload.order
    if payload.show_in_nav is not None:
        page.show_in_nav = payload.show_in_nav
    if payload.is_published is not None:
        page.is_published = payload.is_published
    if payload.is_homepage is not None:
        page.is_homepage = payload.is_homepage

    page.save()
    return _page_to_out(page)

@router.delete('/sites/by-profile/{profile_name}/pages/{page_id}/', auth=ProfileAuth())
@ratelimit(group='cms:delete_page', key=user_or_ip, rate='60/h')
def delete_profile_site_page(request, profile_name: str, page_id: str):
    """Delete a page. Profile owner only."""
    _require_profile_owner(request, profile_name)
    site = _get_site_for_profile(profile_name)
    page = get_object_or_404(site.pages, id=page_id)
    page.delete()
    return {'ok': True}
