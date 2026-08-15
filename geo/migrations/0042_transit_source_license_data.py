"""Record the licence of every upstream feed we mirror — where the publisher states one.

Only verbatim-verified terms are filled in here. An empty `license` is a fact, not a
gap to be guessed at: it means the publisher states no terms, which leaves our public
relay of that feed unsettled. See PK/gtfs-feed-quirks.md § Licences.
"""

from django.db import migrations


# slug -> (license, license_url, attribution)
VERIFIED = {
    'pid-prague': (
        'CC-BY-4.0',
        'https://pid.cz/opendata/',
        'Pražská integrovaná doprava (PID)',
    ),
    'kcm-seattle': (
        'King County Transit Data Terms of Use',
        'https://kingcounty.gov/en/dept/metro/rider-tools/mobile-and-web-apps',
        'Transit scheduling, geographic, and real-time data provided by permission of King County',
    ),
    # The agreement is a PDF behind the developer page; its required credit wording
    # has not been read, so attribution stays empty rather than invented.
    'mbta-boston': (
        'MassDOT Developers License Agreement',
        'https://www.mbta.com/developers/gtfs',
        '',
    ),
}


def set_licenses(apps, schema_editor):
    TransitDataSource = apps.get_model('geo', 'TransitDataSource')
    for slug, (license_id, url, attribution) in VERIFIED.items():
        TransitDataSource.objects.filter(slug=slug).update(
            license=license_id, license_url=url, attribution=attribution,
        )


def clear_licenses(apps, schema_editor):
    TransitDataSource = apps.get_model('geo', 'TransitDataSource')
    TransitDataSource.objects.filter(slug__in=VERIFIED).update(
        license='', license_url='', attribution='',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('geo', '0041_transit_source_license'),
    ]

    operations = [
        migrations.RunPython(set_licenses, clear_licenses),
    ]
