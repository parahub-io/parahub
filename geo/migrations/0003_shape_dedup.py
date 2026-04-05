# Schema: create Shape model + Trip.shape_ref FK (keep old Trip.shape for rollback safety)

import core.models
import django.contrib.gis.db.models.fields
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('geo', '0002_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Shape',
            fields=[
                ('id', models.CharField(default=core.models.generate_ulid, editable=False, help_text='ULID (Universally Unique Lexicographically Sortable Identifier)', max_length=26, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('attributes', models.JSONField(blank=True, default=dict, help_text='Key-value store for intrinsic properties of this object')),
                ('relations', models.JSONField(blank=True, default=list, help_text='List of relationships to other objects. Format: [{type: str, target_id: str, target_type: str}]')),
                ('source_id', models.CharField(blank=True, db_index=True, help_text='GTFS shape_id', max_length=100)),
                ('geometry', django.contrib.gis.db.models.fields.LineStringField(geography=True, srid=4326)),
                ('length_m', models.FloatField(default=0, help_text='Precomputed ST_Length(geography)')),
                ('agency', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shapes', to='geo.agency')),
            ],
        ),
        migrations.AddField(
            model_name='trip',
            name='shape_ref',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='trips', to='geo.shape'),
        ),
        migrations.AddConstraint(
            model_name='shape',
            constraint=models.UniqueConstraint(condition=models.Q(('source_id', ''), _negated=True), fields=('agency', 'source_id'), name='unique_agency_shape'),
        ),
    ]
