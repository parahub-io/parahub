"""Create the Django groups behind the platform capabilities.

`parahub.capabilities.PLATFORM_CAPABILITIES` maps each capability to one group
name and reads membership off the Account. The rows are created here rather than
on first grant so the set is visible (and grantable) in Django admin from the
start, and so a fresh node has the same four names as this one.
"""
from django.db import migrations

GROUPS = ['urban_validators', 'moderators', 'infra_operators', 'federation_admins']


def create_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    for name in GROUPS:
        Group.objects.get_or_create(name=name)


def noop(apps, schema_editor):
    """Never delete a group on reverse — it may hold appointments by then."""


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0013_profileverificationphoto_reconfirmation_started_at_and_more'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(create_groups, noop),
    ]
