"""Tests for the WoT verification-photo re-confirmation round.

Invariants that must never break:
- A pending round can actually be satisfied (it used to be unwinnable: the
  verify endpoint refused every verification while pending, and a verification
  was the only thing that could feed the count)
- Three re-confirmations mean three distinct verifiers, not one signing thrice
- Revoking a re-confirmation puts the profile back into pending
- Deleting the photo record and uploading a new one does not wipe the round
- Verifications made before the face changed never count toward it
"""

from unittest.mock import patch

import numpy as np
from django.test import TestCase, RequestFactory
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone
from ninja.errors import HttpError

from core.models import Instance
from identity.models import Account, Profile, ProfileVerificationPhoto, Verification
from identity.services.face_dedup import (
    serialize_embedding, requires_reconfirmation, RECONFIRMATION_THRESHOLD,
)


def _embedding(offset=0.0):
    """A synthetic 128-d embedding, `offset` away from the origin one per axis."""
    return serialize_embedding(np.full(128, offset, dtype=np.float64))


# Distance between _embedding(0) and _embedding(x) is sqrt(128) * x
_NEAR = 0.001   # ~0.011 apart — same face
_FAR = 0.1      # ~1.13 apart — different face


class ReconfirmationTestBase(TestCase):
    def setUp(self):
        self.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test Instance', public_key='test-key',
        )
        self.target = self._profile('target')
        self.verifiers = [self._profile(f'verifier{i}') for i in range(4)]
        self.photo = ProfileVerificationPhoto.objects.create(
            profile=self.target,
            face_embedding=_embedding(),
            photo_hash='0' * 64,
            biometric_consent=True,
            biometric_consent_at=timezone.now(),
        )

    def _profile(self, name):
        account = Account.objects.create_user(
            username=name, email=f'{name}@test.parahub.io',
            password='testpass123', instance=self.instance,
        )
        return Profile.objects.create(
            account=account, instance=self.instance, local_name=name,
            display_name=name.title(), is_primary=True,
            profile_type=Profile.ProfileType.PERSONAL,
            pgp_public_key='-----BEGIN PGP PUBLIC KEY BLOCK-----',
            pgp_fingerprint=f'{name:*<40}'[:40].upper(),
        )

    def _verify(self, verifier, when=None):
        """Create or re-affirm a verification, the way the endpoint does."""
        verification, _ = Verification.objects.get_or_create(
            verifier=verifier, verified_profile=self.target,
            defaults={'verification_method': 'IN_PERSON', 'signature': 'sig'},
        )
        verification.is_active = True
        verification.verified_at = when or timezone.now()
        verification.save()
        return verification

    def _change_face(self):
        self.photo.mark_face_changed()
        self.photo.save()


class ReconfirmationCountingTest(ReconfirmationTestBase):
    """The count is derived from verifications, not incremented per submission."""

    def test_pending_clears_after_three_distinct_reconfirmations(self):
        for v in self.verifiers[:3]:
            self._verify(v)
        self._change_face()
        self.assertTrue(self.photo.reconfirmation_needed)
        self.assertEqual(self.photo.reconfirmation_count, 0)

        for expected, verifier in enumerate(self.verifiers[:3], start=1):
            self._verify(verifier)
            self.photo.refresh_from_db()
            self.assertEqual(self.photo.reconfirmation_count, expected)

        self.assertFalse(self.photo.reconfirmation_needed)

    def test_one_verifier_cannot_confirm_three_times(self):
        for v in self.verifiers[:3]:
            self._verify(v)
        self._change_face()

        for _ in range(3):
            self._verify(self.verifiers[0])

        self.photo.refresh_from_db()
        self.assertEqual(self.photo.reconfirmation_count, 1)
        self.assertTrue(self.photo.reconfirmation_needed)

    def test_older_verifications_do_not_count(self):
        for v in self.verifiers[:3]:
            self._verify(v)
        self._change_face()

        self.photo.refresh_reconfirmation()
        self.assertEqual(self.photo.reconfirmation_count, 0)
        self.assertTrue(self.photo.reconfirmation_needed)

    def test_new_verifier_counts_toward_the_round(self):
        for v in self.verifiers[:3]:
            self._verify(v)
        self._change_face()

        self._verify(self.verifiers[3])  # never verified this profile before

        self.photo.refresh_from_db()
        self.assertEqual(self.photo.reconfirmation_count, 1)

    def test_revoked_reconfirmation_reopens_pending(self):
        for v in self.verifiers[:3]:
            self._verify(v)
        self._change_face()
        for v in self.verifiers[:3]:
            self._verify(v)
        self.photo.refresh_from_db()
        self.assertFalse(self.photo.reconfirmation_needed)

        revoked = Verification.objects.get(verifier=self.verifiers[0], verified_profile=self.target)
        revoked.is_active = False
        revoked.save()

        self.photo.refresh_from_db()
        self.assertTrue(self.photo.reconfirmation_needed)
        self.assertEqual(self.photo.reconfirmation_count, 2)

    def test_deleted_verification_reopens_pending(self):
        for v in self.verifiers[:3]:
            self._verify(v)
        self._change_face()
        for v in self.verifiers[:3]:
            self._verify(v)
        self.photo.refresh_from_db()
        self.assertFalse(self.photo.reconfirmation_needed)

        Verification.objects.get(verifier=self.verifiers[2], verified_profile=self.target).delete()

        self.photo.refresh_from_db()
        self.assertTrue(self.photo.reconfirmation_needed)
        self.assertEqual(self.photo.reconfirmation_count, 2)

    def test_unverified_profile_is_never_pending(self):
        """Nothing to re-confirm when nobody verified the profile yet."""
        self.assertFalse(self.photo.reconfirmation_needed)
        self.photo.refresh_reconfirmation()
        self.assertFalse(self.photo.reconfirmation_needed)


class ReconfirmationTriggerTest(ReconfirmationTestBase):
    """Which uploads open a round (requires_reconfirmation)."""

    def test_significant_change_on_verified_profile_opens_round(self):
        self._verify(self.verifiers[0])
        self.assertTrue(requires_reconfirmation(self.target.id, _embedding(), _embedding(_FAR)))

    def test_signed_upload_never_opens_a_round(self):
        """A signature proves the key holder swapped the photo — the whole question."""
        self._verify(self.verifiers[0])
        self.assertFalse(requires_reconfirmation(
            self.target.id, _embedding(), _embedding(_FAR), owner_signed=True
        ))
        self.assertFalse(requires_reconfirmation(
            self.target.id, None, _embedding(_FAR), owner_signed=True
        ))

    def test_same_face_does_not_open_round(self):
        self._verify(self.verifiers[0])
        self.assertFalse(requires_reconfirmation(self.target.id, _embedding(), _embedding(_NEAR)))

    def test_no_verifications_never_opens_round(self):
        self.assertFalse(requires_reconfirmation(self.target.id, _embedding(), _embedding(_FAR)))

    def test_missing_old_embedding_opens_round(self):
        """DELETE + re-upload leaves nothing to compare against — not a clean slate."""
        self._verify(self.verifiers[0])
        self.assertTrue(requires_reconfirmation(self.target.id, None, _embedding()))

    def test_thresholds_match_the_synthetic_fixtures(self):
        """Guard the fixtures: _NEAR/_FAR must sit either side of the threshold."""
        span = np.sqrt(128)
        self.assertLess(span * _NEAR, RECONFIRMATION_THRESHOLD)
        self.assertGreater(span * _FAR, RECONFIRMATION_THRESHOLD)


class PhotoUploadSignatureTest(ReconfirmationTestBase):
    """The signed-upload check: `_verify_photo_owner_signature`."""

    def setUp(self):
        super().setUp()
        from parahub.endpoints.profiles.photos import _verify_photo_owner_signature
        self.check = _verify_photo_owner_signature
        self.sha256 = 'a' * 64

    def _statement(self, sha256=None, when=None, **overrides):
        import json
        payload = {
            "action": "verification_photo_upload",
            "profile_id": self.target.id,
            "profile_hna": self.target.hna,
            "sha256": sha256 or self.sha256,
            "timestamp": (when or timezone.now()).isoformat(),
        }
        payload.update(overrides)
        return json.dumps(payload, indent=2)

    def test_unsigned_upload_is_not_an_error(self):
        self.assertFalse(self.check(self.target, self.sha256, '', ''))

    def test_valid_signature_accepted(self):
        with patch('parahub.crypto.pgp.pgp_crypto.verify_signature', return_value=True):
            self.assertTrue(self.check(self.target, self.sha256, self._statement(), 'sig'))

    def test_statement_for_other_bytes_rejected(self):
        """The signature must cover the file actually being uploaded."""
        with patch('parahub.crypto.pgp.pgp_crypto.verify_signature', return_value=True):
            with self.assertRaises(HttpError):
                self.check(self.target, 'b' * 64, self._statement(), 'sig')

    def test_statement_for_other_profile_rejected(self):
        with patch('parahub.crypto.pgp.pgp_crypto.verify_signature', return_value=True):
            with self.assertRaises(HttpError):
                self.check(self.target, self.sha256, self._statement(profile_id=self.verifiers[0].id), 'sig')

    def test_stale_statement_rejected(self):
        from datetime import timedelta
        stale = timezone.now() - timedelta(minutes=10)
        with patch('parahub.crypto.pgp.pgp_crypto.verify_signature', return_value=True):
            with self.assertRaises(HttpError):
                self.check(self.target, self.sha256, self._statement(when=stale), 'sig')

    def test_bad_signature_rejected_not_downgraded(self):
        with patch('parahub.crypto.pgp.pgp_crypto.verify_signature', return_value=False):
            with self.assertRaises(HttpError):
                self.check(self.target, self.sha256, self._statement(), 'sig')

    def test_signature_without_a_key_on_the_profile_rejected(self):
        self.target.pgp_public_key = ''
        self.target.save(update_fields=['pgp_public_key'])
        with self.assertRaises(HttpError):
            self.check(self.target, self.sha256, self._statement(), 'sig')


class SignedPhotoUploadEndpointTest(ReconfirmationTestBase):
    """The upload endpoint end to end, with a real key and a real signature.

    Only the face embedding is stubbed — dlib finds no face in a generated
    fixture, and what is under test is the signature path, not its own extractor.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from parahub.crypto.tests import generate_test_keypair
        cls.gpg, cls.gpg_home, cls.keyid, cls.pub, cls.priv, cls.passphrase = generate_test_keypair()

    @classmethod
    def tearDownClass(cls):
        from parahub.crypto.tests import _cleanup_gpg_home
        _cleanup_gpg_home(cls.gpg_home)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        import tempfile
        self.factory = RequestFactory()
        self.media_root = tempfile.mkdtemp(prefix='parahub_test_media_')
        self.target.pgp_public_key = self.pub
        self.target.save(update_fields=['pgp_public_key'])
        self._verify(self.verifiers[0])  # something to re-confirm

    def tearDown(self):
        import shutil
        shutil.rmtree(self.media_root, ignore_errors=True)
        super().tearDown()

    def _jpeg_bytes(self):
        from io import BytesIO
        from PIL import Image
        buf = BytesIO()
        Image.new('RGB', (400, 500), (128, 128, 128)).save(buf, format='JPEG')
        return buf.getvalue()

    def _upload(self, image_bytes, sign=True, tamper_bytes=False, face_offset=_FAR):
        import json
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings
        from parahub.crypto.tests import sign_message
        from parahub.endpoints.profiles.photos import upload_verification_photo
        from identity.services.face_dedup import compute_photo_hash

        statement, signature = '', ''
        if sign:
            signed_bytes = b'other' if tamper_bytes else image_bytes
            statement = json.dumps({
                "action": "verification_photo_upload",
                "profile_id": self.target.id,
                "profile_hna": self.target.hna,
                "sha256": compute_photo_hash(signed_bytes),
                "timestamp": timezone.now().isoformat(),
            }, indent=2)
            signature = sign_message(self.gpg, self.keyid, self.passphrase, statement)

        request = self.factory.post('/fake/')
        request.user = self.target.account
        request.auth = self.target
        request.auth_profile = self.target

        upload = SimpleUploadedFile('face.jpg', image_bytes, content_type='image/jpeg')

        with override_settings(MEDIA_ROOT=self.media_root), \
             patch('identity.services.face_dedup.extract_embedding',
                   return_value=(np.full(128, face_offset, dtype=np.float64), [])):
            return upload_verification_photo(
                request, upload, biometric_consent=True,
                photo_statement=statement, photo_signature=signature,
            )

    def test_signed_replacement_opens_no_round(self):
        response = self._upload(self._jpeg_bytes(), sign=True)

        self.assertTrue(response['success'])
        self.assertTrue(response['owner_signed'])
        self.assertFalse(response['reconfirmation_needed'])
        self.photo.refresh_from_db()
        self.assertFalse(self.photo.reconfirmation_needed)
        self.assertIsNone(self.photo.reconfirmation_started_at)

    def test_unsigned_replacement_opens_a_round(self):
        response = self._upload(self._jpeg_bytes(), sign=False)

        self.assertTrue(response['success'])
        self.assertFalse(response['owner_signed'])
        self.assertTrue(response['reconfirmation_needed'])
        self.photo.refresh_from_db()
        self.assertTrue(self.photo.reconfirmation_needed)
        self.assertIsNotNone(self.photo.reconfirmation_started_at)

    def test_signed_upload_closes_an_open_round(self):
        """The signature answers what the round was asking — it need not stay open."""
        self._change_face()
        self.assertTrue(self.photo.reconfirmation_needed)

        response = self._upload(self._jpeg_bytes(), sign=True)

        self.assertTrue(response['owner_signed'])
        self.assertFalse(response['reconfirmation_needed'])
        self.photo.refresh_from_db()
        self.assertFalse(self.photo.reconfirmation_needed)
        self.assertIsNone(self.photo.reconfirmation_started_at)

    def test_unsigned_upload_leaves_an_open_round_open(self):
        """Re-uploading the same face unsigned answers nothing, so it closes nothing."""
        self._change_face()

        response = self._upload(self._jpeg_bytes(), sign=False, face_offset=0.0)

        self.assertTrue(response['reconfirmation_needed'])
        self.photo.refresh_from_db()
        self.assertTrue(self.photo.reconfirmation_needed)

    def test_signature_over_other_bytes_is_refused(self):
        """The signature has to cover the file that actually arrived."""
        status, body = self._upload(self._jpeg_bytes(), sign=True, tamper_bytes=True)

        self.assertEqual(status, 400)
        self.assertIn('does not match', body['error'])
        self.photo.refresh_from_db()
        self.assertFalse(self.photo.reconfirmation_needed)


class ReconfirmationEndpointTest(ReconfirmationTestBase):
    """The verify endpoint accepts the verifications that satisfy a round."""

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()
        for v in self.verifiers[:3]:
            self._verify(v)
        self.target.update_wot_status()
        # Verifiers need to be verified themselves to be allowed to verify others
        for verifier in self.verifiers:
            for other in self.verifiers:
                if other != verifier:
                    Verification.objects.create(
                        verifier=other, verified_profile=verifier,
                        verification_method='IN_PERSON', signature='sig', is_active=True,
                    )
            ProfileVerificationPhoto.objects.create(
                profile=verifier, face_embedding=_embedding(0.5 + len(verifier.local_name) / 100),
                photo_hash='1' * 64, biometric_consent=True, biometric_consent_at=timezone.now(),
            )
        self._change_face()

    def _call_verify(self, verifier):
        from parahub.endpoints.wot import create_verification, CreateVerificationRequest
        import json

        timestamp = timezone.now().isoformat()
        statement = json.dumps({
            "action": "wot_verify",
            "verifier_hna": verifier.hna,
            "verifier_id": verifier.id,
            "verified_hna": self.target.hna,
            "verified_id": self.target.id,
            "method": "IN_PERSON",
            "timestamp": timestamp,
        }, indent=2)

        request = self.factory.post('/fake/')
        request.user = verifier.account
        request.auth = verifier
        request.auth_profile = verifier
        request.session = SessionStore()
        request.session.create()

        data = CreateVerificationRequest(
            verified_user_id=self.target.id,
            verification_method='IN_PERSON',
            timestamp=timestamp,
            statement=statement,
            signature='-----BEGIN PGP SIGNATURE-----',
        )
        with patch('parahub.crypto.pgp.pgp_crypto.verify_signature', return_value=True), \
             patch('identity.services.face_dedup.check_duplicate', return_value=None), \
             patch('notifications.services.notify_verification_received'):
            return create_verification(request, data)

    def test_existing_verifier_may_sign_again_while_pending(self):
        response = self._call_verify(self.verifiers[0])

        self.assertTrue(response['success'])
        self.photo.refresh_from_db()
        self.assertEqual(self.photo.reconfirmation_count, 1)
        # Still one verification from this verifier, re-signed in place
        self.assertEqual(
            Verification.objects.filter(verifier=self.verifiers[0], verified_profile=self.target).count(), 1
        )

    def test_round_closes_after_three_verifiers_sign_again(self):
        for verifier in self.verifiers[:3]:
            self._call_verify(verifier)

        self.photo.refresh_from_db()
        self.assertFalse(self.photo.reconfirmation_needed)
        self.assertEqual(self.photo.reconfirmation_count, 3)

    def test_second_signature_from_the_same_verifier_is_refused(self):
        self._call_verify(self.verifiers[0])

        with self.assertRaises(HttpError) as ctx:
            self._call_verify(self.verifiers[0])
        self.assertEqual(getattr(ctx.exception, 'code', None), 'already_verified')

    def test_verifying_without_a_pending_round_is_refused_as_before(self):
        self.photo.reconfirmation_started_at = None
        self.photo.reconfirmation_needed = False
        self.photo.save()

        with self.assertRaises(HttpError) as ctx:
            self._call_verify(self.verifiers[0])
        self.assertEqual(getattr(ctx.exception, 'code', None), 'already_verified')
