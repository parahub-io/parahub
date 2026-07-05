"""
Tests for the polymorphic-attachment pre_delete fan-out (core/signals.py).

Invariants:
- Deleting a host removes its object_id/target_id attachments (rows + storage)
- Active investment shares / distribution history BLOCK host deletion
- Inactive shares follow their host
"""

from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.db.models import ProtectedError
from django.test import TestCase

from core.models import (
    Instance, Like, ObjectComment, ObjectDistribution, ObjectFile,
    ObjectPhoto, ObjectShare,
)
from identity.models import Account, Profile
from market.models import Item

# 1x1 px GIF — smallest well-formed image Django's ImageField accepts
TINY_GIF = (
    b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
    b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00'
    b'\x02\x02D\x01\x00;'
)


class AttachmentFanoutTests(TestCase):
    def setUp(self):
        self.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test', public_key='k')
        self.account = Account.objects.create_user(
            username='alice', email='alice@test.parahub.io',
            password='x', instance=self.instance)
        self.profile = Profile.objects.create(
            account=self.account, instance=self.instance,
            local_name='alice', display_name='Alice', is_primary=True)
        self.item = Item.objects.create(
            owner=self.profile, title='Bike', type='CREDIT')

    def _attach_everything(self, oid):
        photo = ObjectPhoto.objects.create(
            object_id=oid,
            image=SimpleUploadedFile('p.gif', TINY_GIF, 'image/gif'),
            uploaded_by=self.profile)
        file = ObjectFile.objects.create(
            object_id=oid,
            file=SimpleUploadedFile('doc.txt', b'hello', 'text/plain'),
            filename='doc.txt', mime_type='text/plain', size_bytes=5,
            uploaded_by=self.profile)
        ObjectComment.objects.create(object_id=oid, author=self.profile, text='hi')
        Like.objects.create(profile=self.profile, target_id=oid, target_type='item')
        return photo, file

    def test_host_delete_removes_attachments_and_storage(self):
        photo, file = self._attach_everything(self.item.id)
        photo_storage, photo_name = photo.image.storage, photo.image.name
        file_storage, file_name = file.file.storage, file.file.name
        self.assertTrue(photo_storage.exists(photo_name))

        self.item.delete()

        oid = self.item.id
        self.assertFalse(ObjectPhoto.objects.filter(object_id=oid).exists())
        self.assertFalse(ObjectFile.objects.filter(object_id=oid).exists())
        self.assertFalse(ObjectComment.objects.filter(object_id=oid).exists())
        self.assertFalse(Like.objects.filter(target_id=oid).exists())
        self.assertFalse(photo_storage.exists(photo_name))
        self.assertFalse(file_storage.exists(file_name))

    def test_queryset_delete_also_fans_out(self):
        """QuerySet.delete() must fire the same fan-out (no fast-delete path)."""
        self._attach_everything(self.item.id)
        Item.objects.filter(id=self.item.id).delete()
        self.assertFalse(ObjectComment.objects.filter(object_id=self.item.id).exists())
        self.assertFalse(Like.objects.filter(target_id=self.item.id).exists())

    def test_active_share_blocks_host_delete(self):
        ObjectShare.objects.create(
            object_id=self.item.id, profile=self.profile,
            share_percent=Decimal('10'), is_active=True)
        # atomic(): keep the aborted delete from poisoning the test transaction
        with self.assertRaises(ProtectedError), transaction.atomic():
            self.item.delete()
        self.assertTrue(Item.objects.filter(id=self.item.id).exists())

    def test_distribution_history_blocks_host_delete(self):
        ObjectDistribution.objects.create(
            object_id=self.item.id, period_label='2026-06',
            total_amount=Decimal('100'), created_by=self.profile)
        with self.assertRaises(ProtectedError), transaction.atomic():
            self.item.delete()

    def test_inactive_share_follows_host(self):
        ObjectShare.objects.create(
            object_id=self.item.id, profile=self.profile,
            share_percent=Decimal('10'), is_active=False)
        self.item.delete()
        self.assertFalse(ObjectShare.objects.filter(object_id=self.item.id).exists())
