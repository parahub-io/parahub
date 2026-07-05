"""
Move Para-ID id_photo from public media (media/id_photos/) to private storage
(media/private/id_photos/), so the raw file is no longer directly fetchable.

After this migration the file lives under nginx's `internal` location and is
served only via the gated /profiles/{id}/id-photo/ endpoint (owner or WoT-verified
viewers). The DB path is rewritten in lock-step with the on-disk move.
"""
import os
import shutil

from django.conf import settings
from django.db import migrations, models


OLD_PREFIX = "id_photos/"
NEW_PREFIX = "private/id_photos/"


def _move(apps, old_to_new):
    """old_to_new: callable(name) -> new_name. Move file on disk + update DB."""
    Profile = apps.get_model("identity", "Profile")
    media_root = settings.MEDIA_ROOT
    for profile in Profile.objects.exclude(id_photo="").exclude(id_photo__isnull=True):
        name = profile.id_photo.name or ""
        new_name = old_to_new(name)
        if not new_name or new_name == name:
            continue
        src = os.path.join(media_root, name)
        dst = os.path.join(media_root, new_name)
        if os.path.exists(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
        # Rewrite the DB pointer even if the source file was already missing,
        # so the field stays consistent with the new upload_to.
        profile.id_photo.name = new_name
        profile.save(update_fields=["id_photo"])


def forwards(apps, schema_editor):
    def to_private(name):
        if name.startswith(NEW_PREFIX):
            return name  # already migrated
        if name.startswith(OLD_PREFIX):
            return NEW_PREFIX + name[len(OLD_PREFIX):]
        return name
    _move(apps, to_private)


def backwards(apps, schema_editor):
    def to_public(name):
        if name.startswith(NEW_PREFIX):
            return OLD_PREFIX + name[len(NEW_PREFIX):]
        return name
    _move(apps, to_public)


class Migration(migrations.Migration):

    dependencies = [
        ("identity", "0003_contract_kind"),
    ]

    operations = [
        migrations.AlterField(
            model_name="profile",
            name="id_photo",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="private/id_photos/%Y/%m/",
                help_text=(
                    "Formal ID photo for Para-ID badge (passport-style, 3:4 ratio). "
                    "Stored under media/private/ (nginx internal) — served only via the "
                    "gated /profiles/{id}/id-photo/ endpoint to the owner or WoT-verified viewers."
                ),
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
