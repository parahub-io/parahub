"""Add database-level DEFAULTs to the similarity columns.

0019 added rel_scale/rel_rotation_deg as NOT NULL with Django *app-level*
defaults but no DB default. A writer that doesn't include the columns in its
INSERT (e.g. a long-running process that imported the model before 0019, or any
raw insert) then hits a NOT NULL violation — which failed an in-flight mission.
Setting DB defaults makes such inserts safe regardless of the writer's schema.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('geo', '0019_openskymission_corr_dx_m_openskymission_corr_dy_m_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE geo_openskyposeedge ALTER COLUMN rel_scale SET DEFAULT 1.0;"
                "ALTER TABLE geo_openskyposeedge ALTER COLUMN rel_rotation_deg SET DEFAULT 0.0;"
            ),
            reverse_sql=(
                "ALTER TABLE geo_openskyposeedge ALTER COLUMN rel_scale DROP DEFAULT;"
                "ALTER TABLE geo_openskyposeedge ALTER COLUMN rel_rotation_deg DROP DEFAULT;"
            ),
        ),
    ]
