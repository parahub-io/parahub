"""
Viewer-language machine translation on the items API (translate_to param).

Market is a pure-MT content class: Item has no authoritative human translation
layer, so any translated content carries is_translated=True. Source language
is the auto-detected Item.language (empty = unknown → skip).

Who may spend a provider call: the list translates titles fresh (shared
per-request budget) and serves descriptions from cache only; the DETAIL
response spends nothing at all, because a page render awaits it; the dedicated
`/{id}/translation/` endpoint is the one path that fills the cache, and the
client calls it after the page is already on screen.

Non-English literals below are translation-test fixtures (CLAUDE.md rule 15
exception) — ru/pt source text is required to exercise the pipeline.
"""

from unittest.mock import MagicMock, patch

import orjson
from django.http import HttpResponse
from django.test import TestCase, RequestFactory

from identity.models import Account, Profile
from core.models import Instance
from market.models import Item
from parahub.endpoints.items import (
    MT_PER_REQUEST_CAP, get_item, get_item_translation, list_items, update_item,
    ItemUpdateRequest,
)

LONG_DESC = 'palavra da descrição longa ' * 10  # >200 chars → list truncation


def _fake_translation_provider():
    """Provider double: prefixes text with the target language."""
    provider = MagicMock()
    provider.translate.side_effect = (
        lambda text, source_lang, target_lang, html=False: f'[{target_lang}] {text}')
    return provider


class ItemTranslationTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test Instance', public_key='test-key')
        account = Account.objects.create_user(
            username='mtseller', email='mtseller@test.parahub.io',
            password='x', instance=cls.instance)
        cls.owner = Profile.objects.create(
            account=account, instance=cls.instance, local_name='mtseller',
            display_name='MT Seller', is_primary=True,
            profile_type=Profile.ProfileType.PERSONAL)
        cls.factory = RequestFactory()

    @classmethod
    def _make_item(cls, title='Pão fresco', description=LONG_DESC,
                   language='pt', **kwargs):
        return Item.objects.create(
            owner=cls.owner, title=title, description=description,
            type='CREDIT', language=language, **kwargs)

    def _request(self, viewer=None):
        request = self.factory.get('/api/v1/items/')
        if viewer is not None:
            request.user = viewer.account
            request.auth = viewer
            request.auth_profile = viewer
        return request

    def _list(self, **params):
        resp = list_items(self._request(), **params)
        if isinstance(resp, HttpResponse):
            return orjson.loads(resp.content)['items']
        return [i.model_dump(mode='json') for i in resp['items']]

    def _by_id(self, items, item):
        return next(i for i in items if i['id'] == item.id)


class ItemListTranslationTest(ItemTranslationTestBase):

    @patch('parahub.services.translation.TranslationService.get_provider')
    def test_list_translates_title_fresh_and_caches(self, mock_get_provider):
        mock_get_provider.return_value = _fake_translation_provider()
        item = self._make_item()

        row = self._by_id(self._list(translate_to='ru'), item)
        self.assertEqual(row['translated_title'], '[ru] Pão fresco')
        self.assertTrue(row['is_translated'])
        # Description is cache-only on list paths — no fresh MT for it here.
        self.assertIsNone(row['translated_description'])

        item.refresh_from_db()
        self.assertEqual(item.mt_cache['ru']['title'], '[ru] Pão fresco')
        self.assertNotIn('description', item.mt_cache['ru'])

    @patch('parahub.services.translation.TranslationService.get_provider')
    def test_list_serves_cached_description_truncated(self, mock_get_provider):
        mock_get_provider.return_value = _fake_translation_provider()
        long_translated = 'слово перевода описания ' * 10
        item = self._make_item()
        Item.objects.filter(pk=item.pk).update(mt_cache={
            'ru': {'title': 'Свежий хлеб', 'description': long_translated}})

        row = self._by_id(self._list(translate_to='ru'), item)
        self.assertEqual(row['translated_title'], 'Свежий хлеб')
        self.assertEqual(row['translated_description'],
                         long_translated[:200] + '…')
        self.assertTrue(row['is_translated'])
        mock_get_provider.assert_not_called()

    @patch('parahub.services.translation.TranslationService.get_provider')
    def test_same_language_and_unknown_source_are_skipped(self, mock_get_provider):
        mock_get_provider.return_value = _fake_translation_provider()
        same_lang = self._make_item(title='Хлеб', language='ru')
        no_lang = self._make_item(title='Mystery', language='')

        items = self._list(translate_to='ru')
        for item in (same_lang, no_lang):
            row = self._by_id(items, item)
            self.assertIsNone(row['translated_title'])
            self.assertFalse(row['is_translated'])
        mock_get_provider.assert_not_called()

    @patch('parahub.services.translation.TranslationService.get_provider')
    def test_unknown_target_language_is_ignored(self, mock_get_provider):
        mock_get_provider.return_value = _fake_translation_provider()
        item = self._make_item()
        row = self._by_id(self._list(translate_to='xx'), item)
        self.assertIsNone(row['translated_title'])
        self.assertFalse(row['is_translated'])
        mock_get_provider.assert_not_called()

    @patch('parahub.services.translation.TranslationService.get_provider')
    def test_no_translate_to_returns_plain_shape(self, mock_get_provider):
        mock_get_provider.return_value = _fake_translation_provider()
        item = self._make_item()
        row = self._by_id(self._list(), item)
        self.assertIsNone(row['translated_title'])
        self.assertFalse(row['is_translated'])
        mock_get_provider.assert_not_called()

    @patch('parahub.services.translation.TranslationService.get_provider')
    def test_fresh_mt_capped_per_request(self, mock_get_provider):
        provider = _fake_translation_provider()
        mock_get_provider.return_value = provider
        for i in range(MT_PER_REQUEST_CAP + 2):
            self._make_item(title=f'Anúncio {i}')

        items = self._list(translate_to='ru')
        translated = [i for i in items if i['translated_title']]
        self.assertEqual(len(translated), MT_PER_REQUEST_CAP)
        self.assertEqual(provider.translate.call_count, MT_PER_REQUEST_CAP)

        # The next request warms the remaining items from a fresh budget.
        translated_after = [
            i for i in self._list(translate_to='ru') if i['translated_title']]
        self.assertEqual(len(translated_after), MT_PER_REQUEST_CAP + 2)

    @patch('parahub.services.translation.TranslationService.get_provider')
    def test_provider_down_degrades_to_original(self, mock_get_provider):
        mock_get_provider.return_value = None
        item = self._make_item()
        row = self._by_id(self._list(translate_to='ru'), item)
        self.assertIsNone(row['translated_title'])
        self.assertFalse(row['is_translated'])
        self.assertEqual(row['title'], 'Pão fresco')
        item.refresh_from_db()
        self.assertEqual(item.mt_cache, {})

    @patch('parahub.services.translation.TranslationService.get_provider')
    def test_orm_path_translates_too(self, mock_get_provider):
        mock_get_provider.return_value = _fake_translation_provider()
        item = self._make_item(title='Pão de milho')
        # q= forces the ORM branch (the raw path bails on search).
        resp = list_items(self._request(), q='milho', translate_to='ru')
        self.assertIsInstance(resp, dict, 'ORM path did not run')
        row = self._by_id(
            [i.model_dump(mode='json') for i in resp['items']], item)
        self.assertEqual(row['translated_title'], '[ru] Pão de milho')
        self.assertTrue(row['is_translated'])


class ItemDetailTranslationTest(ItemTranslationTestBase):

    def _detail(self, item, **params):
        resp = get_item(self._request(), item.id, **params)
        return resp.model_dump(mode='json')

    def _translation(self, item, lang):
        resp = get_item_translation(self._request(), item.id, lang=lang)
        return resp.model_dump(mode='json')

    @patch('parahub.services.translation.TranslationService.get_provider')
    def test_detail_never_calls_the_provider(self, mock_get_provider):
        """The detail response is awaited by the page render, so it must be
        cache-only: a cold listing would otherwise freeze the navigation for a
        provider round-trip per field."""
        provider = _fake_translation_provider()
        mock_get_provider.return_value = provider
        item = self._make_item()

        data = self._detail(item, translate_to='ru')
        provider.translate.assert_not_called()
        self.assertIsNone(data['translated_title'])
        self.assertIsNone(data['translated_description'])
        self.assertFalse(data['is_translated'])

    @patch('parahub.services.translation.TranslationService.get_provider')
    def test_translation_endpoint_translates_both_fields_and_fills_cache(self, mock_get_provider):
        provider = _fake_translation_provider()
        mock_get_provider.return_value = provider
        item = self._make_item()

        data = self._translation(item, 'ru')
        self.assertEqual(data['translated_title'], '[ru] Pão fresco')
        self.assertEqual(data['translated_description'], f'[ru] {LONG_DESC}')
        self.assertTrue(data['is_translated'])
        self.assertEqual(data['language'], 'pt')
        self.assertEqual(provider.translate.call_count, 2)

        item.refresh_from_db()
        self.assertEqual(item.mt_cache['ru']['description'], f'[ru] {LONG_DESC}')

        # The detail response now serves both fields from that cache, in full.
        provider.translate.reset_mock()
        data = self._detail(item, translate_to='ru')
        self.assertEqual(data['translated_title'], '[ru] Pão fresco')
        self.assertEqual(data['translated_description'], f'[ru] {LONG_DESC}')
        provider.translate.assert_not_called()

        # And the LIST shows the truncated cached description.
        row = self._by_id(self._list(translate_to='ru'), item)
        self.assertEqual(row['translated_description'],
                         f'[ru] {LONG_DESC}'[:200] + '…')

    @patch('parahub.services.translation.TranslationService.get_provider')
    def test_translation_endpoint_completes_partial_cache(self, mock_get_provider):
        provider = _fake_translation_provider()
        mock_get_provider.return_value = provider
        item = self._make_item()
        Item.objects.filter(pk=item.pk).update(
            mt_cache={'ru': {'title': 'Кэшированный заголовок'}})

        data = self._translation(item, 'ru')
        self.assertEqual(data['translated_title'], 'Кэшированный заголовок')
        self.assertEqual(data['translated_description'], f'[ru] {LONG_DESC}')
        # Only the missing description costs a provider call.
        self.assertEqual(provider.translate.call_count, 1)

    @patch('parahub.services.translation.TranslationService.get_provider')
    def test_detail_serves_cached_description_untruncated(self, mock_get_provider):
        """The list truncates its description to 200 chars; the detail view must
        not inherit that truncation from the shared resolver."""
        provider = _fake_translation_provider()
        mock_get_provider.return_value = provider
        item = self._make_item()
        Item.objects.filter(pk=item.pk).update(
            mt_cache={'ru': {'title': '[ru] Pão fresco',
                             'description': f'[ru] {LONG_DESC}'}})

        data = self._detail(item, translate_to='ru')
        self.assertEqual(data['translated_description'], f'[ru] {LONG_DESC}')
        self.assertGreater(len(data['translated_description']), 200)
        provider.translate.assert_not_called()


class ItemTranslationInvalidationTest(ItemTranslationTestBase):

    def _put(self, item, **fields):
        request = self.factory.put(f'/api/v1/items/{item.id}/')
        request.user = self.owner.account
        request.auth = self.owner
        request.auth_profile = self.owner
        resp = update_item(request, item.id, ItemUpdateRequest(**fields))
        self.assertNotIsInstance(resp, tuple, f'update failed: {resp}')
        item.refresh_from_db()
        return resp

    @patch('parahub.services.translation.TranslationService.get_provider')
    def test_real_text_edit_wipes_mt_cache(self, mock_get_provider):
        mock_get_provider.return_value = _fake_translation_provider()
        item = self._make_item()
        Item.objects.filter(pk=item.pk).update(
            mt_cache={'ru': {'title': 'Старый перевод'}})
        item.refresh_from_db()

        self._put(item, title='Pão de centeio novo')
        self.assertEqual(item.mt_cache, {})

    @patch('parahub.endpoints.items.detect_content_language', return_value='pt')
    @patch('parahub.services.translation.TranslationService.get_provider')
    def test_unchanged_text_put_keeps_cache(self, mock_get_provider, _mock_detect):
        mock_get_provider.return_value = _fake_translation_provider()
        item = self._make_item()
        Item.objects.filter(pk=item.pk).update(
            mt_cache={'ru': {'title': 'Тёплый кэш'}})
        item.refresh_from_db()

        # Full-form PUT resending identical text (plus an unrelated field).
        self._put(item, title=item.title, description=item.description,
                  is_active=True)
        self.assertEqual(item.mt_cache['ru']['title'], 'Тёплый кэш')

    @patch('parahub.services.translation.TranslationService.get_provider')
    def test_description_edit_wipes_cache(self, mock_get_provider):
        mock_get_provider.return_value = _fake_translation_provider()
        item = self._make_item()
        Item.objects.filter(pk=item.pk).update(
            mt_cache={'ru': {'description': 'Старое описание'}})
        item.refresh_from_db()

        self._put(item, description='Descrição completamente nova do produto.')
        self.assertEqual(item.mt_cache, {})
