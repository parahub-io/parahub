"""
Blog posts: list/detail/CRUD, batch moderation, RSS.
"""


from typing import List, Optional
from datetime import datetime
import logging

from ninja import Schema
from ninja.errors import HttpError

from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import Case, Q, When
from django.shortcuts import get_object_or_404
from django.utils import timezone

from parahub.auth import ProfileAuth, OptionalProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from identity.models import Profile
from geo.permissions import get_establishment_for_action, POSTING_ROLES, SIGNING_ROLES
from core.models import ObjectPhoto, ObjectFile
from ..models import Post

from .base import router
from .helpers import _check_wot3, _exclude_demo_posts, _is_demo_obj, _is_privileged_user

logger = logging.getLogger(__name__)

# Content size limits
MAX_POST_CONTENT_SIZE = 200_000  # ~200KB markdown

class PostListOut(Schema):
    id: str
    object_type: str = 'post'
    title: str
    slug: str
    excerpt: str
    status: str
    language: str
    published_at: Optional[datetime] = None
    is_pinned: bool
    allow_comments: bool
    allow_tips: bool
    subscribers_only: bool = False
    comments_count: int
    author_id: str
    author_hna: str
    author_local_name: str = ''
    author_display_name: Optional[str] = None
    author_avatar: Optional[str] = None
    establishment_id: Optional[str] = None
    establishment_name: Optional[str] = None
    establishment_slug: Optional[str] = None
    featured_image_url: Optional[str] = None
    tags: List[dict] = []
    available_languages: List[dict] = []  # [{language, slug, id}] — other translations
    is_demo: bool = False
    publish_order: Optional[int] = None
    approved_at: Optional[datetime] = None
    approved_by_id: Optional[str] = None
    approved_by_name: Optional[str] = None
    translation_of_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class TranslationRef(Schema):
    id: str
    language: str
    slug: str
    title: str

class PostDetailOut(PostListOut):
    content: str
    content_html: str
    meta_description: str
    featured_image_id: str
    translation_of_id: Optional[str] = None
    translations: List[TranslationRef] = []
    pgp_signature: str
    files: List[dict] = []
    updated_at: datetime
    # True when this is a subscribers_only post the viewer cannot unlock — the
    # body fields above are blanked and the frontend shows the excerpt + a prompt.
    locked: bool = False

class PostCreateIn(Schema):
    title: str
    content: str
    establishment_id: Optional[str] = None
    status: str = 'draft'
    language: str = 'en'
    meta_description: str = ''
    featured_image_id: str = ''
    is_pinned: bool = False
    allow_comments: bool = True
    allow_tips: bool = True
    subscribers_only: bool = False
    translation_of_id: Optional[str] = None
    tag_ids: List[str] = []
    publish_order: Optional[int] = None

class PostUpdateIn(Schema):
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    language: Optional[str] = None
    meta_description: Optional[str] = None
    featured_image_id: Optional[str] = None
    is_pinned: Optional[bool] = None
    allow_comments: Optional[bool] = None
    allow_tips: Optional[bool] = None
    subscribers_only: Optional[bool] = None
    translation_of_id: Optional[str] = None
    tag_ids: Optional[List[str]] = None
    publish_order: Optional[int] = None

class BatchPostsIn(Schema):
    post_ids: List[str]

def _post_to_list(post: Post, translations_map: dict = None, photos_map: dict = None) -> PostListOut:
    author = post.author
    est = post.establishment

    featured_url = None
    if post.featured_image_id:
        if photos_map is not None:
            featured_url = photos_map.get(post.featured_image_id)
        else:
            photo = ObjectPhoto.objects.filter(id=post.featured_image_id).first()
            if photo:
                featured_url = photo.image.url

    tag_list = [{'id': t.id, 'name': t.name, 'slug': t.slug} for t in post.tags.all()]

    # Available translations
    available = []
    if translations_map is not None and post.id in translations_map:
        available = translations_map[post.id]
    else:
        # Fallback: query translations for this original
        original_id = post.translation_of_id or post.id
        siblings = Post.objects.filter(
            Q(id=original_id) | Q(translation_of_id=original_id),
            status='published',
        ).exclude(id=post.id).only('id', 'language', 'slug')
        available = [{'id': s.id, 'language': s.language, 'slug': s.slug} for s in siblings]

    approver = post.approved_by
    return PostListOut(
        id=post.id,
        title=post.title,
        slug=post.slug,
        excerpt=post.excerpt,
        status=post.status,
        language=post.language,
        published_at=post.published_at,
        is_pinned=post.is_pinned,
        allow_comments=post.allow_comments,
        allow_tips=post.allow_tips,
        subscribers_only=post.subscribers_only,
        comments_count=post.comments_count,
        author_id=author.id,
        author_hna=author.hna,
        author_local_name=author.local_name,
        author_display_name=author.display_name or None,
        author_avatar=author.avatar.url if author.avatar else None,
        establishment_id=est.id if est else None,
        establishment_name=est.name if est else None,
        establishment_slug=est.slug if est else None,
        featured_image_url=featured_url,
        tags=tag_list,
        available_languages=available,
        is_demo=_is_demo_obj(post),
        publish_order=post.publish_order,
        approved_at=post.approved_at,
        approved_by_id=approver.id if approver else None,
        approved_by_name=(approver.display_name or approver.hna) if approver else None,
        translation_of_id=post.translation_of_id,
        created_at=post.created_at,
        updated_at=post.updated_at,
    )

def _post_to_detail(post: Post, viewer_profile: Profile = None) -> PostDetailOut:
    author = post.author
    est = post.establishment

    # Restricted-content gate. A subscribers_only post serves its full body only to
    # the author, to a superuser, and to a live subscriber of the author
    # (finance.Subscription). Everyone else gets the excerpt + a locked flag — the
    # body is stripped HERE, server-side, so it never reaches a non-subscriber's
    # client (SSR or JSON). Org posts gate by their (human) author's subscribers.
    locked = False
    if post.subscribers_only:
        is_author = viewer_profile is not None and viewer_profile.id == post.author_id
        is_super = viewer_profile is not None and viewer_profile.account.is_superuser
        if not (is_author or is_super):
            from finance.services import is_live_subscriber
            locked = not is_live_subscriber(viewer_profile, author)

    featured_url = None
    if post.featured_image_id:
        photo = ObjectPhoto.objects.filter(id=post.featured_image_id).first()
        if photo:
            featured_url = photo.image.url

    tag_list = [{'id': t.id, 'name': t.name, 'slug': t.slug} for t in post.tags.all()]

    files = ObjectFile.objects.filter(object_id=post.id).order_by('order', 'created_at')
    file_list = [{
        'id': f.id,
        'filename': f.filename,
        'mime_type': f.mime_type,
        'size_bytes': f.size_bytes,
        'url': f.file.url,
        'order': f.order,
    } for f in files]

    # Gather sibling translations: if this is a translation, find siblings of the original.
    # If this is an original, find its translations.
    translations = []
    original_id = post.translation_of_id or post.id
    siblings = Post.objects.filter(
        Q(id=original_id) | Q(translation_of_id=original_id),
        status='published',
    ).exclude(id=post.id).only('id', 'language', 'slug', 'title')
    for s in siblings:
        translations.append(TranslationRef(id=s.id, language=s.language, slug=s.slug, title=s.title))

    approver = post.approved_by
    return PostDetailOut(
        id=post.id,
        title=post.title,
        slug=post.slug,
        excerpt=post.excerpt,
        status=post.status,
        language=post.language,
        published_at=post.published_at,
        is_pinned=post.is_pinned,
        allow_comments=post.allow_comments,
        allow_tips=post.allow_tips,
        subscribers_only=post.subscribers_only,
        comments_count=post.comments_count,
        author_id=author.id,
        author_hna=author.hna,
        author_local_name=author.local_name,
        author_display_name=author.display_name or None,
        author_avatar=author.avatar.url if author.avatar else None,
        establishment_id=est.id if est else None,
        establishment_name=est.name if est else None,
        establishment_slug=est.slug if est else None,
        featured_image_url=featured_url,
        tags=tag_list,
        is_demo=_is_demo_obj(post),
        publish_order=post.publish_order,
        approved_at=post.approved_at,
        approved_by_id=approver.id if approver else None,
        approved_by_name=(approver.display_name or approver.hna) if approver else None,
        created_at=post.created_at,
        content='' if locked else post.content,
        content_html='' if locked else post.content_html,
        meta_description=post.meta_description,
        featured_image_id=post.featured_image_id,
        translation_of_id=post.translation_of_id,
        translations=translations,
        pgp_signature='' if locked else post.pgp_signature,
        files=[] if locked else file_list,
        updated_at=post.updated_at,
        locked=locked,
    )

def _can_edit_post(post: Post, profile: Profile) -> bool:
    """Check if profile can edit/delete this post."""
    if post.author_id == profile.id:
        return True
    if profile.account.is_superuser:
        return True
    if post.establishment_id:
        from geo.permissions import get_user_role
        role = get_user_role(post.establishment, profile)
        return role in SIGNING_ROLES
    return False

@router.get('/posts/', response={200: dict}, auth=OptionalProfileAuth())
def list_posts(request, establishment_id: str = None, establishment_slug: str = None,
               author_id: str = None, author_name: str = None,
               tag: str = None, language: str = None,
               status: str = None, search: str = None):
    """
    Public post feed. Filters by establishment, author, tag, language.
    Drafts visible only to author/OWNER/ADMIN.
    """
    qs = Post.objects.select_related('author', 'establishment', 'approved_by').prefetch_related('tags')

    profile = getattr(request, 'auth_profile', None)

    # Filter by establishment
    if establishment_id:
        qs = qs.filter(establishment_id=establishment_id)
    elif establishment_slug:
        qs = qs.filter(establishment__slug=establishment_slug)

    # Filter by author
    if author_id:
        qs = qs.filter(author_id=author_id, establishment__isnull=True)
    elif author_name:
        qs = qs.filter(author__local_name=author_name, establishment__isnull=True)

    # Filter by tag slug
    if tag:
        qs = qs.filter(tags__slug=tag)

    # Filter by language
    if language:
        qs = qs.filter(language=language)

    # Full-text search on title + content (PostgreSQL FTS, portuguese config)
    if search:
        search_vector = (
            SearchVector('title', config='portuguese', weight='A') +
            SearchVector('content', config='portuguese', weight='B')
        )
        search_query = SearchQuery(search, config='portuguese', search_type='websearch')
        qs = qs.annotate(
            search=search_vector,
            rank=SearchRank(search_vector, search_query),
        ).filter(search=search_query)

    # Hide demo/test content from public users
    if not _is_privileged_user(request):
        qs = _exclude_demo_posts(qs)

    # Visibility: published only for public, drafts for owner/admin
    if status and status in ('draft', 'archived', 'all') and profile:
        # Show drafts/archived/all only if user can manage them
        if status != 'all':
            qs = qs.filter(status=status)
        qs = qs.filter(
            Q(author=profile) |
            Q(establishment__owner=profile) |
            Q(establishment__memberships__profile=profile,
              establishment__memberships__role__in=SIGNING_ROLES)
        ).distinct()
    else:
        qs = qs.filter(status='published')
        # In the public feed, hide translations — show only originals.
        # When filtering by explicit language, show all (including translations).
        if not language:
            qs = qs.filter(translation_of__isnull=True)

    # When searching, order by relevance instead of default ordering
    if search:
        qs = qs.order_by('-rank', '-published_at')

    # Apply pagination manually at DB level, then transform the page.
    # Management views (status='all', authenticated) may legitimately need
    # every post for a topic-grouped UI, so they get a higher cap.
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))
    max_page_size = 500 if (status == 'all' and profile) else 100
    if page_size > max_page_size:
        page_size = max_page_size
    offset = (page - 1) * page_size

    total = qs.count()
    posts = list(qs[offset:offset + page_size])

    # Batch-fetch translations for this page only
    post_ids = [p.id for p in posts]
    translations_map: dict = {pid: [] for pid in post_ids}
    if post_ids:
        siblings = Post.objects.filter(
            translation_of_id__in=post_ids, status='published',
        ).only('id', 'language', 'slug', 'translation_of_id')
        for s in siblings:
            translations_map[s.translation_of_id].append({
                'id': s.id, 'language': s.language, 'slug': s.slug,
            })

    # Batch-fetch featured photos for this page
    photo_ids = [p.featured_image_id for p in posts if p.featured_image_id]
    photos_map = {}
    if photo_ids:
        for photo in ObjectPhoto.objects.filter(id__in=photo_ids):
            photos_map[photo.id] = photo.image.url

    return {'items': [_post_to_list(p, translations_map, photos_map) for p in posts], 'count': total}

@router.get('/posts/rss/', auth=None)
def posts_rss(request, establishment_slug: str = None, author_name: str = None):
    """RSS 2.0 feed of published posts."""
    from django.http import HttpResponse
    from xml.sax.saxutils import escape as xml_escape

    qs = _exclude_demo_posts(
        Post.objects.filter(status='published')
    ).select_related('author', 'establishment').order_by('-published_at')

    if establishment_slug:
        qs = qs.filter(establishment__slug=establishment_slug)
    elif author_name:
        qs = qs.filter(author__local_name=author_name, establishment__isnull=True)

    posts = list(qs[:30])

    base = 'https://parahub.io'
    if establishment_slug:
        feed_title = f'Blog — {establishment_slug}'
        feed_link = f'{base}/org/{establishment_slug}/blog/'
    elif author_name:
        feed_title = f'Blog — {author_name}'
        feed_link = f'{base}/u/{author_name}/blog/'
    else:
        feed_title = 'Parahub Blog'
        feed_link = f'{base}/blog/'

    items = []
    for p in posts:
        if p.establishment and p.establishment.slug:
            link = f'{base}/org/{p.establishment.slug}/blog/{p.slug}'
        else:
            author_ln = p.author.local_name if p.author else ''
            link = f'{base}/u/{author_ln}/blog/{p.slug}'
        pub = p.published_at.strftime('%a, %d %b %Y %H:%M:%S +0000') if p.published_at else ''
        title = xml_escape(p.title or '')
        desc = xml_escape(p.excerpt or '')
        link = xml_escape(link)
        author_name_str = xml_escape(p.author.display_name or p.author.local_name or '')
        items.append(f'''    <item>
      <title>{title}</title>
      <link>{link}</link>
      <description>{desc}</description>
      <pubDate>{pub}</pubDate>
      <dc:creator>{author_name_str}</dc:creator>
      <guid isPermaLink="true">{link}</guid>
    </item>''')

    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{feed_title}</title>
    <link>{feed_link}</link>
    <description>{feed_title}</description>
    <language>{posts[0].language if posts else 'en'}</language>
    <atom:link href="{feed_link}rss/" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>'''

    return HttpResponse(xml, content_type='application/rss+xml; charset=utf-8')

@router.get('/posts/by-slug/{slug}/', response=PostDetailOut, auth=OptionalProfileAuth())
def get_post_by_slug(request, slug: str, establishment_slug: str = None,
                     author_name: str = None):
    """Get a post by slug. Needs establishment_slug or author_name to disambiguate."""
    qs = Post.objects.select_related('author', 'establishment', 'approved_by').prefetch_related('tags')

    if establishment_slug:
        qs = qs.filter(establishment__slug=establishment_slug, slug=slug)
    elif author_name:
        qs = qs.filter(author__local_name=author_name, slug=slug, establishment__isnull=True)
    else:
        # Ambiguous — prefer published, newest first
        qs = qs.filter(slug=slug).order_by(
            Case(When(status='published', then=0), default=1),
            '-published_at', '-created_at',
        )

    post = qs.first()
    if not post:
        raise HttpError(404, "Post not found")

    profile = getattr(request, 'auth_profile', None)

    # Check visibility
    if post.status != 'published':
        if not profile or not _can_edit_post(post, profile):
            raise HttpError(404, "Post not found")

    return _post_to_detail(post, profile)

def _batch_check_and_fetch(profile: Profile, post_ids: List[str]) -> List[Post]:
    """
    Load posts, verify they all belong to same establishment, verify profile is
    OWNER/ADMIN (or superuser). Returns posts list.
    """
    if not post_ids:
        raise HttpError(400, "post_ids cannot be empty")
    if len(post_ids) > 50:
        raise HttpError(400, "Maximum 50 posts per batch")

    posts = list(
        Post.objects.select_related('establishment', 'author')
        .filter(id__in=post_ids)
    )
    if len(posts) != len(post_ids):
        raise HttpError(404, "One or more posts not found")

    # All posts must belong to the same establishment
    est_ids = {p.establishment_id for p in posts}
    if len(est_ids) != 1 or None in est_ids:
        raise HttpError(400, "All posts must belong to the same establishment")

    est = posts[0].establishment
    if not profile.account.is_superuser:
        from geo.permissions import get_user_role
        role = get_user_role(est, profile)
        if role not in SIGNING_ROLES:
            raise HttpError(403, "Only OWNER/ADMIN can perform batch actions")

    return posts

@router.post('/posts/batch-approve/', response=List[PostListOut], auth=ProfileAuth())
@ratelimit(group='cms:batch_approve', key=user_or_ip, rate='120/h')
def batch_approve_posts(request, payload: BatchPostsIn):
    """Mark a set of posts (one topic across languages) as approved. OWNER/ADMIN only."""
    from django.db import transaction
    profile: Profile = request.auth
    posts = _batch_check_and_fetch(profile, payload.post_ids)

    now = timezone.now()
    with transaction.atomic():
        for p in posts:
            p.approved_at = now
            p.approved_by = profile
            p.save(update_fields=['approved_at', 'approved_by'])

    logger.info(f"Batch approved {len(posts)} posts by {profile.hna}")
    refreshed = list(
        Post.objects.select_related('author', 'establishment', 'approved_by')
        .prefetch_related('tags')
        .filter(id__in=[p.id for p in posts])
    )
    return [_post_to_list(p) for p in refreshed]

@router.post('/posts/batch-unapprove/', response=List[PostListOut], auth=ProfileAuth())
@ratelimit(group='cms:batch_unapprove', key=user_or_ip, rate='120/h')
def batch_unapprove_posts(request, payload: BatchPostsIn):
    """Revoke approval (move back to drafts). OWNER/ADMIN only."""
    from django.db import transaction
    profile: Profile = request.auth
    posts = _batch_check_and_fetch(profile, payload.post_ids)

    with transaction.atomic():
        for p in posts:
            if p.status == 'published':
                raise HttpError(400, f"Cannot unapprove published post '{p.title}' — unpublish first")
            p.approved_at = None
            p.approved_by = None
            p.save(update_fields=['approved_at', 'approved_by'])

    logger.info(f"Batch unapproved {len(posts)} posts by {profile.hna}")
    refreshed = list(
        Post.objects.select_related('author', 'establishment', 'approved_by')
        .prefetch_related('tags')
        .filter(id__in=[p.id for p in posts])
    )
    return [_post_to_list(p) for p in refreshed]

@router.post('/posts/batch-publish/', response=List[PostListOut], auth=ProfileAuth())
@ratelimit(group='cms:batch_publish', key=user_or_ip, rate='60/h')
def batch_publish_posts(request, payload: BatchPostsIn):
    """Publish a set of posts atomically (one topic across languages). OWNER/ADMIN only + WoT 3+."""
    from django.db import transaction
    profile: Profile = request.auth
    posts = _batch_check_and_fetch(profile, payload.post_ids)
    _check_wot3(profile)

    now = timezone.now()
    with transaction.atomic():
        for p in posts:
            if p.status == 'published':
                continue
            p.status = 'published'
            if not p.published_at:
                p.published_at = now
            p.save(update_fields=['status', 'published_at'])

    logger.info(f"Batch published {len(posts)} posts by {profile.hna}")
    refreshed = list(
        Post.objects.select_related('author', 'establishment', 'approved_by')
        .prefetch_related('tags')
        .filter(id__in=[p.id for p in posts])
    )
    return [_post_to_list(p) for p in refreshed]

@router.get('/posts/{post_id}/', response=PostDetailOut, auth=OptionalProfileAuth())
def get_post(request, post_id: str):
    """Get a post by ID."""
    post = get_object_or_404(
        Post.objects.select_related('author', 'establishment', 'approved_by').prefetch_related('tags'),
        id=post_id,
    )

    profile = getattr(request, 'auth_profile', None)

    if post.status != 'published':
        if not profile or not _can_edit_post(post, profile):
            raise HttpError(404, "Post not found")

    return _post_to_detail(post, profile)

@router.post('/posts/', response=PostDetailOut, auth=ProfileAuth())
@ratelimit(group='cms:create_post', key=user_or_ip, rate='20/h')
def create_post(request, payload: PostCreateIn):
    """Create a blog post. Requires WoT 3+."""
    profile: Profile = request.auth

    # Content size check
    if len(payload.content) > MAX_POST_CONTENT_SIZE:
        raise HttpError(400, f"Content too large (max {MAX_POST_CONTENT_SIZE // 1000}KB)")

    # Validate status
    if payload.status not in ('draft', 'published'):
        raise HttpError(400, "Status must be 'draft' or 'published'")

    # WoT check only for publishing
    if payload.status == 'published':
        _check_wot3(profile)

    establishment = None
    if payload.establishment_id:
        establishment = get_establishment_for_action(
            payload.establishment_id, profile, POSTING_ROLES
        )

    post = Post(
        author=profile,
        establishment=establishment,
        title=payload.title.strip()[:200],
        content=payload.content,
        status=payload.status,
        language=payload.language[:2] if payload.language else 'en',
        meta_description=payload.meta_description[:300],
        featured_image_id='',
        is_pinned=False,  # Set below with role check
        allow_comments=payload.allow_comments,
        allow_tips=payload.allow_tips,
        subscribers_only=payload.subscribers_only,
        publish_order=payload.publish_order,
    )

    # is_pinned requires SIGNING_ROLES for establishment posts
    if payload.is_pinned:
        if establishment:
            from geo.permissions import get_user_role
            role = get_user_role(establishment, profile)
            if role in SIGNING_ROLES or profile.account.is_superuser:
                post.is_pinned = True
        else:
            post.is_pinned = True  # Personal posts: author can always pin

    if payload.translation_of_id:
        try:
            original = Post.objects.get(id=payload.translation_of_id)
            # Enforce flat translation chain: always point to the root original
            if original.translation_of_id:
                original = Post.objects.get(id=original.translation_of_id)
            # Prevent same-language translations
            if original.language == post.language:
                raise HttpError(400, "Translation must be in a different language than the original")
            post.translation_of = original
            # Inherit publish_order from original if not explicitly set
            if post.publish_order is None and original.publish_order is not None:
                post.publish_order = original.publish_order
        except Post.DoesNotExist:
            pass

    post.save()

    # Set featured image (validate existence)
    if payload.featured_image_id:
        if ObjectPhoto.objects.filter(id=payload.featured_image_id[:26]).exists():
            post.featured_image_id = payload.featured_image_id[:26]
            post.save(update_fields=['featured_image_id'])

    if payload.tag_ids:
        from taxonomy.models import Category
        tags = Category.objects.filter(id__in=payload.tag_ids)
        post.tags.set(tags)

    # Re-fetch with relations
    post = Post.objects.select_related('author', 'establishment', 'approved_by').prefetch_related('tags').get(id=post.id)
    logger.info(f"Post created: '{post.title}' by {profile.hna}")
    return _post_to_detail(post, profile)

@router.patch('/posts/{post_id}/', response=PostDetailOut, auth=ProfileAuth())
@ratelimit(group='cms:update_post', key=user_or_ip, rate='60/h')
def update_post(request, post_id: str, payload: PostUpdateIn):
    """Update a blog post. Author or OWNER/ADMIN only."""
    profile: Profile = request.auth

    if payload.content is not None and len(payload.content) > MAX_POST_CONTENT_SIZE:
        raise HttpError(400, f"Content too large (max {MAX_POST_CONTENT_SIZE // 1000}KB)")

    post = get_object_or_404(
        Post.objects.select_related('author', 'establishment', 'approved_by'),
        id=post_id,
    )

    if not _can_edit_post(post, profile):
        raise HttpError(403, "Not authorized to edit this post")

    # WoT check on publish
    if payload.status == 'published' and post.status != 'published':
        _check_wot3(profile)

    if payload.title is not None:
        post.title = payload.title.strip()[:200]
    if payload.content is not None:
        post.content = payload.content
    if payload.status is not None:
        if payload.status not in ('draft', 'published', 'archived'):
            raise HttpError(400, "Invalid status")
        post.status = payload.status
    if payload.language is not None:
        post.language = payload.language[:2]
    if payload.meta_description is not None:
        post.meta_description = payload.meta_description[:300]
    if payload.featured_image_id is not None:
        if payload.featured_image_id:
            if ObjectPhoto.objects.filter(id=payload.featured_image_id[:26]).exists():
                post.featured_image_id = payload.featured_image_id[:26]
        else:
            post.featured_image_id = ''
    if payload.is_pinned is not None:
        if post.establishment_id:
            from geo.permissions import get_user_role
            role = get_user_role(post.establishment, profile)
            if role in SIGNING_ROLES or profile.account.is_superuser:
                post.is_pinned = payload.is_pinned
        else:
            post.is_pinned = payload.is_pinned
    if payload.allow_comments is not None:
        post.allow_comments = payload.allow_comments
    if payload.allow_tips is not None:
        post.allow_tips = payload.allow_tips
    if payload.subscribers_only is not None:
        post.subscribers_only = payload.subscribers_only
    if payload.publish_order is not None:
        post.publish_order = payload.publish_order
    if payload.translation_of_id is not None:
        if payload.translation_of_id:
            try:
                original = Post.objects.get(id=payload.translation_of_id)
                # Enforce flat chain: always point to root
                if original.translation_of_id:
                    original = Post.objects.get(id=original.translation_of_id)
                if original.language == (payload.language or post.language):
                    raise HttpError(400, "Translation must be in a different language than the original")
                post.translation_of = original
            except Post.DoesNotExist:
                pass
        else:
            post.translation_of = None

    post.save()

    if payload.tag_ids is not None:
        from taxonomy.models import Category
        tags = Category.objects.filter(id__in=payload.tag_ids)
        post.tags.set(tags)

    post = Post.objects.select_related('author', 'establishment', 'approved_by').prefetch_related('tags').get(id=post.id)
    return _post_to_detail(post, profile)

@router.delete('/posts/{post_id}/', auth=ProfileAuth())
@ratelimit(group='cms:delete_post', key=user_or_ip, rate='20/h')
def delete_post(request, post_id: str):
    """Delete a blog post. Author or OWNER/ADMIN only."""
    profile: Profile = request.auth
    post = get_object_or_404(Post, id=post_id)

    if not _can_edit_post(post, profile):
        raise HttpError(403, "Not authorized to delete this post")

    # Attachments (photos/files incl. disk blobs, comments, videos, likes)
    # cascade via the core pre_delete fan-out (core/signals.py).
    post.delete()
    logger.info(f"Post deleted: '{post.title}' by {profile.hna}")
    return {'ok': True}
