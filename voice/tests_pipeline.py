"""Guards for the two pure functions the pipeline's correctness hangs on.

Container sniffing and language normalisation are where a wrong answer is silent:
a mislabelled container makes the provider reject perfectly good audio, and an
unmapped language code sends a Russian note to be translated *into* Russian.
Both are covered here without touching a provider.
"""

from django.test import SimpleTestCase

from voice.services.pipeline import normalize_language, sniff_audio


class SniffAudioTests(SimpleTestCase):
    def test_webm_by_ebml_magic(self):
        self.assertEqual(sniff_audio(b'\x1a\x45\xdf\xa3' + b'\x00' * 8)[0], 'webm')

    def test_mp4_by_ftyp_box(self):
        # What iOS Safari records while calling the blob .webm.
        self.assertEqual(sniff_audio(b'\x00\x00\x00\x20ftypisom')[0], 'mp4')

    def test_ogg_and_wav(self):
        self.assertEqual(sniff_audio(b'OggS' + b'\x00' * 8)[0], 'ogg')
        self.assertEqual(sniff_audio(b'RIFF\x00\x00\x00\x00WAVE')[0], 'wav')

    def test_mp3_by_id3_and_by_frame_sync(self):
        self.assertEqual(sniff_audio(b'ID3\x03\x00\x00\x00\x00\x00\x00\x00\x00')[0], 'mp3')
        self.assertEqual(sniff_audio(b'\xff\xfb\x90\x64' + b'\x00' * 8)[0], 'mp3')

    def test_unknown_falls_back_to_webm(self):
        self.assertEqual(sniff_audio(b'nonsense')[0], 'webm')

    def test_short_input_does_not_raise(self):
        # A truncated first frame must not take the connection down.
        self.assertEqual(sniff_audio(b'\xff')[0], 'webm')
        self.assertEqual(sniff_audio(b'')[0], 'webm')

    def test_content_type_matches_extension(self):
        self.assertEqual(sniff_audio(b'OggS' + b'\x00' * 8), ('ogg', 'audio/ogg'))


class NormalizeLanguageTests(SimpleTestCase):
    def test_three_letter_codes_from_the_provider(self):
        # Scribe answers ISO-639-3; profiles speak two letters.
        self.assertEqual(normalize_language('por'), 'pt')
        self.assertEqual(normalize_language('rus'), 'ru')
        self.assertEqual(normalize_language('eng'), 'en')
        self.assertEqual(normalize_language('deu'), 'de')
        self.assertEqual(normalize_language('ger'), 'de')

    def test_regional_tags_collapse_to_the_language(self):
        self.assertEqual(normalize_language('pt-BR'), 'pt')
        self.assertEqual(normalize_language('pt_PT'), 'pt')
        self.assertEqual(normalize_language('EN-us'), 'en')

    def test_empty_stays_empty(self):
        self.assertEqual(normalize_language(''), '')
        self.assertEqual(normalize_language(None), '')
