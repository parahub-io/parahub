# Data migration: deduplicate Trip.shape geometries into Shape table, link trips via shape_ref

from django.db import migrations


def deduplicate_shapes(apps, schema_editor):
    """
    Batch-deduplicate trip shapes into the Shape table using geometry hash.
    ~17K unique shapes from ~1.28M trips.
    """
    from django.db import connection

    with connection.cursor() as cursor:
        # Step 1: Create Shape rows from unique (agency, geometry) combinations.
        # Uses MD5 of WKB for dedup. generate_ulid() is a Python function,
        # so we use a subquery with DISTINCT ON + generate random ULIDs via pgcrypto.
        # Actually, we need proper ULIDs — use encode(gen_random_bytes) as placeholder,
        # then let Django assign proper ULIDs.

        # First, count what we're dealing with
        cursor.execute("""
            SELECT COUNT(DISTINCT (r.agency_id, MD5(ST_AsBinary(t.shape))))
            FROM geo_trip t
            JOIN geo_route r ON r.id = t.route_id
            WHERE t.shape IS NOT NULL
        """)
        unique_count = cursor.fetchone()[0]

        if unique_count == 0:
            return

        # Step 2: Create temp table mapping geometry hash → agency for dedup
        cursor.execute("""
            CREATE TEMP TABLE _shape_dedup AS
            SELECT DISTINCT ON (r.agency_id, MD5(ST_AsBinary(t.shape)))
                r.agency_id,
                t.id as sample_trip_id,
                MD5(ST_AsBinary(t.shape)) as geom_hash,
                t.shape as geometry,
                ST_Length(t.shape::geography) as length_m
            FROM geo_trip t
            JOIN geo_route r ON r.id = t.route_id
            WHERE t.shape IS NOT NULL
        """)

        # Step 3: Insert into geo_shape from dedup table
        # Use core_models.generate_ulid() equivalent — we need ULIDs.
        # Import and generate in Python, batch insert.
        cursor.execute("SELECT agency_id, sample_trip_id, geom_hash, geometry, length_m FROM _shape_dedup")
        rows = cursor.fetchall()

    # Generate ULIDs in Python and batch insert
    from ulid import ULID
    from django.db import connection

    # Build (ulid, agency_id, geom_hash) mapping for the update step
    hash_to_shape_id = {}  # (agency_id, geom_hash) → shape_id

    BATCH = 2000
    with connection.cursor() as cursor:
        for i in range(0, len(rows), BATCH):
            batch = rows[i:i + BATCH]
            values = []
            params = []
            for agency_id, sample_trip_id, geom_hash, geometry, length_m in batch:
                shape_id = str(ULID())
                hash_to_shape_id[(agency_id, geom_hash)] = shape_id
                values.append("(%s, %s, '', %s, %s, NOW(), NOW(), '{}'::jsonb, '[]'::jsonb)")
                params.extend([shape_id, agency_id, geometry, length_m or 0])

            if values:
                sql = (
                    "INSERT INTO geo_shape (id, agency_id, source_id, geometry, length_m, "
                    "created_at, updated_at, attributes, relations) VALUES "
                    + ", ".join(values)
                )
                cursor.execute(sql, params)

    # Step 4: Link trips to shapes via hash join.
    # Add hash column to trip temporarily for efficient join.
    with connection.cursor() as cursor:
        cursor.execute("""
            CREATE TEMP TABLE _trip_hashes AS
            SELECT t.id as trip_id, r.agency_id,
                   MD5(ST_AsBinary(t.shape)) as geom_hash
            FROM geo_trip t
            JOIN geo_route r ON r.id = t.route_id
            WHERE t.shape IS NOT NULL
        """)
        cursor.execute("CREATE INDEX ON _trip_hashes (agency_id, geom_hash)")

        # Build a temp table of hash→shape_id for SQL join
        if hash_to_shape_id:
            values = []
            params = []
            for (agency_id, geom_hash), shape_id in hash_to_shape_id.items():
                values.append("(%s, %s, %s)")
                params.extend([agency_id, geom_hash, shape_id])

            cursor.execute(
                "CREATE TEMP TABLE _hash_shape_map (agency_id VARCHAR(26), geom_hash TEXT, shape_id VARCHAR(26))"
            )

            # Batch insert the mapping
            for j in range(0, len(values), BATCH):
                batch_vals = values[j:j + BATCH]
                batch_params = params[j * 3:(j + BATCH) * 3]
                cursor.execute(
                    "INSERT INTO _hash_shape_map VALUES " + ", ".join(batch_vals),
                    batch_params,
                )

            cursor.execute("CREATE INDEX ON _hash_shape_map (agency_id, geom_hash)")

            # Single UPDATE with JOIN — efficient for 1.28M rows
            cursor.execute("""
                UPDATE geo_trip t
                SET shape_ref_id = m.shape_id
                FROM _trip_hashes h
                JOIN _hash_shape_map m ON m.agency_id = h.agency_id AND m.geom_hash = h.geom_hash
                WHERE h.trip_id = t.id
            """)

        # Cleanup temp tables
        cursor.execute("DROP TABLE IF EXISTS _shape_dedup, _trip_hashes, _hash_shape_map")


def reverse_shapes(apps, schema_editor):
    """Reverse: just truncate geo_shape and null out shape_ref."""
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("UPDATE geo_trip SET shape_ref_id = NULL WHERE shape_ref_id IS NOT NULL")
        cursor.execute("DELETE FROM geo_shape")


class Migration(migrations.Migration):

    dependencies = [
        ('geo', '0003_shape_dedup'),
    ]

    operations = [
        migrations.RunPython(deduplicate_shapes, reverse_shapes),
    ]
