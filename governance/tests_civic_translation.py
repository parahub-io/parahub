"""
Viewer-language machine translation on the civic ideas API (translate_to param).

Ideas are pure UGC: MT never touches ballot text (a promoted poll gets a fresh
staff formulation), so translating them cannot distort a vote. Source language
is auto-detected at creation (CivicIdea.language, empty = unknown → skip).
Idea text is immutable after creation, so mt_cache has no invalidation path.
The list is the terminal view (no detail page): title AND body both translate
fresh under the shared per-request budget and are cached on the row.

Non-English literals below are translation-test fixtures (CLAUDE.md rule 15
exception) — ru source text is required to exercise the pipeline.
"""
from unittest.mock import MagicMock, patch

from governance.civic_api import (
    IdeaCreateRequest, create_idea, list_ideas, support_idea,
)
from governance.models import CivicIdea
from governance.tests_civic import CivicPollTestCase
from parahub.services.translation import MT_PER_REQUEST_CAP

RU_TITLE = 'Больше скамеек в парке у реки'
RU_BODY = 'В парке у реки негде сидеть пожилым жителям района.'


def _fake_translation_provider():
    """Provider double: prefixes text with the target language."""
    provider = MagicMock()
    provider.translate.side_effect = (
        lambda text, source_lang, target_lang, html=False: f'[{target_lang}] {text}')
    return provider


class CivicIdeaTranslationTest(CivicPollTestCase):

    def _req(self, profile, method='post'):
        request = getattr(self.factory, method)('/fake/')
        request.auth_profile = profile
        return request

    def _ru_idea(self, title=RU_TITLE, body=RU_BODY):
        return create_idea(self._req(self.alice), IdeaCreateRequest(
            territory_id=self.muni_a.id, title=title, body=body))

    def test_create_detects_language(self):
        out = self._ru_idea()
        self.assertEqual(CivicIdea.objects.get(id=out['id']).language, 'ru')

    @patch('parahub.services.translation.TranslationService.get_provider')
    def test_list_translates_both_fields_and_caches(self, get_provider):
        provider = _fake_translation_provider()
        get_provider.return_value = provider
        out = self._ru_idea()

        listed = list_ideas(self._req(self.bob, 'get'), translate_to='pt')
        row = next(i for i in listed if i['id'] == out['id'])
        self.assertEqual(row['translated_title'], f'[pt] {RU_TITLE}')
        self.assertEqual(row['translated_body'], f'[pt] {RU_BODY}')
        self.assertTrue(row['is_translated'])
        self.assertEqual(provider.translate.call_count, 2)

        cache = CivicIdea.objects.get(id=out['id']).mt_cache
        self.assertEqual(cache['pt'], {'title': f'[pt] {RU_TITLE}',
                                       'body': f'[pt] {RU_BODY}'})

        # Warm cache: second request costs zero provider calls
        listed = list_ideas(self._req(self.bob, 'get'), translate_to='pt')
        row = next(i for i in listed if i['id'] == out['id'])
        self.assertEqual(row['translated_title'], f'[pt] {RU_TITLE}')
        self.assertEqual(provider.translate.call_count, 2)

    @patch('parahub.services.translation.TranslationService.get_provider')
    def test_same_language_and_unknown_target_skip(self, get_provider):
        provider = _fake_translation_provider()
        get_provider.return_value = provider
        self._ru_idea()

        for target in ('ru', 'xx', None):
            listed = list_ideas(self._req(self.bob, 'get'), translate_to=target)
            self.assertTrue(all(not i['is_translated']
                                and i['translated_title'] is None for i in listed))
        self.assertEqual(provider.translate.call_count, 0)

    @patch('parahub.services.translation.TranslationService.get_provider')
    def test_unknown_source_language_skips(self, get_provider):
        provider = _fake_translation_provider()
        get_provider.return_value = provider
        out = self._ru_idea()
        CivicIdea.objects.filter(id=out['id']).update(language='')

        listed = list_ideas(self._req(self.bob, 'get'), translate_to='pt')
        row = next(i for i in listed if i['id'] == out['id'])
        self.assertFalse(row['is_translated'])
        self.assertEqual(provider.translate.call_count, 0)

    @patch('parahub.services.translation.TranslationService.get_provider')
    def test_budget_cap_warms_progressively(self, get_provider):
        provider = _fake_translation_provider()
        get_provider.return_value = provider
        # 3 ideas x 2 fields = 6 needed calls > cap of 3
        for n in range(3):
            self._ru_idea(title=f'{RU_TITLE} {n}')

        list_ideas(self._req(self.bob, 'get'), translate_to='pt')
        self.assertEqual(provider.translate.call_count, MT_PER_REQUEST_CAP)

        # Next request completes the remaining fields from a warmer cache
        listed = list_ideas(self._req(self.bob, 'get'), translate_to='pt')
        self.assertEqual(provider.translate.call_count, 6)
        self.assertTrue(all(i['translated_title'] and i['translated_body']
                            for i in listed))

    @patch('parahub.services.translation.TranslationService.get_provider')
    def test_provider_down_degrades_to_original(self, get_provider):
        get_provider.return_value = None
        out = self._ru_idea()

        listed = list_ideas(self._req(self.bob, 'get'), translate_to='pt')
        row = next(i for i in listed if i['id'] == out['id'])
        self.assertIsNone(row['translated_title'])
        self.assertFalse(row['is_translated'])
        self.assertEqual(row['title'], RU_TITLE)
        self.assertEqual(CivicIdea.objects.get(id=out['id']).mt_cache, {})

    @patch('parahub.services.translation.TranslationService.get_provider')
    def test_support_response_carries_translation(self, get_provider):
        provider = _fake_translation_provider()
        get_provider.return_value = provider
        out = self._ru_idea()

        res = support_idea(self._req(self.bob), out['id'], translate_to='pt')
        self.assertEqual(res['translated_title'], f'[pt] {RU_TITLE}')
        self.assertTrue(res['is_translated'])
        self.assertTrue(res['supported_by_me'])
