"""
Tests for CMS: Post, Site, SitePage models + API endpoints.

Tests invariants that must never break:
- Post slug uniqueness per author/establishment
- Site one-owner constraint (profile XOR establishment)
- Site unique custom domain constraint
- Custom domain validation (block parahub.io subdomains)
- Translation chain stays flat (always points to root)
- Same-language translation rejected
- Markdown rendering + XSS sanitization
- Access control: only author/OWNER/ADMIN can edit/delete
- Draft posts hidden from public feed
- WoT 2+ required for publishing (not drafts)
- RSS feed returns valid XML
"""

from unittest.mock import patch, MagicMock

from django.db import IntegrityError
from django.test import TestCase, RequestFactory
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone
from ninja.errors import HttpError

from identity.models import Account, Profile, Verification
from core.models import Instance, ObjectFile
from geo.models import Establishment, EstablishmentMembership
from cms.models import Post, Site, SitePage, render_markdown


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _instance():
    return Instance.objects.create(
        domain='test.parahub.io', name='Test', public_key='test-key',
    )


def _account(instance, username='alice'):
    return Account.objects.create_user(
        username=username, email=f'{username}@test.parahub.io',
        password='testpass123', instance=instance,
    )


def _profile(account, instance, local_name=None):
    local_name = local_name or account.username
    return Profile.objects.create(
        account=account, instance=instance, local_name=local_name,
        display_name=local_name.title(), is_primary=True,
        profile_type=Profile.ProfileType.PERSONAL,
    )


def _establishment(owner, name='Test Org', slug='test-org'):
    return Establishment.objects.create(
        owner=owner, name=name, slug=slug, is_active=True,
    )


def _membership(profile, establishment, role='MEMBER'):
    return EstablishmentMembership.objects.create(
        profile=profile, establishment=establishment, role=role,
    )


def _auth_request(factory, account, profile, method='get', path='/fake/', data=None):
    fn = getattr(factory, method)
    if data:
        request = fn(path, data=data, content_type='application/json')
    else:
        request = fn(path)
    request.user = account
    request.auth = profile
    request.auth_profile = profile
    request.session = SessionStore()
    request.session.create()
    return request


def _add_wot2(profile, instance):
    """Give profile 2 verifications to pass WoT 2+ check."""
    for i in range(2):
        acc = _account(instance, username=f'verifier{i}_{profile.local_name}')
        verifier = _profile(acc, instance, local_name=acc.username)
        Verification.objects.create(
            verifier=verifier, verified_profile=profile,
            verification_method='IN_PERSON',
            is_active=True,
        )


# ===========================================================================
# render_markdown tests
# ===========================================================================

class RenderMarkdownTest(TestCase):
    def test_basic_markdown(self):
        html = render_markdown('**bold** and *italic*')
        self.assertIn('<strong>bold</strong>', html)
        self.assertIn('<em>italic</em>', html)

    def test_xss_script_stripped(self):
        html = render_markdown('<script>alert("xss")</script>')
        self.assertNotIn('<script>', html)
        self.assertNotIn('alert(', html)

    def test_xss_onerror_stripped(self):
        html = render_markdown('<img src=x onerror="alert(1)">')
        self.assertNotIn('onerror', html)

    def test_link_rel_noopener(self):
        html = render_markdown('[link](https://example.com)')
        self.assertIn('rel="noopener noreferrer"', html)

    def test_video_embed(self):
        html = render_markdown('::video[abc-123]')
        self.assertIn('videos/embed/abc-123', html)
        self.assertIn('class="video-embed"', html)

    def test_table_rendering(self):
        md = '| A | B |\n|---|---|\n| 1 | 2 |'
        html = render_markdown(md)
        self.assertIn('<table>', html)
        self.assertIn('<td>', html)

    def test_strikethrough(self):
        html = render_markdown('~~deleted~~')
        self.assertIn('<s>deleted</s>', html)

    def test_iframe_not_in_plain_markdown(self):
        """nh3 strips iframes from user markdown — only video embed adds them."""
        html = render_markdown('<iframe src="evil.com"></iframe>')
        self.assertNotIn('<iframe', html)


# ===========================================================================
# Post Model Tests
# ===========================================================================

class PostModelTest(TestCase):
    def setUp(self):
        self.instance = _instance()
        self.acc = _account(self.instance)
        self.profile = _profile(self.acc, self.instance)

    def test_create_post(self):
        post = Post.objects.create(
            author=self.profile, title='Hello World',
            content='# Test\nSome content here.',
        )
        self.assertEqual(post.title, 'Hello World')
        self.assertEqual(post.slug, 'hello-world')
        self.assertEqual(post.status, 'draft')
        self.assertIn('<h1>Test</h1>', post.content_html)

    def test_slug_auto_generated(self):
        post = Post.objects.create(
            author=self.profile, title='My First Post',
            content='Content',
        )
        self.assertEqual(post.slug, 'my-first-post')

    def test_slug_uniqueness_per_author(self):
        """Two posts by same author with same title get different slugs."""
        p1 = Post.objects.create(
            author=self.profile, title='Duplicate', content='A',
        )
        p2 = Post.objects.create(
            author=self.profile, title='Duplicate', content='B',
        )
        self.assertEqual(p1.slug, 'duplicate')
        self.assertNotEqual(p1.slug, p2.slug)
        self.assertTrue(p2.slug.startswith('duplicate-'))

    def test_same_slug_different_authors(self):
        """Two authors can have posts with the same slug."""
        acc2 = _account(self.instance, 'bob')
        profile2 = _profile(acc2, self.instance, 'bob')
        p1 = Post.objects.create(
            author=self.profile, title='Same Title', content='A',
        )
        p2 = Post.objects.create(
            author=profile2, title='Same Title', content='B',
        )
        self.assertEqual(p1.slug, p2.slug)

    def test_auto_excerpt(self):
        content = 'A' * 500
        post = Post.objects.create(
            author=self.profile, title='Long', content=content,
        )
        self.assertEqual(len(post.excerpt), 300)

    def test_published_at_set_on_publish(self):
        post = Post.objects.create(
            author=self.profile, title='Draft', content='X',
            status='draft',
        )
        self.assertIsNone(post.published_at)
        post.status = 'published'
        post.save()
        self.assertIsNotNone(post.published_at)

    def test_published_at_not_overwritten(self):
        """published_at stays the same on subsequent saves."""
        post = Post.objects.create(
            author=self.profile, title='Pub', content='X',
            status='published',
        )
        original_time = post.published_at
        post.title = 'Updated'
        post.save()
        post.refresh_from_db()
        self.assertEqual(post.published_at, original_time)

    def test_content_html_rendered(self):
        post = Post.objects.create(
            author=self.profile, title='MD', content='**bold**',
        )
        self.assertIn('<strong>bold</strong>', post.content_html)

    def test_empty_content(self):
        post = Post.objects.create(
            author=self.profile, title='Empty', content='',
        )
        self.assertEqual(post.content_html, '')


# ===========================================================================
# Translation Tests
# ===========================================================================

class PostTranslationTest(TestCase):
    def setUp(self):
        self.instance = _instance()
        self.acc = _account(self.instance)
        self.profile = _profile(self.acc, self.instance)

    def test_translation_of_fk(self):
        original = Post.objects.create(
            author=self.profile, title='Original', content='EN',
            language='en',
        )
        translation = Post.objects.create(
            author=self.profile, title='Traducao', content='PT',
            language='pt', translation_of=original,
        )
        self.assertEqual(translation.translation_of_id, original.id)
        self.assertIn(translation, original.translations.all())

    def test_flat_chain_enforced_by_api(self):
        """API enforces flat chain — translation_of always points to root.
        This is tested in API tests below. Model allows nesting but API prevents it."""
        original = Post.objects.create(
            author=self.profile, title='Root', content='EN', language='en',
        )
        child = Post.objects.create(
            author=self.profile, title='Child', content='PT',
            language='pt', translation_of=original,
        )
        # Model allows this (API prevents it):
        grandchild = Post.objects.create(
            author=self.profile, title='Grandchild', content='ES',
            language='es', translation_of=child,
        )
        self.assertEqual(grandchild.translation_of_id, child.id)


# ===========================================================================
# Site Model Tests
# ===========================================================================

class SiteModelTest(TestCase):
    def setUp(self):
        self.instance = _instance()
        self.acc = _account(self.instance)
        self.profile = _profile(self.acc, self.instance)
        self.est = _establishment(self.profile)

    def test_create_site_for_establishment(self):
        site = Site.objects.create(establishment=self.est)
        self.assertEqual(site.establishment_id, self.est.id)
        self.assertIsNone(site.profile_id)
        self.assertTrue(site.is_active)

    def test_create_site_for_profile(self):
        site = Site.objects.create(profile=self.profile)
        self.assertEqual(site.profile_id, self.profile.id)
        self.assertIsNone(site.establishment_id)

    def test_site_one_owner_constraint(self):
        """Cannot have both profile AND establishment set."""
        with self.assertRaises(IntegrityError):
            Site.objects.create(
                profile=self.profile, establishment=self.est,
            )

    def test_site_one_owner_neither(self):
        """Cannot have neither profile nor establishment set."""
        with self.assertRaises(IntegrityError):
            Site.objects.create()

    def test_unique_custom_domain(self):
        """Two sites cannot share the same custom domain."""
        Site.objects.create(
            establishment=self.est, custom_domain='cafe.pt',
        )
        acc2 = _account(self.instance, 'bob')
        profile2 = _profile(acc2, self.instance, 'bob')
        est2 = _establishment(profile2, 'Org2', 'org2')
        with self.assertRaises(IntegrityError):
            Site.objects.create(
                establishment=est2, custom_domain='cafe.pt',
            )

    def test_empty_custom_domain_not_unique(self):
        """Multiple sites can have empty custom_domain (partial unique)."""
        Site.objects.create(establishment=self.est, custom_domain='')
        acc2 = _account(self.instance, 'bob')
        profile2 = _profile(acc2, self.instance, 'bob')
        est2 = _establishment(profile2, 'Org2', 'org2')
        site2 = Site.objects.create(establishment=est2, custom_domain='')
        self.assertEqual(site2.custom_domain, '')

    def test_hero_text_rendered(self):
        site = Site.objects.create(
            establishment=self.est, hero_text='**Welcome**',
        )
        self.assertIn('<strong>Welcome</strong>', site.hero_text_html)

    def test_subdomain_property(self):
        site = Site.objects.create(establishment=self.est)
        self.assertEqual(site.subdomain, self.est.slug)
        self.assertEqual(site.subdomain_type, 'org')

    def test_subdomain_profile(self):
        site = Site.objects.create(profile=self.profile)
        self.assertEqual(site.subdomain, self.profile.local_name)
        self.assertEqual(site.subdomain_type, 'u')

    def test_default_accent_color(self):
        site = Site.objects.create(establishment=self.est)
        self.assertEqual(site.accent_color, '#F5C518')

    def test_one_site_per_establishment(self):
        """OneToOneField prevents multiple sites per establishment."""
        Site.objects.create(establishment=self.est)
        with self.assertRaises(IntegrityError):
            Site.objects.create(establishment=self.est)


# ===========================================================================
# SitePage Model Tests
# ===========================================================================

class SitePageModelTest(TestCase):
    def setUp(self):
        self.instance = _instance()
        self.acc = _account(self.instance)
        self.profile = _profile(self.acc, self.instance)
        self.est = _establishment(self.profile)
        self.site = Site.objects.create(establishment=self.est)

    def test_create_page(self):
        page = SitePage.objects.create(
            site=self.site, title='About Us', content='We are great.',
        )
        self.assertEqual(page.slug, 'about-us')
        self.assertIn('We are great.', page.content_html)

    def test_slug_auto_generated(self):
        page = SitePage.objects.create(
            site=self.site, title='Our History',
        )
        self.assertEqual(page.slug, 'our-history')

    def test_slug_preserved_if_set(self):
        page = SitePage.objects.create(
            site=self.site, title='Custom', slug='my-slug',
        )
        self.assertEqual(page.slug, 'my-slug')

    def test_unique_slug_per_site(self):
        SitePage.objects.create(site=self.site, title='Page', slug='page')
        with self.assertRaises(IntegrityError):
            SitePage.objects.create(site=self.site, title='Page 2', slug='page')

    def test_same_slug_different_sites(self):
        """Different sites can have pages with the same slug."""
        acc2 = _account(self.instance, 'bob')
        profile2 = _profile(acc2, self.instance, 'bob')
        est2 = _establishment(profile2, 'Org2', 'org2')
        site2 = Site.objects.create(establishment=est2)

        SitePage.objects.create(site=self.site, title='About', slug='about')
        page2 = SitePage.objects.create(site=site2, title='About', slug='about')
        self.assertEqual(page2.slug, 'about')

    def test_ordering(self):
        p3 = SitePage.objects.create(site=self.site, title='C', slug='c', order=3)
        p1 = SitePage.objects.create(site=self.site, title='A', slug='a', order=1)
        p2 = SitePage.objects.create(site=self.site, title='B', slug='b', order=2)
        pages = list(self.site.pages.all())
        self.assertEqual([p.slug for p in pages], ['a', 'b', 'c'])

    def test_content_html_rendered(self):
        page = SitePage.objects.create(
            site=self.site, title='MD Page', content='*emphasis*',
        )
        self.assertIn('<em>emphasis</em>', page.content_html)


# ===========================================================================
# API Tests — Post CRUD
# ===========================================================================

class PostCreateAPITest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _instance()
        self.acc = _account(self.instance)
        self.profile = _profile(self.acc, self.instance)
        _add_wot2(self.profile, self.instance)

    def test_create_draft_no_wot(self):
        """Draft creation doesn't require WoT 2+."""
        from cms.api import create_post, PostCreateIn
        acc2 = _account(self.instance, 'newbie')
        prof2 = _profile(acc2, self.instance, 'newbie')
        # No verifications — WoT 0

        request = _auth_request(self.factory, acc2, prof2, 'post')
        payload = PostCreateIn(title='My Draft', content='Test content')
        result = create_post(request, payload)
        self.assertEqual(result.title, 'My Draft')
        self.assertEqual(result.status, 'draft')

    def test_create_published_requires_wot2(self):
        """Publishing requires WoT 2+."""
        from cms.api import create_post, PostCreateIn
        acc2 = _account(self.instance, 'newbie')
        prof2 = _profile(acc2, self.instance, 'newbie')

        request = _auth_request(self.factory, acc2, prof2, 'post')
        payload = PostCreateIn(
            title='My Post', content='Content', status='published',
        )
        with self.assertRaises(HttpError) as ctx:
            create_post(request, payload)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_create_published_with_wot2(self):
        from cms.api import create_post, PostCreateIn
        request = _auth_request(self.factory, self.acc, self.profile, 'post')
        payload = PostCreateIn(
            title='Published Post', content='Content', status='published',
        )
        result = create_post(request, payload)
        self.assertEqual(result.status, 'published')
        self.assertIsNotNone(result.published_at)

    def test_create_post_for_establishment(self):
        from cms.api import create_post, PostCreateIn
        est = _establishment(self.profile)
        _membership(self.profile, est, 'OWNER')

        request = _auth_request(self.factory, self.acc, self.profile, 'post')
        payload = PostCreateIn(
            title='Org Post', content='Content',
            establishment_id=est.id,
        )
        result = create_post(request, payload)
        self.assertEqual(result.establishment_id, est.id)

    def test_invalid_status_rejected(self):
        from cms.api import create_post, PostCreateIn
        request = _auth_request(self.factory, self.acc, self.profile, 'post')
        payload = PostCreateIn(
            title='Bad', content='X', status='invalid',
        )
        with self.assertRaises(HttpError) as ctx:
            create_post(request, payload)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_translation_flat_chain(self):
        """Translation of a translation should point to root original."""
        from cms.api import create_post, PostCreateIn

        request = _auth_request(self.factory, self.acc, self.profile, 'post')

        # Create original
        original = create_post(request, PostCreateIn(
            title='Original', content='EN text', language='en',
        ))

        # Create translation of original
        child = create_post(request, PostCreateIn(
            title='Traducao', content='PT text', language='pt',
            translation_of_id=original.id,
        ))
        self.assertEqual(child.translation_of_id, original.id)

        # Create translation of child — API should redirect to root
        grandchild = create_post(request, PostCreateIn(
            title='Traduccion', content='ES text', language='es',
            translation_of_id=child.id,
        ))
        self.assertEqual(grandchild.translation_of_id, original.id)

    def test_same_language_translation_rejected(self):
        """Cannot create a translation in the same language as the original."""
        from cms.api import create_post, PostCreateIn

        request = _auth_request(self.factory, self.acc, self.profile, 'post')
        original = create_post(request, PostCreateIn(
            title='Original EN', content='EN', language='en',
        ))

        with self.assertRaises(HttpError) as ctx:
            create_post(request, PostCreateIn(
                title='Also EN', content='EN2', language='en',
                translation_of_id=original.id,
            ))
        self.assertEqual(ctx.exception.status_code, 400)


class PostUpdateAPITest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _instance()
        self.acc = _account(self.instance)
        self.profile = _profile(self.acc, self.instance)
        _add_wot2(self.profile, self.instance)
        self.post = Post.objects.create(
            author=self.profile, title='Test', content='Content',
        )

    def test_update_own_post(self):
        from cms.api import update_post, PostUpdateIn
        request = _auth_request(self.factory, self.acc, self.profile, 'patch')
        result = update_post(request, self.post.id, PostUpdateIn(title='Updated'))
        self.assertEqual(result.title, 'Updated')

    def test_update_others_post_rejected(self):
        from cms.api import update_post, PostUpdateIn
        acc2 = _account(self.instance, 'bob')
        prof2 = _profile(acc2, self.instance, 'bob')

        request = _auth_request(self.factory, acc2, prof2, 'patch')
        with self.assertRaises(HttpError) as ctx:
            update_post(request, self.post.id, PostUpdateIn(title='Hacked'))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_superuser_can_edit_any_post(self):
        from cms.api import update_post, PostUpdateIn
        admin_acc = _account(self.instance, 'admin')
        admin_acc.is_superuser = True
        admin_acc.save()
        admin_prof = _profile(admin_acc, self.instance, 'admin')

        request = _auth_request(self.factory, admin_acc, admin_prof, 'patch')
        result = update_post(request, self.post.id, PostUpdateIn(title='Admin Edit'))
        self.assertEqual(result.title, 'Admin Edit')

    def test_est_admin_can_edit_org_post(self):
        """Establishment ADMIN can edit posts in their org."""
        from cms.api import update_post, PostUpdateIn
        est = _establishment(self.profile)
        _membership(self.profile, est, 'OWNER')

        # Create org post
        org_post = Post.objects.create(
            author=self.profile, title='Org Post', content='X',
            establishment=est,
        )

        # Another profile who is ADMIN
        acc2 = _account(self.instance, 'bob')
        prof2 = _profile(acc2, self.instance, 'bob')
        _membership(prof2, est, 'ADMIN')

        request = _auth_request(self.factory, acc2, prof2, 'patch')
        result = update_post(request, org_post.id, PostUpdateIn(title='Admin Updated'))
        self.assertEqual(result.title, 'Admin Updated')

    def test_est_member_cannot_edit_org_post(self):
        """Establishment MEMBER cannot edit other people's posts."""
        from cms.api import update_post, PostUpdateIn
        est = _establishment(self.profile)
        _membership(self.profile, est, 'OWNER')

        org_post = Post.objects.create(
            author=self.profile, title='Org Post', content='X',
            establishment=est,
        )

        acc2 = _account(self.instance, 'charlie')
        prof2 = _profile(acc2, self.instance, 'charlie')
        _membership(prof2, est, 'MEMBER')

        request = _auth_request(self.factory, acc2, prof2, 'patch')
        with self.assertRaises(HttpError) as ctx:
            update_post(request, org_post.id, PostUpdateIn(title='Nope'))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_publish_draft_requires_wot2(self):
        """Changing draft → published requires WoT 2+."""
        from cms.api import update_post, PostUpdateIn
        acc2 = _account(self.instance, 'newbie')
        prof2 = _profile(acc2, self.instance, 'newbie')

        draft = Post.objects.create(
            author=prof2, title='My Draft', content='X', status='draft',
        )
        request = _auth_request(self.factory, acc2, prof2, 'patch')
        with self.assertRaises(HttpError) as ctx:
            update_post(request, draft.id, PostUpdateIn(status='published'))
        self.assertEqual(ctx.exception.status_code, 403)


class PostDeleteAPITest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _instance()
        self.acc = _account(self.instance)
        self.profile = _profile(self.acc, self.instance)

    def test_delete_own_post(self):
        from cms.api import delete_post
        post = Post.objects.create(
            author=self.profile, title='Delete Me', content='X',
        )
        request = _auth_request(self.factory, self.acc, self.profile, 'delete')
        result = delete_post(request, post.id)
        self.assertTrue(result['ok'])
        self.assertFalse(Post.objects.filter(id=post.id).exists())

    def test_delete_others_post_rejected(self):
        from cms.api import delete_post
        post = Post.objects.create(
            author=self.profile, title='Protected', content='X',
        )
        acc2 = _account(self.instance, 'bob')
        prof2 = _profile(acc2, self.instance, 'bob')

        request = _auth_request(self.factory, acc2, prof2, 'delete')
        with self.assertRaises(HttpError) as ctx:
            delete_post(request, post.id)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_delete_cleans_up_files(self):
        """Deleting a post removes associated ObjectFiles."""
        from cms.api import delete_post
        post = Post.objects.create(
            author=self.profile, title='With Files', content='X',
        )
        ObjectFile.objects.create(
            object_id=post.id, filename='test.pdf',
            mime_type='application/pdf', size_bytes=100,
            uploaded_by=self.profile,
        )
        self.assertEqual(ObjectFile.objects.filter(object_id=post.id).count(), 1)

        request = _auth_request(self.factory, self.acc, self.profile, 'delete')
        delete_post(request, post.id)
        self.assertEqual(ObjectFile.objects.filter(object_id=post.id).count(), 0)


# ===========================================================================
# API Tests — Post Listing / Visibility
# ===========================================================================

class PostListAPITest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _instance()
        self.acc = _account(self.instance)
        self.profile = _profile(self.acc, self.instance)
        _add_wot2(self.profile, self.instance)

    def test_only_published_in_public_feed(self):
        from cms.api import list_posts
        Post.objects.create(
            author=self.profile, title='Draft', content='X', status='draft',
        )
        Post.objects.create(
            author=self.profile, title='Published', content='X', status='published',
        )

        # Anonymous request
        request = self.factory.get('/fake/')
        request.auth_profile = None
        request.GET = request.GET.copy()
        result = list_posts(request)
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['items'][0].title, 'Published')

    def test_translations_hidden_in_public_feed(self):
        """Public feed hides translations (shows only originals)."""
        from cms.api import list_posts
        original = Post.objects.create(
            author=self.profile, title='Original', content='EN',
            language='en', status='published',
        )
        Post.objects.create(
            author=self.profile, title='Traducao', content='PT',
            language='pt', status='published', translation_of=original,
        )

        request = self.factory.get('/fake/')
        request.auth_profile = None
        request.GET = request.GET.copy()
        result = list_posts(request)
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['items'][0].title, 'Original')

    def test_language_filter_shows_translations(self):
        """Explicit language filter shows translations too."""
        from cms.api import list_posts
        original = Post.objects.create(
            author=self.profile, title='EN Post', content='EN',
            language='en', status='published',
        )
        Post.objects.create(
            author=self.profile, title='PT Post', content='PT',
            language='pt', status='published', translation_of=original,
        )

        request = self.factory.get('/fake/')
        request.auth_profile = None
        request.GET = request.GET.copy()
        result = list_posts(request, language='pt')
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['items'][0].title, 'PT Post')


class PostDetailVisibilityTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _instance()
        self.acc = _account(self.instance)
        self.profile = _profile(self.acc, self.instance)

    def test_draft_hidden_from_anonymous(self):
        from cms.api import get_post
        post = Post.objects.create(
            author=self.profile, title='Draft', content='X', status='draft',
        )
        request = self.factory.get('/fake/')
        request.auth_profile = None
        with self.assertRaises(HttpError) as ctx:
            get_post(request, post.id)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_draft_visible_to_author(self):
        from cms.api import get_post
        post = Post.objects.create(
            author=self.profile, title='Draft', content='X', status='draft',
        )
        request = _auth_request(self.factory, self.acc, self.profile)
        result = get_post(request, post.id)
        self.assertEqual(result.title, 'Draft')

    def test_published_visible_to_anonymous(self):
        from cms.api import get_post
        post = Post.objects.create(
            author=self.profile, title='Public', content='X', status='published',
        )
        request = self.factory.get('/fake/')
        request.auth_profile = None
        result = get_post(request, post.id)
        self.assertEqual(result.title, 'Public')


# ===========================================================================
# API Tests — RSS
# ===========================================================================

class RSSFeedTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _instance()
        self.acc = _account(self.instance)
        self.profile = _profile(self.acc, self.instance)

    def test_rss_returns_xml(self):
        from cms.api import posts_rss
        Post.objects.create(
            author=self.profile, title='RSS Post', content='Content',
            status='published',
        )
        request = self.factory.get('/fake/')
        response = posts_rss(request)
        self.assertEqual(response['Content-Type'], 'application/rss+xml; charset=utf-8')
        content = response.content.decode()
        self.assertIn('<?xml', content)
        self.assertIn('<rss', content)
        self.assertIn('RSS Post', content)

    def test_rss_excludes_drafts(self):
        from cms.api import posts_rss
        Post.objects.create(
            author=self.profile, title='Draft', content='X', status='draft',
        )
        request = self.factory.get('/fake/')
        response = posts_rss(request)
        content = response.content.decode()
        self.assertNotIn('Draft', content)

    def test_rss_filter_by_establishment(self):
        from cms.api import posts_rss
        est = _establishment(self.profile)
        Post.objects.create(
            author=self.profile, title='Org Post', content='X',
            status='published', establishment=est,
        )
        Post.objects.create(
            author=self.profile, title='Personal', content='X',
            status='published',
        )
        request = self.factory.get('/fake/')
        response = posts_rss(request, establishment_slug=est.slug)
        content = response.content.decode()
        self.assertIn('Org Post', content)
        self.assertNotIn('Personal', content)


# ===========================================================================
# API Tests — Custom Domain
# ===========================================================================

class CustomDomainAPITest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _instance()
        self.acc = _account(self.instance)
        self.profile = _profile(self.acc, self.instance)
        self.est = _establishment(self.profile)
        _membership(self.profile, self.est, 'OWNER')

    def test_set_custom_domain(self):
        from cms.api import set_custom_domain, CustomDomainIn
        request = _auth_request(self.factory, self.acc, self.profile, 'post')
        result = set_custom_domain(request, self.est.id, CustomDomainIn(domain='cafe.pt'))
        self.assertEqual(result.custom_domain, 'cafe.pt')
        self.assertFalse(result.custom_domain_verified)

    def test_reject_parahub_subdomain(self):
        from cms.api import set_custom_domain, CustomDomainIn
        request = _auth_request(self.factory, self.acc, self.profile, 'post')
        with self.assertRaises(HttpError) as ctx:
            set_custom_domain(
                request, self.est.id,
                CustomDomainIn(domain='evil.parahub.io'),
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_reject_parahub_io_itself(self):
        from cms.api import set_custom_domain, CustomDomainIn
        request = _auth_request(self.factory, self.acc, self.profile, 'post')
        with self.assertRaises(HttpError) as ctx:
            set_custom_domain(
                request, self.est.id,
                CustomDomainIn(domain='parahub.io'),
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_reject_invalid_domain_format(self):
        from cms.api import set_custom_domain, CustomDomainIn
        request = _auth_request(self.factory, self.acc, self.profile, 'post')
        with self.assertRaises(HttpError) as ctx:
            set_custom_domain(
                request, self.est.id,
                CustomDomainIn(domain='not a domain!'),
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_reject_domain_already_taken(self):
        from cms.api import set_custom_domain, CustomDomainIn
        # First site takes the domain
        Site.objects.get_or_create(establishment=self.est)
        site = Site.objects.get(establishment=self.est)
        site.custom_domain = 'taken.pt'
        site.save()

        # Second establishment tries
        acc2 = _account(self.instance, 'bob')
        prof2 = _profile(acc2, self.instance, 'bob')
        est2 = _establishment(prof2, 'Org2', 'org2')
        _membership(prof2, est2, 'OWNER')

        request = _auth_request(self.factory, acc2, prof2, 'post')
        with self.assertRaises(HttpError) as ctx:
            set_custom_domain(
                request, est2.id,
                CustomDomainIn(domain='taken.pt'),
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_clear_custom_domain(self):
        from cms.api import set_custom_domain, CustomDomainIn
        site, _ = Site.objects.get_or_create(establishment=self.est)
        site.custom_domain = 'old.pt'
        site.custom_domain_verified = True
        site.save()

        request = _auth_request(self.factory, self.acc, self.profile, 'post')
        with patch('cms.api._trigger_ssl_removal'):
            result = set_custom_domain(
                request, self.est.id, CustomDomainIn(domain=''),
            )
        self.assertEqual(result.custom_domain, '')
        self.assertFalse(result.custom_domain_verified)

    def test_reject_reserved_tld_local(self):
        """SSRF protection: .local domains must be rejected."""
        from cms.api import set_custom_domain, CustomDomainIn
        request = _auth_request(self.factory, self.acc, self.profile, 'post')
        with self.assertRaises(HttpError) as ctx:
            set_custom_domain(
                request, self.est.id,
                CustomDomainIn(domain='internal.service.local'),
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('not allowed', str(ctx.exception.message))

    def test_reject_reserved_tld_localhost(self):
        """SSRF protection: .localhost domains must be rejected."""
        from cms.api import set_custom_domain, CustomDomainIn
        request = _auth_request(self.factory, self.acc, self.profile, 'post')
        with self.assertRaises(HttpError) as ctx:
            set_custom_domain(
                request, self.est.id,
                CustomDomainIn(domain='app.localhost'),
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_reject_reserved_tld_internal(self):
        """SSRF protection: .internal domains must be rejected."""
        from cms.api import set_custom_domain, CustomDomainIn
        request = _auth_request(self.factory, self.acc, self.profile, 'post')
        with self.assertRaises(HttpError) as ctx:
            set_custom_domain(
                request, self.est.id,
                CustomDomainIn(domain='metadata.corp.internal'),
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_reject_onion_domain(self):
        """SSRF protection: .onion domains must be rejected."""
        from cms.api import set_custom_domain, CustomDomainIn
        request = _auth_request(self.factory, self.acc, self.profile, 'post')
        with self.assertRaises(HttpError) as ctx:
            set_custom_domain(
                request, self.est.id,
                CustomDomainIn(domain='hidden.service.onion'),
            )
        self.assertEqual(ctx.exception.status_code, 400)

    @patch('cms.api.socket.gethostbyname', return_value='127.0.0.1')
    def test_reject_domain_resolving_to_loopback(self, mock_dns):
        """SSRF protection: domain resolving to 127.x.x.x must be rejected."""
        from cms.api import set_custom_domain, CustomDomainIn
        request = _auth_request(self.factory, self.acc, self.profile, 'post')
        with self.assertRaises(HttpError) as ctx:
            set_custom_domain(
                request, self.est.id,
                CustomDomainIn(domain='evil.example.com'),
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('private', str(ctx.exception.message).lower())

    @patch('cms.api.socket.gethostbyname', return_value='<LXC_IP>')
    def test_reject_domain_resolving_to_private_10(self, mock_dns):
        """SSRF protection: domain resolving to 10.x.x.x must be rejected."""
        from cms.api import set_custom_domain, CustomDomainIn
        request = _auth_request(self.factory, self.acc, self.profile, 'post')
        with self.assertRaises(HttpError) as ctx:
            set_custom_domain(
                request, self.est.id,
                CustomDomainIn(domain='evil2.example.com'),
            )
        self.assertEqual(ctx.exception.status_code, 400)

    @patch('cms.api.socket.gethostbyname', return_value='169.254.169.254')
    def test_reject_domain_resolving_to_metadata(self, mock_dns):
        """SSRF protection: domain resolving to 169.254.x.x (cloud metadata) must be rejected."""
        from cms.api import set_custom_domain, CustomDomainIn
        request = _auth_request(self.factory, self.acc, self.profile, 'post')
        with self.assertRaises(HttpError) as ctx:
            set_custom_domain(
                request, self.est.id,
                CustomDomainIn(domain='metadata.example.com'),
            )
        self.assertEqual(ctx.exception.status_code, 400)

    @patch('cms.api.socket.gethostbyname', return_value='192.168.1.1')
    def test_reject_domain_resolving_to_private_192(self, mock_dns):
        """SSRF protection: domain resolving to 192.168.x.x must be rejected."""
        from cms.api import set_custom_domain, CustomDomainIn
        request = _auth_request(self.factory, self.acc, self.profile, 'post')
        with self.assertRaises(HttpError) as ctx:
            set_custom_domain(
                request, self.est.id,
                CustomDomainIn(domain='router.example.com'),
            )
        self.assertEqual(ctx.exception.status_code, 400)

    @patch('cms.api.socket.gethostbyname', side_effect=__import__('socket').gaierror)
    def test_allow_domain_that_doesnt_resolve_yet(self, mock_dns):
        """Domain that doesn't resolve yet is OK — user may not have set DNS."""
        from cms.api import set_custom_domain, CustomDomainIn
        request = _auth_request(self.factory, self.acc, self.profile, 'post')
        result = set_custom_domain(
            request, self.est.id,
            CustomDomainIn(domain='future.cafe.pt'),
        )
        self.assertEqual(result.custom_domain, 'future.cafe.pt')


# ===========================================================================
# API Tests — Content Size Limits
# ===========================================================================

class ContentSizeLimitTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _instance()
        self.acc = _account(self.instance)
        self.profile = _profile(self.acc, self.instance)

    def test_reject_oversized_post_content(self):
        from cms.api import create_post, PostCreateIn, MAX_POST_CONTENT_SIZE
        request = _auth_request(self.factory, self.acc, self.profile, 'post')
        huge_content = 'x' * (MAX_POST_CONTENT_SIZE + 1)
        with self.assertRaises(HttpError) as ctx:
            create_post(request, PostCreateIn(
                title='Test', content=huge_content, status='draft',
            ))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('too large', str(ctx.exception.message).lower())

    def test_allow_max_size_post_content(self):
        from cms.api import create_post, PostCreateIn, MAX_POST_CONTENT_SIZE
        request = _auth_request(self.factory, self.acc, self.profile, 'post')
        content = 'x' * MAX_POST_CONTENT_SIZE
        result = create_post(request, PostCreateIn(
            title='Test OK', content=content, status='draft',
        ))
        self.assertEqual(result.title, 'Test OK')


# ===========================================================================
# API Tests — Site Resolve
# ===========================================================================

class SiteResolveAPITest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _instance()
        self.acc = _account(self.instance)
        self.profile = _profile(self.acc, self.instance)
        self.est = _establishment(self.profile)

    def test_resolve_by_slug_org(self):
        from cms.api import resolve_site
        request = self.factory.get('/fake/')
        result = resolve_site(request, slug=self.est.slug, type='org')
        self.assertEqual(result.establishment_slug, self.est.slug)

    def test_resolve_by_slug_user(self):
        from cms.api import resolve_site
        request = self.factory.get('/fake/')
        result = resolve_site(request, slug=self.profile.local_name, type='u')
        self.assertEqual(result.profile_local_name, self.profile.local_name)

    def test_resolve_by_custom_domain(self):
        from cms.api import resolve_site
        site = Site.objects.create(
            establishment=self.est, custom_domain='cafe.pt',
            custom_domain_verified=True,
        )
        request = self.factory.get('/fake/')
        result = resolve_site(request, domain='cafe.pt')
        self.assertEqual(result.id, site.id)

    def test_resolve_unverified_custom_domain_404(self):
        from cms.api import resolve_site
        Site.objects.create(
            establishment=self.est, custom_domain='unverified.pt',
            custom_domain_verified=False,
        )
        request = self.factory.get('/fake/')
        with self.assertRaises(HttpError) as ctx:
            resolve_site(request, domain='unverified.pt')
        self.assertEqual(ctx.exception.status_code, 404)

    def test_resolve_missing_params(self):
        from cms.api import resolve_site
        request = self.factory.get('/fake/')
        with self.assertRaises(HttpError) as ctx:
            resolve_site(request)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_resolve_auto_creates_site(self):
        """Resolving a slug auto-creates a Site if it doesn't exist."""
        from cms.api import resolve_site
        self.assertFalse(Site.objects.filter(establishment=self.est).exists())
        request = self.factory.get('/fake/')
        result = resolve_site(request, slug=self.est.slug, type='org')
        self.assertTrue(Site.objects.filter(establishment=self.est).exists())

    def test_resolve_inactive_site_404(self):
        from cms.api import resolve_site
        site = Site.objects.create(establishment=self.est, is_active=False)
        request = self.factory.get('/fake/')
        with self.assertRaises(HttpError) as ctx:
            resolve_site(request, slug=self.est.slug, type='org')
        self.assertEqual(ctx.exception.status_code, 404)


# ===========================================================================
# API Tests — Profile Site Owner Check
# ===========================================================================

class ProfileSiteOwnerTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _instance()
        self.acc = _account(self.instance)
        self.profile = _profile(self.acc, self.instance)

    def test_owner_can_update(self):
        from cms.api import update_profile_site, SiteUpdateIn
        Site.objects.get_or_create(profile=self.profile)
        request = _auth_request(self.factory, self.acc, self.profile, 'patch')
        result = update_profile_site(
            request, self.profile.local_name,
            SiteUpdateIn(accent_color='#FF0000'),
        )
        self.assertEqual(result.accent_color, '#FF0000')

    def test_non_owner_rejected(self):
        from cms.api import update_profile_site, SiteUpdateIn
        Site.objects.get_or_create(profile=self.profile)
        acc2 = _account(self.instance, 'bob')
        prof2 = _profile(acc2, self.instance, 'bob')

        request = _auth_request(self.factory, acc2, prof2, 'patch')
        with self.assertRaises(HttpError) as ctx:
            update_profile_site(
                request, self.profile.local_name,
                SiteUpdateIn(accent_color='#FF0000'),
            )
        self.assertEqual(ctx.exception.status_code, 403)

    def test_superuser_bypass(self):
        from cms.api import update_profile_site, SiteUpdateIn
        Site.objects.get_or_create(profile=self.profile)
        admin_acc = _account(self.instance, 'admin')
        admin_acc.is_superuser = True
        admin_acc.save()
        admin_prof = _profile(admin_acc, self.instance, 'admin')

        request = _auth_request(self.factory, admin_acc, admin_prof, 'patch')
        result = update_profile_site(
            request, self.profile.local_name,
            SiteUpdateIn(accent_color='#00FF00'),
        )
        self.assertEqual(result.accent_color, '#00FF00')


# ===========================================================================
# API Tests — Site Page CRUD
# ===========================================================================

class SitePageAPITest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _instance()
        self.acc = _account(self.instance)
        self.profile = _profile(self.acc, self.instance)
        self.est = _establishment(self.profile)
        _membership(self.profile, self.est, 'OWNER')
        self.site = Site.objects.create(establishment=self.est)

    def test_create_page(self):
        from cms.api import create_site_page, SitePageCreateIn
        request = _auth_request(self.factory, self.acc, self.profile, 'post')
        result = create_site_page(
            request, self.est.id,
            SitePageCreateIn(title='About', content='# About Us'),
        )
        self.assertEqual(result.title, 'About')
        self.assertEqual(result.slug, 'about')
        self.assertIn('<h1>About Us</h1>', result.content_html)

    def test_list_pages_only_published(self):
        from cms.api import list_site_pages
        SitePage.objects.create(
            site=self.site, title='Published', slug='pub', is_published=True,
        )
        SitePage.objects.create(
            site=self.site, title='Hidden', slug='hidden', is_published=False,
        )
        request = self.factory.get('/fake/')
        result = list_site_pages(request, self.est.id)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, 'Published')

    def test_delete_page(self):
        from cms.api import delete_site_page
        page = SitePage.objects.create(
            site=self.site, title='Delete Me', slug='del',
        )
        request = _auth_request(self.factory, self.acc, self.profile, 'delete')
        result = delete_site_page(request, self.est.id, page.id)
        self.assertTrue(result['ok'])
        self.assertFalse(SitePage.objects.filter(id=page.id).exists())

    def test_get_page_by_slug(self):
        from cms.api import get_site_page_by_slug
        SitePage.objects.create(
            site=self.site, title='History', slug='history',
            content='Our history...', is_published=True,
        )
        request = self.factory.get('/fake/')
        result = get_site_page_by_slug(request, self.est.id, 'history')
        self.assertEqual(result.title, 'History')

    def test_unpublished_page_404(self):
        from cms.api import get_site_page_by_slug
        SitePage.objects.create(
            site=self.site, title='Draft Page', slug='draft',
            is_published=False,
        )
        request = self.factory.get('/fake/')
        with self.assertRaises(HttpError) as ctx:
            get_site_page_by_slug(request, self.est.id, 'draft')
        self.assertEqual(ctx.exception.status_code, 404)

    def test_duplicate_slug_rejected_on_update(self):
        from cms.api import update_site_page, SitePageUpdateIn
        SitePage.objects.create(
            site=self.site, title='Page A', slug='page-a',
        )
        page_b = SitePage.objects.create(
            site=self.site, title='Page B', slug='page-b',
        )
        request = _auth_request(self.factory, self.acc, self.profile, 'patch')
        with self.assertRaises(HttpError) as ctx:
            update_site_page(
                request, self.est.id, page_b.id,
                SitePageUpdateIn(slug='page-a'),
            )
        self.assertEqual(ctx.exception.status_code, 400)
