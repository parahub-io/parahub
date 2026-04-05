import re

from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.text import slugify
import markdown_it
import nh3

from core.models import ULIDModel

_VIDEO_EMBED_RE = re.compile(r'::video\[([a-zA-Z0-9-]+)\]')


def render_markdown(md_text: str) -> str:
    """Render Markdown to sanitized HTML."""
    md = markdown_it.MarkdownIt('commonmark', {'typographer': True}).enable('strikethrough').enable('table')
    raw_html = md.render(md_text)
    html = nh3.clean(
        raw_html,
        tags={
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'p', 'br', 'hr',
            'strong', 'em', 'del', 's',
            'a', 'img',
            'ul', 'ol', 'li',
            'blockquote', 'pre', 'code',
            'table', 'thead', 'tbody', 'tr', 'th', 'td',
        },
        attributes={
            'a': {'href', 'title'},
            'img': {'src', 'alt', 'title'},
            'th': {'align'},
            'td': {'align'},
        },
        link_rel='noopener noreferrer',
    )
    # Replace ::video[uuid] with PeerTube embed iframe (post-sanitization)
    peertube_url = getattr(settings, 'PEERTUBE_URL', 'https://video.parahub.io')
    html = _VIDEO_EMBED_RE.sub(
        lambda m: (
            f'<div class="video-embed" style="position:relative;aspect-ratio:16/9">'
            f'<iframe src="{peertube_url}/videos/embed/{m.group(1)}" '
            f'allowfullscreen sandbox="allow-same-origin allow-scripts allow-popups" '
            f'style="position:absolute;inset:0;width:100%;height:100%;border:none">'
            f'</iframe></div>'
        ),
        html,
    )
    return html


class Site(ULIDModel):
    """Mini-site for a profile or establishment. Custom branding, pages, navigation."""

    # One of two — profile OR establishment
    profile = models.OneToOneField(
        'identity.Profile', on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='site',
    )
    establishment = models.OneToOneField(
        'geo.Establishment', on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='site',
    )

    # Branding
    accent_color = models.CharField(max_length=7, default='#F5C518', help_text="Hex color")
    hero_text = models.TextField(blank=True, help_text="Markdown hero section text")
    hero_text_html = models.TextField(blank=True)
    hero_image_id = models.CharField(max_length=26, blank=True, help_text="ObjectPhoto ULID")

    # Navigation — which built-in sections to show
    # [{"type": "blog", "order": 1}, {"type": "gallery", "order": 2}, ...]
    # SitePages with show_in_nav=True are merged by their order field
    nav_sections = models.JSONField(default=list, blank=True)

    is_active = models.BooleanField(default=True)

    # Custom domain (Phase 3)
    custom_domain = models.CharField(max_length=253, blank=True, db_index=True,
                                      help_text="e.g. cafe-central.pt")
    custom_domain_verified = models.BooleanField(default=False,
                                                   help_text="CNAME verified pointing to parahub.io")
    custom_domain_ssl_ready = models.BooleanField(default=False,
                                                    help_text="SSL cert issued and nginx configured")

    class Meta:
        indexes = [
            models.Index(fields=['establishment']),
            models.Index(fields=['profile']),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(profile__isnull=False, establishment__isnull=True) |
                    models.Q(profile__isnull=True, establishment__isnull=False)
                ),
                name='site_one_owner',
            ),
            models.UniqueConstraint(
                fields=['custom_domain'],
                condition=~models.Q(custom_domain=''),
                name='unique_custom_domain',
            ),
        ]

    def __str__(self):
        if self.establishment:
            return f"Site: {self.establishment.name}"
        if self.profile:
            return f"Site: {self.profile.hna}"
        return f"Site {self.id}"

    def save(self, **kwargs):
        if self.hero_text:
            self.hero_text_html = render_markdown(self.hero_text)
        else:
            self.hero_text_html = ''
        super().save(**kwargs)

    @property
    def subdomain(self):
        """Return the subdomain slug for this site."""
        if self.establishment:
            return self.establishment.slug
        if self.profile:
            return self.profile.local_name
        return None

    @property
    def subdomain_type(self):
        """Return 'org' or 'u'."""
        if self.establishment_id:
            return 'org'
        return 'u'


class SitePage(ULIDModel):
    """Custom page within a mini-site (História, Heráldica, Serviços, etc.)."""

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='pages')
    title = models.CharField(max_length=200)
    slug = models.CharField(max_length=200)
    content = models.TextField(blank=True, help_text="Markdown")
    content_html = models.TextField(blank=True)
    order = models.IntegerField(default=0)
    show_in_nav = models.BooleanField(default=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ['order', 'created_at']
        constraints = [
            models.UniqueConstraint(fields=['site', 'slug'], name='unique_site_page_slug'),
        ]
        indexes = [
            models.Index(fields=['site', 'order']),
        ]

    def __str__(self):
        return f"{self.title} ({self.site})"

    def save(self, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title, allow_unicode=True)[:180] or 'page'
        if self.content:
            self.content_html = render_markdown(self.content)
        else:
            self.content_html = ''
        super().save(**kwargs)


class Post(ULIDModel):
    """Blog post — can belong to a person or an establishment."""

    author = models.ForeignKey(
        'identity.Profile', on_delete=models.CASCADE,
        related_name='blog_posts',
        help_text="Always a person, even when posting on behalf of establishment",
    )
    establishment = models.ForeignKey(
        'geo.Establishment', on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='blog_posts',
        help_text="If set, this is an org blog post",
    )

    title = models.CharField(max_length=200)
    slug = models.CharField(max_length=200, db_index=True)
    content = models.TextField(help_text="Markdown source of truth")
    content_html = models.TextField(blank=True, help_text="Pre-rendered HTML from Markdown")
    excerpt = models.TextField(blank=True, max_length=300)

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    published_at = models.DateTimeField(null=True, blank=True)

    language = models.CharField(max_length=2, default='en',
                                 help_text="ISO 639-1: pt, en, es, fr, de, ru")
    translation_of = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='translations',
    )

    # SEO
    meta_description = models.CharField(max_length=300, blank=True)
    featured_image_id = models.CharField(max_length=26, blank=True,
                                          help_text="ObjectPhoto ULID")

    # Taxonomy
    tags = models.ManyToManyField('taxonomy.Category', blank=True, related_name='blog_posts')

    # Parahub-specific
    pgp_signature = models.TextField(blank=True)
    allow_comments = models.BooleanField(default=True)
    allow_tips = models.BooleanField(default=True)

    # Org features
    is_pinned = models.BooleanField(default=False)

    # Publishing queue
    publish_order = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Topic ordering for publish queue. PT+EN share the same number.",
    )

    # Denormalized
    comments_count = models.IntegerField(default=0)

    class Meta:
        ordering = ['-is_pinned', '-published_at', '-created_at']
        indexes = [
            models.Index(fields=['establishment', 'status', '-published_at']),
            models.Index(fields=['author', 'status', '-published_at']),
            models.Index(fields=['slug']),
            models.Index(fields=['language']),
            models.Index(fields=['status', '-published_at']),
            models.Index(fields=['establishment', 'publish_order']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['establishment', 'slug'],
                condition=models.Q(establishment__isnull=False),
                name='unique_est_slug',
            ),
            models.UniqueConstraint(
                fields=['author', 'slug'],
                condition=models.Q(establishment__isnull=True),
                name='unique_author_slug',
            ),
        ]

    def __str__(self):
        return self.title

    def save(self, **kwargs):
        # Auto-generate slug
        if not self.slug:
            base = slugify(self.title, allow_unicode=True)[:180]
            self.slug = base or 'post'
            # Ensure uniqueness
            qs = Post.objects.filter(slug=self.slug)
            if self.establishment_id:
                qs = qs.filter(establishment_id=self.establishment_id)
            else:
                qs = qs.filter(author_id=self.author_id, establishment__isnull=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                import ulid as _ulid
                suffix = str(_ulid.ULID())[-6:].lower()
                self.slug = f"{base}-{suffix}"

        # Render Markdown → HTML
        if self.content:
            self.content_html = render_markdown(self.content)
        else:
            self.content_html = ''

        # Auto-excerpt: render markdown → strip HTML → collapse whitespace
        if not self.excerpt and self.content_html:
            plain = re.sub(r'\s+', ' ', strip_tags(self.content_html)).strip()
            self.excerpt = plain[:300].strip()

        # Set published_at on first publish
        if self.status == 'published' and not self.published_at:
            self.published_at = timezone.now()

        super().save(**kwargs)
