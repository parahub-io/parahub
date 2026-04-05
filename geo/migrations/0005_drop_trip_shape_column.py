# Drop the legacy Trip.shape column after data migrated to Shape table

import django.contrib.gis.db.models.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('geo', '0004_populate_shapes'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='trip',
            name='shape',
        ),
    ]
