"""Turn the public relay back on only where redistribution is actually permitted.

Two cases qualify. A feed whose licence allows redistribution — of the 17 sources
that is PID Prague alone (CC-BY-4.0). And a managed source, where the operator
publishes their own data through us and the relay is the feature they came for.

Everything else stays off: 14 publishers state no terms at all, and the two that
do (King County's revocable Transit Data Terms of Use, MBTA's MassDOT agreement)
have not been read as granting redistribution. See PK/gtfs-feed-quirks.md § Licences.
"""

from django.db import migrations


RELAYABLE_LICENSES = ['CC-BY-4.0']


def open_permitted_relays(apps, schema_editor):
    TransitDataSource = apps.get_model('geo', 'TransitDataSource')
    Agency = apps.get_model('geo', 'Agency')

    TransitDataSource.objects.filter(license__in=RELAYABLE_LICENSES).update(relay_allowed=True)

    managed_source_ids = Agency.objects.filter(
        is_managed=True, data_source__isnull=False,
    ).values_list('data_source_id', flat=True)
    TransitDataSource.objects.filter(id__in=list(managed_source_ids)).update(relay_allowed=True)


def close_all_relays(apps, schema_editor):
    TransitDataSource = apps.get_model('geo', 'TransitDataSource')
    TransitDataSource.objects.update(relay_allowed=False)


class Migration(migrations.Migration):

    dependencies = [
        ('geo', '0043_transit_source_relay_allowed'),
    ]

    operations = [
        migrations.RunPython(open_permitted_relays, close_all_relays),
    ]
