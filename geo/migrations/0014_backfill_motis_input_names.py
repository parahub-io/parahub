from django.db import migrations


MAPPING = {
    'carris-metropolitana': 'carris_metropolitana.zip',
    'carris-lisboa': 'carris_lisboa.zip',
    'stcp-porto': 'stcp_porto.zip',
    'hsl-helsinki': 'hsl_helsinki.zip',
    'pid-prague': 'pid_prague.zip',
    'mbta-boston': 'mbta_boston.zip',
    'kcm-seattle': 'king_county_seattle.zip',
}


def backfill(apps, schema_editor):
    TransitDataSource = apps.get_model('geo', 'TransitDataSource')
    for slug, fname in MAPPING.items():
        TransitDataSource.objects.filter(slug=slug).update(motis_input_name=fname)


def reverse(apps, schema_editor):
    TransitDataSource = apps.get_model('geo', 'TransitDataSource')
    TransitDataSource.objects.filter(slug__in=MAPPING).update(motis_input_name='')


class Migration(migrations.Migration):
    dependencies = [
        ('geo', '0013_transitdatasource_motis_input_name'),
    ]
    operations = [
        migrations.RunPython(backfill, reverse),
    ]
