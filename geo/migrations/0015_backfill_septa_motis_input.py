from django.db import migrations


SLUG = 'septa-philadelphia'
FILENAME = 'septa_philadelphia_flat.zip'


def backfill(apps, schema_editor):
    TransitDataSource = apps.get_model('geo', 'TransitDataSource')
    TransitDataSource.objects.filter(slug=SLUG).update(motis_input_name=FILENAME)


def reverse(apps, schema_editor):
    TransitDataSource = apps.get_model('geo', 'TransitDataSource')
    TransitDataSource.objects.filter(slug=SLUG).update(motis_input_name='')


class Migration(migrations.Migration):
    dependencies = [
        ('geo', '0014_backfill_motis_input_names'),
    ]
    operations = [
        migrations.RunPython(backfill, reverse),
    ]
