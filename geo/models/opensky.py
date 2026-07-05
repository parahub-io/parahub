from django.contrib.gis.db import models
from core.models import ULIDModel
from identity.models import Profile


class OpenSkyMission(ULIDModel):
    """
    Aerial imagery mission for OpenSky layer.

    Workflow (single file):
    1. User uploads ZIP with drone photos → status=QUEUED
    2. systemd timer runs process_opensky_queue → status=PROCESSING
    3. ODM + gdal2tiles → status=PUBLISHED or FAILED

    Workflow (multi-file for better stitching):
    1. User uploads first ZIP → status=UPLOADING
    2. User uploads more ZIPs (appended to same mission)
    3. User clicks "Finalize" → status=QUEUED
    4. Processing continues as above

    Legacy statuses (AVAILABLE, ASSIGNED) are for future bounty system.
    """
    class Status(models.TextChoices):
        AVAILABLE = 'AVAILABLE', 'Available (Bounty)'
        ASSIGNED = 'ASSIGNED', 'Assigned to Pilot'
        UPLOADING = 'UPLOADING', 'Uploading (multi-file)'
        QUEUED = 'QUEUED', 'Queued for Processing'
        PROCESSING = 'PROCESSING', 'Data Processing'
        PUBLISHED = 'PUBLISHED', 'Published'
        FAILED = 'FAILED', 'Failed'

    class MeshStatus(models.TextChoices):
        NONE = 'NONE', 'No mesh'
        MESH_QUEUED = 'MESH_QUEUED', 'Mesh queued'
        MESH_PROCESSING = 'MESH_PROCESSING', 'Mesh processing'
        MESH_READY = 'MESH_READY', 'Mesh ready'
        MESH_FAILED = 'MESH_FAILED', 'Mesh failed'

    # Area covered by this mission (calculated from tiles after processing)
    area = models.PolygonField(srid=4326, geography=True, null=True, blank=True)

    status = models.CharField(max_length=15, choices=Status.choices, default=Status.QUEUED, db_index=True)
    pilot = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL, related_name="opensky_missions")

    # Split-merge consolidation (see PK/opensky-system.md § Consolidation).
    # A consolidation is itself an OpenSkyMission row (is_consolidation=True) whose
    # tiles are the joint ODM split-merge of its member missions' photos — one
    # seamless ortho that overrides the members in latest/. Members keep their own
    # tiles/orthos (for rollback) and point back via superseded_by.
    is_consolidation = models.BooleanField(default=False, db_index=True,
        help_text="True if this row is a split-merge super-tile, not a single flight")
    # SET_NULL (NOT CASCADE): deleting the consolidation must free its members,
    # never delete them. rebuild_tiles_after_deletion heals latest/ from members.
    superseded_by = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='superseded_members',
        help_text="If set, this mission is a member of a consolidation and its tiles are overridden by it")

    # Mission metadata
    name = models.CharField(max_length=255, blank=True, help_text="Optional mission name")

    # Source photos stats
    source_photos_count = models.IntegerField(default=0)
    source_photos_size_mb = models.FloatField(default=0)

    # Per-direction photo counts (classified from gimbal pitch + yaw EXIF/XMP).
    # Keys: nadir, n, e, s, w, unknown. Values: photo counts.
    # Used for coverage pills UI. Threshold for "covered" = 50 photos per direction.
    direction_counts = models.JSONField(default=dict, blank=True)

    # Generated tiles stats
    tiles_count = models.IntegerField(default=0)
    tiles_size_mb = models.FloatField(default=0)
    min_zoom = models.IntegerField(default=13)
    max_zoom = models.IntegerField(default=23)

    # Center point for map display
    center_lat = models.FloatField(null=True, blank=True)
    center_lng = models.FloatField(null=True, blank=True)

    # Reverse-geocoded place (computed once at publish via local Pelias).
    # The card "Location" readout reads these stored fields; the client-side
    # lookup is only a fallback for missions not yet backfilled.
    place_label = models.CharField(max_length=120, blank=True, default='', help_text="Area name (parish/municipality) for the mission card readout")
    place_region = models.CharField(max_length=120, blank=True, default='', help_text="Region · country subtitle for the mission card readout")

    # Web Mercator tile coordinates (Z/X/Y, default Z17 ~305×240m)
    tile_z = models.SmallIntegerField(null=True, blank=True, default=17)
    tile_x = models.IntegerField(null=True, blank=True)
    tile_y = models.IntegerField(null=True, blank=True)

    # Processing sub-step (for real-time progress display)
    class ProcessingStep(models.TextChoices):
        ODM = 'odm', 'Running ODM'
        REPROJECTION = 'reprojection', 'Reprojecting'
        ALIGNMENT = 'alignment', 'Aligning'
        TILING = 'tiling', 'Generating tiles'
        MESH = 'mesh', 'Generating 3D mesh'
        FINALIZING = 'finalizing', 'Finalizing'

    processing_step = models.CharField(max_length=20, choices=ProcessingStep.choices, default='', blank=True)

    # Timestamps
    uploaded_at = models.DateTimeField(auto_now_add=True, db_index=True)
    captured_at = models.DateTimeField(null=True, blank=True, help_text="Earliest photo EXIF DateTimeOriginal")
    processing_started_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    # Error tracking
    error_message = models.TextField(blank=True, help_text="Error details if status=FAILED")

    # 3D Mesh generation
    mesh_status = models.CharField(max_length=15, choices=MeshStatus.choices, default=MeshStatus.NONE, db_index=True)
    mesh_size_mb = models.FloatField(default=0, help_text="ZIP archive size (OBJ+MTL+textures)")
    mesh_glb_size_mb = models.FloatField(default=0, help_text="GLB file size for browser viewer")
    mesh_error_message = models.TextField(blank=True, help_text="Error details if mesh_status=MESH_FAILED")
    mesh_requested_at = models.DateTimeField(null=True, blank=True)
    mesh_completed_at = models.DateTimeField(null=True, blank=True)

    # ODM reconstruction origin (UTM coords from odm_georeferencing/coords.txt)
    # Stored for 3D Tiles georeferencing: this is the (0,0,0) of the local OBJ coordinate system
    odm_origin = models.JSONField(null=True, blank=True, help_text="ODM origin {x, y, z} in UTM meters + EPSG code")

    # Cumulative similarity correction applied by the Phase-2 similarity BA
    # (composition of all applied deltas, about the ortho centroid, EPSG:3857).
    # Bookkeeping/debug only — the solver works in DELTA space against fresh
    # edges; nothing re-derives state from these. See realign_opensky_similarity.
    corr_ln_scale = models.FloatField(default=0.0, help_text="ln(scale) correction last applied (0 = none)")
    corr_rotation_deg = models.FloatField(default=0.0, help_text="Rotation correction last applied (deg, 0 = none)")
    corr_dx_m = models.FloatField(default=0.0, help_text="X translation correction last applied (m, EPSG:3857)")
    corr_dy_m = models.FloatField(default=0.0, help_text="Y translation correction last applied (m, EPSG:3857)")

    # When the saved ortho's georeference last changed physically (publish,
    # satellite/consensus shift, similarity warp). Pose edges measured BEFORE
    # this moment describe a frame that no longer exists on disk — the Phase-2
    # solver must ignore them (see § frame freshness in realign_opensky_similarity).
    georef_changed_at = models.DateTimeField(null=True, blank=True,
                                             help_text="Last physical georef change of the saved ortho")

    # Processing options
    satellite_align = models.BooleanField(default=False, help_text="Align to satellite imagery (ESRI) during processing")

    # Licensing (CC BY-SA 4.0): uploaded imagery + all derived ortho/mesh/tiles.
    # consent recorded at upload; pilot FK records who consented.
    license = models.CharField(max_length=32, default='CC-BY-SA-4.0', help_text="License of uploaded imagery + derived ortho/mesh/tiles")
    license_consent_at = models.DateTimeField(null=True, blank=True, help_text="When the pilot accepted the imagery license terms at upload")

    # Legacy fields (for future bounty system)
    reputation_reward = models.FloatField(default=1.0)
    published_data_cid = models.CharField(max_length=255, blank=True, help_text="IPFS CID for decentralized storage")

    class Meta:
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['status', 'uploaded_at']),
            models.Index(fields=['pilot', 'status']),
            models.Index(fields=['tile_z', 'tile_x', 'tile_y']),
        ]

    def __str__(self):
        return f"OpenSky {self.id[:8]} ({self.status})"

class OpenSkyTileLayer(models.Model):
    """
    Tracks which missions contribute to each tile in latest/.
    Used for rebuilding tiles when a mission is deleted.
    """
    z = models.IntegerField()
    x = models.IntegerField()
    y = models.IntegerField()
    mission = models.ForeignKey(OpenSkyMission, on_delete=models.CASCADE, related_name='tile_layers')
    layer_order = models.IntegerField(help_text="Order in compositing stack (higher = on top)")

    class Meta:
        unique_together = ('z', 'x', 'y', 'mission')
        indexes = [
            models.Index(fields=['z', 'x', 'y']),
            models.Index(fields=['mission']),
        ]

    def __str__(self):
        return f"Tile {self.z}/{self.x}/{self.y} <- Mission {self.mission_id[:8]}"

class OpenSkyConsolidationMember(models.Model):
    """
    Membership of a single-flight mission in a split-merge consolidation.

    The consolidation and each member are both OpenSkyMission rows; this through
    table records which flights were jointly reconstructed, plus the collision-safe
    image filename ``prefix`` (e.g. ``m00_``) used when pooling photos into one ODM
    project. ``order`` makes prefix assignment deterministic across re-runs.
    """
    consolidation = models.ForeignKey(OpenSkyMission, on_delete=models.CASCADE, related_name='members')
    member = models.ForeignKey(OpenSkyMission, on_delete=models.CASCADE, related_name='consolidation_links')
    prefix = models.CharField(max_length=16, help_text="Image filename prefix for this member in the joint ODM project")
    order = models.IntegerField(default=0)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('consolidation', 'member')
        ordering = ['order']
        indexes = [
            models.Index(fields=['consolidation']),
            models.Index(fields=['member']),
        ]

    def __str__(self):
        return f"{self.consolidation_id[:8]} <- {self.member_id[:8]} ({self.prefix})"

class OpenSkyPoseEdge(models.Model):
    """
    Pose graph edge — one observation relating two missions or one mission to
    the absolute reference frame.

    Edges are immutable raw data. Mission positions are derived from edges via
    consensus (Phase 1) or regional bundle adjustment (Phase 2). See
    PK/opensky-system.md § Pose Graph Architecture.
    """
    class EdgeType(models.TextChoices):
        ORB_PAIR = 'orb_pair', 'ORB feature match vs another mission'
        SATELLITE_ANCHOR = 'satellite_anchor', 'ECC alignment vs satellite imagery (absolute anchor)'

    mission_a = models.ForeignKey(
        OpenSkyMission, on_delete=models.CASCADE, related_name='pose_edges_outgoing',
        help_text="Mission whose position is being measured (perspective).",
    )
    mission_b = models.ForeignKey(
        OpenSkyMission, on_delete=models.CASCADE, null=True, blank=True,
        related_name='pose_edges_incoming',
        help_text="Reference neighbor. NULL for SATELLITE_ANCHOR (absolute frame).",
    )
    edge_type = models.CharField(max_length=20, choices=EdgeType.choices, db_index=True)
    dx_m = models.FloatField(help_text="X shift (m, EPSG:3857) to apply to mission_a to align with mission_b (or absolute frame)")
    dy_m = models.FloatField(help_text="Y shift (m, EPSG:3857) to apply to mission_a to align with mission_b (or absolute frame)")
    # Similarity components of the ORB measurement (Phase 2 similarity BA).
    # rel_scale = size(mission_b)/size(mission_a); rel_rotation_deg = map-frame
    # rotation of mission_a onto mission_b. Defaults make legacy translation-only
    # edges valid similarities (s=1, θ=0). SATELLITE_ANCHOR observes neither.
    rel_scale = models.FloatField(default=1.0, help_text="Relative scale s_ij of mission_a vs mission_b (ORB only)")
    rel_rotation_deg = models.FloatField(default=0.0, help_text="Relative rotation (deg, map frame) of mission_a vs mission_b (ORB only)")
    # Where dx/dy is referenced: the (west, north) corner of the measured
    # intersection window (= pixel (0,0) of the ORB affine), EPSG:3857. The
    # Phase-2 lever-arm needs this exact point; NULL (legacy edges / anchors)
    # falls back to the nominal Z17-cell intersection corner (~0.2-0.5m error).
    ref_x_3857 = models.FloatField(null=True, blank=True, help_text="X of the translation reference point (m, EPSG:3857)")
    ref_y_3857 = models.FloatField(null=True, blank=True, help_text="Y of the translation reference point (m, EPSG:3857)")
    weight = models.FloatField(default=1.0, help_text="Solver weight (e.g. overlap area for ORB)")
    confidence = models.FloatField(default=1.0, help_text="Observation quality (RANSAC inlier ratio for ORB, ECC correlation for satellite)")
    overlap_area_m2 = models.FloatField(default=0, help_text="Geographic intersection area (ORB only)")
    measured_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['mission_a', 'edge_type']),
            models.Index(fields=['mission_b', 'edge_type']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['mission_a', 'mission_b', 'edge_type'],
                name='unique_pose_edge',
            ),
        ]

    def __str__(self):
        b = self.mission_b_id[:8] if self.mission_b_id else 'SAT'
        return f"PoseEdge {self.mission_a_id[:8]} → {b} [{self.edge_type}] ({self.dx_m:+.2f}, {self.dy_m:+.2f})"
