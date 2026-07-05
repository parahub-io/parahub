"""
Mini-sites: public resolve + establishment/profile site settings.
"""


from typing import List, Optional
import logging

from ninja import Schema
from ninja.errors import HttpError

from django.db.models import Q
from django.shortcuts import get_object_or_404

from parahub.auth import ProfileAuth, OptionalProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from identity.models import Profile
from geo.permissions import get_establishment_for_action, SIGNING_ROLES
from core.models import ObjectPhoto
from ..models import Site

from .base import router
from .helpers import _require_profile_owner

logger = logging.getLogger(__name__)

VALID_NAV_SECTION_TYPES = {'blog', 'gallery', 'items', 'contact'}

class SiteNavSection(Schema):
    type: str
    order: int

class SiteOut(Schema):
    id: str
    object_type: str = 'site'
    accent_color: str
    hero_text: str
    hero_text_html: str
    hero_image_id: str
    hero_image_url: Optional[str] = None
    logo_url: Optional[str] = None
    nav_sections: list
    is_active: bool
    custom_domain: str
    custom_domain_verified: bool = False
    custom_domain_ssl_ready: bool = False
    # Owner info
    establishment_id: Optional[str] = None
    establishment_name: Optional[str] = None
    establishment_slug: Optional[str] = None
    profile_id: Optional[str] = None
    profile_name: Optional[str] = None
    profile_local_name: Optional[str] = None
    # Navigation pages
    nav_pages: List[dict] = []

class SiteUpdateIn(Schema):
    accent_color: Optional[str] = None
    hero_text: Optional[str] = None
    hero_image_id: Optional[str] = None
    nav_sections: Optional[List[SiteNavSection]] = None
    is_active: Optional[bool] = None

def _site_to_out(site: Site) -> SiteOut:
    hero_url = None
    if site.hero_image_id:
        photo = ObjectPhoto.objects.filter(id=site.hero_image_id).first()
        if photo:
            hero_url = photo.image.url

    nav_pages = [{
        'id': p.id,
        'title': p.title,
        'slug': p.slug,
        'order': p.order,
        'is_homepage': p.is_homepage,
        'content_html': p.content_html if p.is_homepage else '',
    } for p in site.pages.filter(is_published=True).filter(
        Q(show_in_nav=True) | Q(is_homepage=True)
    ).order_by('order')]

    est = site.establishment
    profile = site.profile

    logo_url = None
    if est and est.logo_url:
        logo_url = est.logo_url
    elif profile and profile.avatar:
        logo_url = profile.avatar.url

    return SiteOut(
        id=site.id,
        accent_color=site.accent_color,
        hero_text=site.hero_text,
        hero_text_html=site.hero_text_html,
        hero_image_id=site.hero_image_id,
        hero_image_url=hero_url,
        logo_url=logo_url,
        nav_sections=site.nav_sections or [],
        is_active=site.is_active,
        custom_domain=site.custom_domain,
        custom_domain_verified=site.custom_domain_verified,
        custom_domain_ssl_ready=site.custom_domain_ssl_ready,
        establishment_id=est.id if est else None,
        establishment_name=est.name if est else None,
        establishment_slug=est.slug if est else None,
        profile_id=profile.id if profile else None,
        profile_name=profile.display_name if profile else None,
        profile_local_name=profile.local_name if profile else None,
        nav_pages=nav_pages,
    )

def _get_site_for_est(establishment_id: str, auto_create: bool = True) -> Site:
    """Get or auto-create site for establishment."""
    from geo.models import Establishment
    est = get_object_or_404(Establishment, id=establishment_id, is_active=True)
    if auto_create:
        site, _ = Site.objects.get_or_create(establishment=est)
    else:
        site = Site.objects.filter(establishment=est).first()
        if not site:
            raise HttpError(404, "Site not found")
    return site

def _get_site_for_profile(profile_name: str, auto_create: bool = True) -> Site:
    """Get or auto-create site for profile by local_name."""
    from identity.models import Profile
    profile = get_object_or_404(Profile, local_name=profile_name)
    if auto_create:
        site, _ = Site.objects.get_or_create(profile=profile)
    else:
        site = Site.objects.filter(profile=profile).first()
        if not site:
            raise HttpError(404, "Site not found")
    return site

@router.get('/sites/resolve/', response=SiteOut, auth=None)
def resolve_site(request, slug: str = '', type: str = 'org', domain: str = ''):
    """
    Resolve a site by subdomain slug OR custom domain.
    Used by Nuxt to fetch site config from Host header.
    - slug + type: subdomain resolution (*.org.parahub.io / *.u.parahub.io)
    - domain: custom domain resolution (cafe-central.pt)
    """
    if domain:
        # Custom domain lookup
        site = Site.objects.filter(
            custom_domain=domain.lower().strip(),
            custom_domain_verified=True,
            is_active=True,
        ).select_related('establishment', 'profile').first()
        if not site:
            raise HttpError(404, "Site not found")
        return _site_to_out(site)

    if not slug:
        raise HttpError(400, "slug or domain parameter required")

    if type == 'org':
        from geo.models import Establishment
        est = Establishment.objects.filter(slug=slug, is_active=True).first()
        if not est:
            raise HttpError(404, "Site not found")
        site = Site.objects.filter(establishment=est, is_active=True).select_related('establishment', 'profile').first()
    else:
        from identity.models import Profile
        profile = Profile.objects.filter(local_name=slug).first()
        if not profile:
            raise HttpError(404, "Site not found")
        site = Site.objects.filter(profile=profile, is_active=True).select_related('establishment', 'profile').first()

    if not site:
        raise HttpError(404, "Site not found")

    return _site_to_out(site)

@router.get('/sites/by-establishment/{establishment_id}/', response=SiteOut, auth=OptionalProfileAuth())
def get_site(request, establishment_id: str):
    """Get site config for an establishment. Auto-creates only for authenticated users."""
    site = _get_site_for_est(establishment_id, auto_create=bool(request.auth))
    return _site_to_out(site)

@router.patch('/sites/by-establishment/{establishment_id}/', response=SiteOut, auth=ProfileAuth())
@ratelimit(group='cms:update_site', key=user_or_ip, rate='30/h')
def update_site(request, establishment_id: str, payload: SiteUpdateIn):
    """Update site settings. OWNER/ADMIN only."""
    profile: Profile = request.auth
    get_establishment_for_action(establishment_id, profile, SIGNING_ROLES)

    site = _get_site_for_est(establishment_id)

    if payload.accent_color is not None:
        import re as _re
        color = payload.accent_color.strip()
        if _re.match(r'^#[0-9a-fA-F]{6}$', color):
            site.accent_color = color
    if payload.hero_text is not None:
        site.hero_text = payload.hero_text
    if payload.hero_image_id is not None:
        site.hero_image_id = payload.hero_image_id[:26]
    if payload.nav_sections is not None:
        for s in payload.nav_sections:
            if s.type not in VALID_NAV_SECTION_TYPES:
                raise HttpError(400, f"Invalid section type: {s.type}")
        site.nav_sections = [s.dict() for s in payload.nav_sections]
    if payload.is_active is not None:
        site.is_active = payload.is_active

    site.save()
    return _site_to_out(site)

@router.get('/sites/by-profile/{profile_name}/', response=SiteOut, auth=OptionalProfileAuth())
def get_profile_site(request, profile_name: str):
    """Get site config for a profile. Auto-creates only for authenticated users."""
    site = _get_site_for_profile(profile_name, auto_create=bool(request.auth))
    return _site_to_out(site)

@router.patch('/sites/by-profile/{profile_name}/', response=SiteOut, auth=ProfileAuth())
@ratelimit(group='cms:update_site', key=user_or_ip, rate='30/h')
def update_profile_site(request, profile_name: str, payload: SiteUpdateIn):
    """Update site settings. Profile owner only."""
    _require_profile_owner(request, profile_name)
    site = _get_site_for_profile(profile_name)

    if payload.accent_color is not None:
        import re as _re
        color = payload.accent_color.strip()
        if _re.match(r'^#[0-9a-fA-F]{6}$', color):
            site.accent_color = color
    if payload.hero_text is not None:
        site.hero_text = payload.hero_text
    if payload.hero_image_id is not None:
        site.hero_image_id = payload.hero_image_id[:26]
    if payload.nav_sections is not None:
        for s in payload.nav_sections:
            if s.type not in VALID_NAV_SECTION_TYPES:
                raise HttpError(400, f"Invalid section type: {s.type}")
        site.nav_sections = [s.dict() for s in payload.nav_sections]
    if payload.is_active is not None:
        site.is_active = payload.is_active

    site.save()
    return _site_to_out(site)
