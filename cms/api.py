"""CMS API — blog posts and file attachments."""
from typing import List, Optional
from datetime import datetime
import logging
import socket

from ninja import Router, Schema, File
from ninja.errors import HttpError
from ninja.files import UploadedFile

from django.conf import settings
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import Q
from django.shortcuts import get_object_or_404

from parahub.auth import ProfileAuth, OptionalProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from identity.models import Profile, Verification
from geo.permissions import get_establishment_for_action, POSTING_ROLES, SIGNING_ROLES
from core.models import ObjectPhoto, ObjectFile
from .models import Post, Site, SitePage

logger = logging.getLogger(__name__)
router = Router(tags=["CMS"])

# Content size limits
MAX_POST_CONTENT_SIZE = 200_000  # ~200KB markdown
MAX_PAGE_CONTENT_SIZE = 200_000


# ── Schemas ───────────────────────────────────────────────────────────────────

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
    comments_count: int
    author_id: str
    author_hna: str
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
    created_at: datetime


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
    translation_of_id: Optional[str] = None
    tag_ids: Optional[List[str]] = None
    publish_order: Optional[int] = None


class FileOut(Schema):
    id: str
    object_type: str = 'object_file'
    filename: str
    mime_type: str
    size_bytes: int
    url: str
    order: int
    created_at: datetime


# ── Helpers ───────────────────────────────────────────────────────────────────

def _check_wot2(profile: Profile):
    """Raise 403 if profile doesn't meet WoT 2+ requirement."""
    if profile.account.is_superuser:
        return
    if profile.is_foundation_member():
        return
    count = Verification.objects.filter(
        verified_profile=profile,
        is_active=True,
    ).count()
    if count < 2:
        raise HttpError(403, "Requires WoT level 2+ to publish blog posts")


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
        comments_count=post.comments_count,
        author_id=author.id,
        author_hna=author.hna,
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
        created_at=post.created_at,
    )


def _post_to_detail(post: Post) -> PostDetailOut:
    author = post.author
    est = post.establishment

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
        comments_count=post.comments_count,
        author_id=author.id,
        author_hna=author.hna,
        author_display_name=author.display_name or None,
        author_avatar=author.avatar.url if author.avatar else None,
        establishment_id=est.id if est else None,
        establishment_name=est.name if est else None,
        establishment_slug=est.slug if est else None,
        featured_image_url=featured_url,
        tags=tag_list,
        is_demo=_is_demo_obj(post),
        publish_order=post.publish_order,
        created_at=post.created_at,
        content=post.content,
        content_html=post.content_html,
        meta_description=post.meta_description,
        featured_image_id=post.featured_image_id,
        translation_of_id=post.translation_of_id,
        translations=translations,
        pgp_signature=post.pgp_signature,
        files=file_list,
        updated_at=post.updated_at,
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


# ── Helpers ──────────────────────────────────────────────────────────────────

def _is_privileged_user(request) -> bool:
    """Return True if the request comes from staff or a test account."""
    user = getattr(request, 'user', None)
    if user and getattr(user, 'is_authenticated', False):
        return getattr(user, 'is_staff', False) or getattr(user, 'is_test', False)
    return False


def _is_demo_obj(obj) -> bool:
    """Check if object has demo markers in attributes/spec_data."""
    attrs = getattr(obj, 'attributes', None) or {}
    if attrs.get('demo') or attrs.get('__demo_seed'):
        return True
    spec = getattr(obj, 'spec_data', None) or {}
    if spec.get('__demo_seed'):
        return True
    author = getattr(obj, 'author', None)
    if author and getattr(author, 'account', None):
        if author.account.is_test or author.account.is_bot:
            return True
    return False


DEMO_ATTR_KEYS = ('demo', '__demo_seed')


def _exclude_demo_posts(qs):
    """Exclude posts with demo markers or from test/bot accounts."""
    qs = qs.exclude(attributes__demo=True).exclude(attributes__has_key='__demo_seed')
    qs = qs.exclude(author__account__is_test=True).exclude(author__account__is_bot=True)
    return qs


def _exclude_demo_sites(qs):
    """Exclude sites with demo markers or owned by test/bot accounts."""
    qs = qs.exclude(attributes__demo=True).exclude(attributes__has_key='__demo_seed')
    qs = qs.exclude(establishment__owner__account__is_test=True).exclude(establishment__owner__account__is_bot=True)
    qs = qs.exclude(profile__account__is_test=True).exclude(profile__account__is_bot=True)
    return qs


def _exclude_demo_pages(qs):
    """Exclude site pages with demo markers or from demo sites."""
    qs = qs.exclude(attributes__demo=True).exclude(attributes__has_key='__demo_seed')
    qs = qs.exclude(site__attributes__demo=True).exclude(site__attributes__has_key='__demo_seed')
    return qs


# ── Posts CRUD ────────────────────────────────────────────────────────────────

@router.get('/posts/', response={200: dict}, auth=OptionalProfileAuth())
def list_posts(request, establishment_id: str = None, establishment_slug: str = None,
               author_id: str = None, author_name: str = None,
               tag: str = None, language: str = None,
               status: str = None, search: str = None):
    """
    Public post feed. Filters by establishment, author, tag, language.
    Drafts visible only to author/OWNER/ADMIN.
    """
    qs = Post.objects.select_related('author', 'establishment').prefetch_related('tags')

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
    if status and status in ('draft', 'archived') and profile:
        # Show drafts/archived only if user can manage them
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

    # Apply pagination manually at DB level, then transform the page
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))
    if page_size > 100:
        page_size = 100
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

    qs = qs[:30]

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
    for p in qs:
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
    <language>en</language>
    <atom:link href="{feed_link}rss/" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>'''

    return HttpResponse(xml, content_type='application/rss+xml; charset=utf-8')


@router.get('/posts/by-slug/{slug}/', response=PostDetailOut, auth=OptionalProfileAuth())
def get_post_by_slug(request, slug: str, establishment_slug: str = None,
                     author_name: str = None):
    """Get a post by slug. Needs establishment_slug or author_name to disambiguate."""
    qs = Post.objects.select_related('author', 'establishment').prefetch_related('tags')

    if establishment_slug:
        qs = qs.filter(establishment__slug=establishment_slug, slug=slug)
    elif author_name:
        qs = qs.filter(author__local_name=author_name, slug=slug, establishment__isnull=True)
    else:
        qs = qs.filter(slug=slug)

    post = qs.first()
    if not post:
        raise HttpError(404, "Post not found")

    profile = getattr(request, 'auth_profile', None)

    # Check visibility
    if post.status != 'published':
        if not profile or not _can_edit_post(post, profile):
            raise HttpError(404, "Post not found")

    return _post_to_detail(post)


@router.get('/posts/{post_id}/', response=PostDetailOut, auth=OptionalProfileAuth())
def get_post(request, post_id: str):
    """Get a post by ID."""
    post = get_object_or_404(
        Post.objects.select_related('author', 'establishment').prefetch_related('tags'),
        id=post_id,
    )

    profile = getattr(request, 'auth_profile', None)

    if post.status != 'published':
        if not profile or not _can_edit_post(post, profile):
            raise HttpError(404, "Post not found")

    return _post_to_detail(post)


@router.post('/posts/', response=PostDetailOut, auth=ProfileAuth())
@ratelimit(group='cms:create_post', key=user_or_ip, rate='20/h')
def create_post(request, payload: PostCreateIn):
    """Create a blog post. Requires WoT 2+."""
    profile: Profile = request.auth

    # Content size check
    if len(payload.content) > MAX_POST_CONTENT_SIZE:
        raise HttpError(400, f"Content too large (max {MAX_POST_CONTENT_SIZE // 1000}KB)")

    # Validate status
    if payload.status not in ('draft', 'published'):
        raise HttpError(400, "Status must be 'draft' or 'published'")

    # WoT check only for publishing
    if payload.status == 'published':
        _check_wot2(profile)

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
    post = Post.objects.select_related('author', 'establishment').prefetch_related('tags').get(id=post.id)
    logger.info(f"Post created: '{post.title}' by {profile.hna}")
    return _post_to_detail(post)


@router.patch('/posts/{post_id}/', response=PostDetailOut, auth=ProfileAuth())
@ratelimit(group='cms:update_post', key=user_or_ip, rate='60/h')
def update_post(request, post_id: str, payload: PostUpdateIn):
    """Update a blog post. Author or OWNER/ADMIN only."""
    profile: Profile = request.auth

    if payload.content is not None and len(payload.content) > MAX_POST_CONTENT_SIZE:
        raise HttpError(400, f"Content too large (max {MAX_POST_CONTENT_SIZE // 1000}KB)")

    post = get_object_or_404(
        Post.objects.select_related('author', 'establishment'),
        id=post_id,
    )

    if not _can_edit_post(post, profile):
        raise HttpError(403, "Not authorized to edit this post")

    # WoT check on publish
    if payload.status == 'published' and post.status != 'published':
        _check_wot2(profile)

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

    post = Post.objects.select_related('author', 'establishment').prefetch_related('tags').get(id=post.id)
    return _post_to_detail(post)


@router.delete('/posts/{post_id}/', auth=ProfileAuth())
@ratelimit(group='cms:delete_post', key=user_or_ip, rate='20/h')
def delete_post(request, post_id: str):
    """Delete a blog post. Author or OWNER/ADMIN only."""
    profile: Profile = request.auth
    post = get_object_or_404(Post, id=post_id)

    if not _can_edit_post(post, profile):
        raise HttpError(403, "Not authorized to delete this post")

    # Delete attached files (both DB records and actual files on disk)
    for f in ObjectFile.objects.filter(object_id=post.id):
        f.file.delete(save=False)
        f.delete()
    # Clean up orphaned photos and comments
    ObjectPhoto.objects.filter(object_id=post.id).delete()
    from core.models import ObjectComment
    ObjectComment.objects.filter(object_id=post.id).delete()
    post.delete()
    logger.info(f"Post deleted: '{post.title}' by {profile.hna}")
    return {'ok': True}


# ── Files ─────────────────────────────────────────────────────────────────────

ALLOWED_FILE_TYPES = {
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'text/plain',
    'text/csv',
}

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


@router.post('/posts/{post_id}/files/', response=FileOut, auth=ProfileAuth())
@ratelimit(group='cms:upload_file', key=user_or_ip, rate='30/h')
def upload_file(request, post_id: str, file: UploadedFile = File(...)):
    """Upload a file attachment to a post."""
    profile: Profile = request.auth
    post = get_object_or_404(Post, id=post_id)

    if not _can_edit_post(post, profile):
        raise HttpError(403, "Not authorized to add files to this post")

    if file.size > MAX_FILE_SIZE:
        raise HttpError(400, f"File too large (max {MAX_FILE_SIZE // 1024 // 1024} MB)")

    # Validate by file extension (not client-provided Content-Type which can be spoofed)
    import os
    ALLOWED_EXTENSIONS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt', '.csv'}
    ext = os.path.splitext(file.name or '')[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HttpError(400, f"File type '{ext}' not allowed. Allowed: PDF, DOC, DOCX, XLS, XLSX, TXT, CSV")
    mime = file.content_type or 'application/octet-stream'

    existing_count = ObjectFile.objects.filter(object_id=post.id).count()
    if existing_count >= 20:
        raise HttpError(400, "Maximum 20 files per post")
    obj_file = ObjectFile.objects.create(
        object_id=post.id,
        file=file,
        filename=file.name[:255],
        mime_type=mime,
        size_bytes=file.size,
        uploaded_by=profile,
        order=existing_count,
    )

    return FileOut(
        id=obj_file.id,
        filename=obj_file.filename,
        mime_type=obj_file.mime_type,
        size_bytes=obj_file.size_bytes,
        url=obj_file.file.url,
        order=obj_file.order,
        created_at=obj_file.created_at,
    )


@router.delete('/posts/{post_id}/files/{file_id}/', auth=ProfileAuth())
def delete_file(request, post_id: str, file_id: str):
    """Delete a file attachment from a post."""
    profile: Profile = request.auth
    post = get_object_or_404(Post, id=post_id)

    if not _can_edit_post(post, profile):
        raise HttpError(403, "Not authorized to remove files from this post")

    obj_file = get_object_or_404(ObjectFile, id=file_id, object_id=post.id)
    obj_file.file.delete(save=False)
    obj_file.delete()
    return {'ok': True}


# ── Site Schemas ──────────────────────────────────────────────────────────────

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
    created_at: datetime
    updated_at: datetime


class SitePageCreateIn(Schema):
    title: str
    slug: str = ''
    content: str = ''
    order: int = 0
    show_in_nav: bool = True
    is_published: bool = True


class SitePageUpdateIn(Schema):
    title: Optional[str] = None
    slug: Optional[str] = None
    content: Optional[str] = None
    order: Optional[int] = None
    show_in_nav: Optional[bool] = None
    is_published: Optional[bool] = None


# ── Site Helpers ──────────────────────────────────────────────────────────────

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
    } for p in site.pages.filter(show_in_nav=True, is_published=True).order_by('order')]

    est = site.establishment
    profile = site.profile

    return SiteOut(
        id=site.id,
        accent_color=site.accent_color,
        hero_text=site.hero_text,
        hero_text_html=site.hero_text_html,
        hero_image_id=site.hero_image_id,
        hero_image_url=hero_url,
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
        created_at=page.created_at,
        updated_at=page.updated_at,
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


# ── Site Endpoints ────────────────────────────────────────────────────────────

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
        site, _ = Site.objects.get_or_create(establishment=est)
    else:
        from identity.models import Profile
        profile = Profile.objects.filter(local_name=slug).first()
        if not profile:
            raise HttpError(404, "Site not found")
        site, _ = Site.objects.get_or_create(profile=profile)

    if not site.is_active:
        raise HttpError(404, "Site not found")

    return _site_to_out(site)


@router.get('/sites/by-establishment/{establishment_id}/', response=SiteOut, auth=None)
def get_site(request, establishment_id: str):
    """Get site config for an establishment (public, auto-creates)."""
    site = _get_site_for_est(establishment_id)
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
        site.nav_sections = [s.dict() for s in payload.nav_sections]
    if payload.is_active is not None:
        site.is_active = payload.is_active

    site.save()
    return _site_to_out(site)


# ── Custom Domain ─────────────────────────────────────────────────────────────

class CustomDomainIn(Schema):
    domain: str


class CustomDomainStatus(Schema):
    custom_domain: str
    custom_domain_verified: bool
    custom_domain_ssl_ready: bool
    cname_target: str = 'parahub.io'
    message: str = ''


# Reserved TLDs and suffixes that should never be used as custom domains
_BLOCKED_DOMAIN_SUFFIXES = (
    '.local', '.localhost', '.internal', '.test', '.example',
    '.invalid', '.onion', '.i2p',
)

# Private/reserved IP prefixes for SSRF protection
_PRIVATE_IP_PREFIXES = (
    '127.', '10.', '192.168.', '0.',
    '169.254.',  # Link-local / cloud metadata
    '172.16.', '172.17.', '172.18.', '172.19.',
    '172.20.', '172.21.', '172.22.', '172.23.',
    '172.24.', '172.25.', '172.26.', '172.27.',
    '172.28.', '172.29.', '172.30.', '172.31.',
)


def _validate_custom_domain(domain: str):
    """Validate custom domain is not internal/reserved. Raises HttpError on failure."""
    import re
    if not re.match(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$', domain):
        raise HttpError(400, "Invalid domain format")

    # Block parahub.io subdomains
    if domain.endswith('.parahub.io') or domain == 'parahub.io':
        raise HttpError(400, "Cannot use parahub.io subdomains as custom domain")

    # Block reserved TLDs (SSRF protection)
    for suffix in _BLOCKED_DOMAIN_SUFFIXES:
        if domain.endswith(suffix) or domain == suffix.lstrip('.'):
            raise HttpError(400, f"Domain with '{suffix}' suffix is not allowed")

    # Block uniqueness collision
    existing = Site.objects.filter(custom_domain=domain).first()
    # (caller handles exclude for own site)

    # Proactive SSRF check: resolve the domain and reject private IPs
    try:
        ip = socket.gethostbyname(domain)
        if any(ip.startswith(prefix) for prefix in _PRIVATE_IP_PREFIXES) or ip == '::1':
            logger.warning(f"SSRF blocked: domain {domain} resolves to private IP {ip}")
            raise HttpError(400, "Domain resolves to a private/reserved IP address")
    except socket.gaierror:
        pass  # Domain doesn't resolve yet — OK, user may not have set DNS yet


_ssl_setup_lock: set = set()  # Domains currently being set up

def _trigger_ssl_setup(domain: str):
    """Run SSL cert issuance + nginx config in a background thread (with concurrency guard)."""
    import threading
    from django.core.management import call_command

    if domain in _ssl_setup_lock:
        logger.info(f"SSL setup already running for {domain}, skipping")
        return

    def _run():
        _ssl_setup_lock.add(domain)
        try:
            call_command('setup_custom_domain', domain)
        except Exception:
            logger.exception(f"SSL setup failed for {domain}")
        finally:
            _ssl_setup_lock.discard(domain)

    threading.Thread(target=_run, daemon=True).start()
    logger.info(f"SSL setup triggered in background for {domain}")


def _trigger_ssl_removal(domain: str):
    """Remove nginx config for a custom domain in background."""
    import threading
    from pathlib import Path
    import subprocess

    def _run():
        try:
            config_path = Path(f'/etc/nginx/sites-enabled/custom-{domain}')
            if config_path.exists():
                config_path.unlink()
                subprocess.run(['sudo', 'nginx', '-t'], capture_output=True, text=True, check=True)
                subprocess.run(['sudo', 'systemctl', 'reload', 'nginx'], check=True)
                logger.info(f"Nginx config removed for {domain}")
        except Exception:
            logger.exception(f"SSL removal failed for {domain}")

    threading.Thread(target=_run, daemon=True).start()


@router.post('/sites/by-establishment/{establishment_id}/domain/', response=CustomDomainStatus, auth=ProfileAuth())
@ratelimit(group='cms:set_domain', key=user_or_ip, rate='10/h')
def set_custom_domain(request, establishment_id: str, payload: CustomDomainIn):
    """Set a custom domain for a site. OWNER/ADMIN only."""
    profile: Profile = request.auth
    get_establishment_for_action(establishment_id, profile, SIGNING_ROLES)

    site = _get_site_for_est(establishment_id)
    domain = payload.domain.strip().lower()

    if not domain:
        # Clear custom domain — also remove nginx/SSL config
        old_domain = site.custom_domain
        site.custom_domain = ''
        site.custom_domain_verified = False
        site.custom_domain_ssl_ready = False
        site.save(update_fields=['custom_domain', 'custom_domain_verified', 'custom_domain_ssl_ready'])
        if old_domain:
            _trigger_ssl_removal(old_domain)
        return CustomDomainStatus(
            custom_domain='', custom_domain_verified=False,
            custom_domain_ssl_ready=False, message='Custom domain removed',
        )

    # Centralized validation: format, reserved TLDs, SSRF, parahub.io block
    _validate_custom_domain(domain)

    # Check not already taken by another site
    existing = Site.objects.filter(custom_domain=domain).exclude(id=site.id).first()
    if existing:
        raise HttpError(400, "Domain already in use by another site")

    site.custom_domain = domain
    site.custom_domain_verified = False
    site.custom_domain_ssl_ready = False
    site.save(update_fields=['custom_domain', 'custom_domain_verified', 'custom_domain_ssl_ready'])

    return CustomDomainStatus(
        custom_domain=domain, custom_domain_verified=False,
        custom_domain_ssl_ready=False,
        message=f'Set domain to {domain}. Create a CNAME record pointing to parahub.io, then verify.',
    )


@router.post('/sites/by-establishment/{establishment_id}/domain/verify/', response=CustomDomainStatus, auth=ProfileAuth())
def verify_custom_domain(request, establishment_id: str):
    """Verify CNAME for custom domain. OWNER/ADMIN only. Rate limited: 1 per 30s per profile."""
    import subprocess as sp
    from django.core.cache import cache
    profile: Profile = request.auth
    get_establishment_for_action(establishment_id, profile, SIGNING_ROLES)

    cache_key = f'cms:domain_verify:{profile.id}'
    if cache.get(cache_key):
        raise HttpError(429, "Please wait before verifying again")
    cache.set(cache_key, 1, timeout=30)

    site = _get_site_for_est(establishment_id)
    domain = site.custom_domain
    if not domain:
        raise HttpError(400, "No custom domain set")

    # Check CNAME or A record
    verified = False
    try:
        result = sp.run(['dig', '+short', 'CNAME', domain], capture_output=True, text=True, timeout=10)
        cname = result.stdout.strip().rstrip('.')
        if cname == 'parahub.io':
            verified = True
    except Exception:
        pass

    if not verified:
        try:
            ip = socket.gethostbyname(domain)
            if ip == settings.PARAHUB_SERVER_IP:
                verified = True
        except socket.gaierror:
            pass

    site.custom_domain_verified = verified
    site.save(update_fields=['custom_domain_verified'])

    msg = 'CNAME verified!' if verified else f'Verification failed. Point {domain} CNAME to parahub.io'

    # Auto-trigger SSL setup if verified and not yet SSL-ready
    if verified and not site.custom_domain_ssl_ready:
        _trigger_ssl_setup(domain)
        msg = 'CNAME verified! SSL certificate is being issued — this may take a minute.'

    return CustomDomainStatus(
        custom_domain=domain,
        custom_domain_verified=verified,
        custom_domain_ssl_ready=site.custom_domain_ssl_ready,
        message=msg,
    )


# ── SitePage Endpoints ────────────────────────────────────────────────────────

@router.get('/sites/by-establishment/{establishment_id}/pages/', response=List[SitePageOut], auth=None)
def list_site_pages(request, establishment_id: str):
    """List published pages for a site (public)."""
    site = _get_site_for_est(establishment_id)
    pages = site.pages.filter(is_published=True).order_by('order')
    return [_page_to_out(p) for p in pages]


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

    page = SitePage(
        site=site,
        title=payload.title.strip()[:200],
        slug=payload.slug.strip()[:200] if payload.slug else '',
        content=payload.content,
        order=payload.order,
        show_in_nav=payload.show_in_nav,
        is_published=payload.is_published,
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

    page.save()
    return _page_to_out(page)


@router.delete('/sites/by-establishment/{establishment_id}/pages/{page_id}/', auth=ProfileAuth())
def delete_site_page(request, establishment_id: str, page_id: str):
    """Delete a page. OWNER/ADMIN only."""
    profile: Profile = request.auth
    get_establishment_for_action(establishment_id, profile, SIGNING_ROLES)

    site = _get_site_for_est(establishment_id)
    page = get_object_or_404(site.pages, id=page_id)
    page.delete()
    return {'ok': True}


# ── Profile Site Endpoints ───────────────────────────────────────────────────

def _require_profile_owner(request, profile_name: str) -> 'Profile':
    """Verify the authenticated user owns this profile (or is superuser)."""
    profile: Profile = request.auth
    if profile.local_name != profile_name and not profile.account.is_superuser:
        raise HttpError(403, "Not your profile")
    return profile


@router.get('/sites/by-profile/{profile_name}/', response=SiteOut, auth=None)
def get_profile_site(request, profile_name: str):
    """Get site config for a profile (public, auto-creates)."""
    site = _get_site_for_profile(profile_name)
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
        site.nav_sections = [s.dict() for s in payload.nav_sections]
    if payload.is_active is not None:
        site.is_active = payload.is_active

    site.save()
    return _site_to_out(site)


@router.post('/sites/by-profile/{profile_name}/domain/', response=CustomDomainStatus, auth=ProfileAuth())
@ratelimit(group='cms:set_domain', key=user_or_ip, rate='10/h')
def set_profile_custom_domain(request, profile_name: str, payload: CustomDomainIn):
    """Set a custom domain for a profile site. Owner only."""
    _require_profile_owner(request, profile_name)
    site = _get_site_for_profile(profile_name)
    domain = payload.domain.strip().lower()

    if not domain:
        old_domain = site.custom_domain
        site.custom_domain = ''
        site.custom_domain_verified = False
        site.custom_domain_ssl_ready = False
        site.save(update_fields=['custom_domain', 'custom_domain_verified', 'custom_domain_ssl_ready'])
        if old_domain:
            _trigger_ssl_removal(old_domain)
        return CustomDomainStatus(
            custom_domain='', custom_domain_verified=False,
            custom_domain_ssl_ready=False, message='Custom domain removed',
        )

    # Centralized validation: format, reserved TLDs, SSRF, parahub.io block
    _validate_custom_domain(domain)

    existing = Site.objects.filter(custom_domain=domain).exclude(id=site.id).first()
    if existing:
        raise HttpError(400, "Domain already in use by another site")

    site.custom_domain = domain
    site.custom_domain_verified = False
    site.custom_domain_ssl_ready = False
    site.save(update_fields=['custom_domain', 'custom_domain_verified', 'custom_domain_ssl_ready'])

    return CustomDomainStatus(
        custom_domain=domain, custom_domain_verified=False,
        custom_domain_ssl_ready=False,
        message=f'Set domain to {domain}. Create a CNAME record pointing to parahub.io, then verify.',
    )


@router.post('/sites/by-profile/{profile_name}/domain/verify/', response=CustomDomainStatus, auth=ProfileAuth())
def verify_profile_custom_domain(request, profile_name: str):
    """Verify CNAME for custom domain. Owner only. Rate limited: 1 per 30s per profile."""
    import subprocess as sp
    from django.core.cache import cache
    _require_profile_owner(request, profile_name)
    profile: Profile = request.auth

    cache_key = f'cms:domain_verify:{profile.id}'
    if cache.get(cache_key):
        raise HttpError(429, "Please wait before verifying again")
    cache.set(cache_key, 1, timeout=30)
    site = _get_site_for_profile(profile_name)
    domain = site.custom_domain
    if not domain:
        raise HttpError(400, "No custom domain set")

    verified = False
    try:
        result = sp.run(['dig', '+short', 'CNAME', domain], capture_output=True, text=True, timeout=10)
        cname = result.stdout.strip().rstrip('.')
        if cname == 'parahub.io':
            verified = True
    except Exception:
        pass

    if not verified:
        try:
            ip = socket.gethostbyname(domain)
            if ip == settings.PARAHUB_SERVER_IP:
                verified = True
        except socket.gaierror:
            pass

    site.custom_domain_verified = verified
    site.save(update_fields=['custom_domain_verified'])

    msg = 'CNAME verified!' if verified else f'Verification failed. Point {domain} CNAME to parahub.io'

    if verified and not site.custom_domain_ssl_ready:
        _trigger_ssl_setup(domain)
        msg = 'CNAME verified! SSL certificate is being issued — this may take a minute.'

    return CustomDomainStatus(
        custom_domain=domain,
        custom_domain_verified=verified,
        custom_domain_ssl_ready=site.custom_domain_ssl_ready,
        message=msg,
    )


@router.get('/sites/by-profile/{profile_name}/pages/', response=List[SitePageOut], auth=None)
def list_profile_site_pages(request, profile_name: str):
    """List published pages for a profile site (public)."""
    site = _get_site_for_profile(profile_name)
    pages = site.pages.filter(is_published=True).order_by('order')
    return [_page_to_out(p) for p in pages]


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

    page = SitePage(
        site=site,
        title=payload.title.strip()[:200],
        slug=payload.slug.strip()[:200] if payload.slug else '',
        content=payload.content,
        order=payload.order,
        show_in_nav=payload.show_in_nav,
        is_published=payload.is_published,
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

    page.save()
    return _page_to_out(page)


@router.delete('/sites/by-profile/{profile_name}/pages/{page_id}/', auth=ProfileAuth())
def delete_profile_site_page(request, profile_name: str, page_id: str):
    """Delete a page. Profile owner only."""
    _require_profile_owner(request, profile_name)
    site = _get_site_for_profile(profile_name)
    page = get_object_or_404(site.pages, id=page_id)
    page.delete()
    return {'ok': True}


# ── Sitemap ──────────────────────────────────────────────────────────────────

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
