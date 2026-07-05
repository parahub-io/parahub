"""
OpenSky Aerial Imagery Processor.

All processing and storage on skystore (Home PT, <SKYSTORE_IP> via WireGuard).
Hetzner orchestrates via SSH, only DB updates are local.

Pipeline: Upload JPG → rsync to skystore → ODM GPU → gdalwarp → alignment →
gdal2tiles → TMS→XYZ WebP → hard links to latest/ → PUBLISHED.

Package layout (by pipeline step):
  constants      paths, ODM params, tile pyramid, alignment/consensus/similarity tunables
  remote         skystore SSH/rsync transport (retry semantics)
  common         tile advisory lock, WS publish, reverse geocode, superseded guard
  ingest         Step 1: photo upload to skystore + orphaned-scratch sweep
  odm            Step 2: ODM Docker GPU runners (per-mission + split-merge)
  satellite      Step 3.4: ECC vs ESRI World Imagery (absolute reference)
  pose_graph     Step 3.5a: ORB edge measurement + persistence + frame freshness
  consensus      Step 3.5b / Phase 1: robust translation consensus
  similarity     Phase 2: similarity bundle adjustment (delta space)
  tiles          Steps 4-5: grid math, tiling scripts, latest/ composite, retile, deletion
  mesh           Step 5.5: ODM origin, ground level, OBJ→GLB chain
  pipeline       process_mission orchestrator (Steps 1-7)
  consolidation  split-merge super-tile (joint ODM over member photos)

Storage (on skystore /skystore/):
  /skystore/opensky/missions/{id}/images/   # Source photos
  /skystore/opensky/orthos/{id}.tif         # Preserved orthophotos (EPSG:3857, unclipped)
  /fast-processing/{id}/                    # ODM temp files (NVMe)
  /skystore/opensky/meshes/{id}/            # 3D mesh artifacts
  /skystore/opensky-tiles/missions/{id}/{z}/{x}/{y}.webp  # Mission tiles
  /skystore/opensky-tiles/latest/{z}/{x}/{y}.webp         # Hard links

Local temp (Hetzner /mnt/opensky/):
  missions/{id}/images/  # Upload buffer only, deleted after rsync to skystore

Every historical top-level name is re-exported here so
`from geo.opensky_processor import X` keeps working everywhere (management
commands, endpoints, tiles3d_generator, tests).
"""

from .constants import (
    ALIGNMENT_MAX_OFFSET_METERS,
    GLTF_TRANSFORM_PATH,
    MAX_CONSENSUS_SHIFT_M,
    MAX_CONSOLIDATION_PHOTOS,
    MESHES_LOCAL_DIR,
    MIN_CONSENSUS_SHIFT_M,
    MIN_FAST_PROCESSING_FREE_GB,
    NODE_BIN_DIR,
    OBJ2GLTF_PATH,
    ODM_MAX_CONCURRENCY,
    ODM_RESOLUTION,
    ODM_SPLIT,
    ODM_SPLIT_OVERLAP,
    OPENSKY_BASE,
    ORTHOS_DIR,
    OUTLIER_FLOOR_M,
    OUTLIER_MEDIAN_MULTIPLE,
    SATELLITE_CACHE_DIR,
    SATELLITE_DAMPING_WEIGHT,
    SATELLITE_ECC_MIN_CC,
    SATELLITE_TILE_URL,
    SATELLITE_TILE_ZOOM,
    SIM_APPLY_ROT_DEG,
    SIM_APPLY_SCALE,
    SIM_APPLY_TRANS_M,
    SIM_GAUGE_PRIOR,
    SIM_MAX_SEASON_GAP_DAYS,
    SIM_ROT_OUTLIER_FLOOR_DEG,
    SIM_SCALE_OUTLIER_FLOOR,
    SIM_TRANS_PRIOR,
    SKYSTORE_3DTILES,
    SKYSTORE_FAST_PROCESSING,
    SKYSTORE_ODM_IMAGE,
    SKYSTORE_OPENSKY,
    SKYSTORE_SSH,
    SKYSTORE_TILES,
    TILES_BASE,
    TILE_MAX_ZOOM,
    TILE_MIN_ZOOM,
    TILE_ZOOM_OVERVIEW_MAX,
    WEBP_QUALITY,
)
from .common import (
    OPENSKY_TILE_LOCK_KEY,
    PELIAS_URL,
    _is_superseded,
    _publish_mission_update,
    opensky_tile_lock,
    reverse_geocode_place,
)
from .remote import _skystore_rsync, _skystore_ssh
from .ingest import (
    FAST_PROCESSING_ORPHAN_HOURS,
    sweep_orphaned_processing_dirs,
    upload_to_skystore,
)
from .odm import (
    _await_odm_container,
    _save_odm_failure_logs,
    run_odm_skystore,
    run_odm_splitmerge_skystore,
)
from .tiles import (
    _build_coverage_script,
    _build_partial_composite_script,
    _build_rebuild_tiles_script,
    _build_tms_to_xyz_webp_script,
    _build_update_latest_script,
    _clear_self_owned_latest_tiles,
    _consolidation_union_bounds_3857,
    _record_tile_layers,
    _reclip_retile_publish,
    _z17_tile_bounds_3857,
    composite_partial_consolidation_tiles,
    delete_skystore_mission_files,
    fill_consolidation_holes_from_members,
    rebuild_overview_latest,
    rebuild_tiles_after_deletion,
    retile_mission_skystore,
)
from .pose_graph import (
    _build_multi_neighbor_alignment_script,
    _edge_is_fresh,
    _mark_georef_changed,
    _parse_alignment_output,
    _write_orb_edges,
    _write_satellite_anchor,
    measure_orb_edges_skystore,
)
from .satellite import (
    _build_satellite_alignment_script,
    apply_satellite_alignment_skystore,
    check_satellite_alignment_skystore,
)
from .consensus import (
    _build_apply_shift_script,
    apply_consensus_alignment_skystore,
    compute_consensus_shift,
)
from .similarity import (
    _build_similarity_warp_script,
    _compose_similarity_about_centroid,
    apply_similarity_correction_skystore,
    solve_similarity_ba,
)
from .mesh import _compute_mesh_ground_z, _extract_odm_origin, _process_mesh_artifacts
from .pipeline import process_mission
from .consolidation import (
    SAT_LARGE_SHIFT_M,
    SAT_LARGE_SHIFT_MIN_CC,
    _anchor_merged_ortho,
    _fit_similarity_to_members,
    _measure_consolidation_vs_members,
    process_consolidation,
    realign_consolidation_to_members,
)

__all__ = [
    # constants
    'ALIGNMENT_MAX_OFFSET_METERS', 'GLTF_TRANSFORM_PATH', 'MAX_CONSENSUS_SHIFT_M',
    'MAX_CONSOLIDATION_PHOTOS', 'MESHES_LOCAL_DIR', 'MIN_CONSENSUS_SHIFT_M',
    'MIN_FAST_PROCESSING_FREE_GB', 'NODE_BIN_DIR', 'OBJ2GLTF_PATH',
    'ODM_MAX_CONCURRENCY', 'ODM_RESOLUTION', 'ODM_SPLIT', 'ODM_SPLIT_OVERLAP',
    'OPENSKY_BASE', 'ORTHOS_DIR', 'OUTLIER_FLOOR_M', 'OUTLIER_MEDIAN_MULTIPLE',
    'SATELLITE_CACHE_DIR', 'SATELLITE_DAMPING_WEIGHT', 'SATELLITE_ECC_MIN_CC',
    'SATELLITE_TILE_URL', 'SATELLITE_TILE_ZOOM', 'SIM_APPLY_ROT_DEG',
    'SIM_APPLY_SCALE', 'SIM_APPLY_TRANS_M', 'SIM_GAUGE_PRIOR',
    'SIM_MAX_SEASON_GAP_DAYS', 'SIM_ROT_OUTLIER_FLOOR_DEG',
    'SIM_SCALE_OUTLIER_FLOOR', 'SIM_TRANS_PRIOR', 'SKYSTORE_3DTILES',
    'SKYSTORE_FAST_PROCESSING', 'SKYSTORE_ODM_IMAGE', 'SKYSTORE_OPENSKY',
    'SKYSTORE_SSH', 'SKYSTORE_TILES', 'TILES_BASE', 'TILE_MAX_ZOOM',
    'TILE_MIN_ZOOM', 'TILE_ZOOM_OVERVIEW_MAX', 'WEBP_QUALITY',
    'OPENSKY_TILE_LOCK_KEY', 'PELIAS_URL', 'FAST_PROCESSING_ORPHAN_HOURS',
    'SAT_LARGE_SHIFT_M', 'SAT_LARGE_SHIFT_MIN_CC',
    # common / remote / ingest / odm
    '_is_superseded', '_publish_mission_update', 'opensky_tile_lock',
    'reverse_geocode_place', '_skystore_rsync', '_skystore_ssh',
    'sweep_orphaned_processing_dirs', 'upload_to_skystore',
    '_await_odm_container', '_save_odm_failure_logs', 'run_odm_skystore',
    'run_odm_splitmerge_skystore',
    # tiles
    '_build_coverage_script', '_build_partial_composite_script',
    '_build_rebuild_tiles_script', '_build_tms_to_xyz_webp_script',
    '_build_update_latest_script', '_clear_self_owned_latest_tiles',
    '_consolidation_union_bounds_3857', '_record_tile_layers',
    '_reclip_retile_publish', '_z17_tile_bounds_3857',
    'composite_partial_consolidation_tiles', 'delete_skystore_mission_files',
    'fill_consolidation_holes_from_members', 'rebuild_overview_latest',
    'rebuild_tiles_after_deletion', 'retile_mission_skystore',
    # pose graph / satellite / consensus / similarity
    '_build_multi_neighbor_alignment_script', '_edge_is_fresh',
    '_mark_georef_changed', '_parse_alignment_output', '_write_orb_edges',
    '_write_satellite_anchor', 'measure_orb_edges_skystore',
    '_build_satellite_alignment_script', 'apply_satellite_alignment_skystore',
    'check_satellite_alignment_skystore', '_build_apply_shift_script',
    'apply_consensus_alignment_skystore', 'compute_consensus_shift',
    '_build_similarity_warp_script', '_compose_similarity_about_centroid',
    'apply_similarity_correction_skystore', 'solve_similarity_ba',
    # mesh / pipeline / consolidation
    '_compute_mesh_ground_z', '_extract_odm_origin', '_process_mesh_artifacts',
    'process_mission', '_anchor_merged_ortho', '_fit_similarity_to_members',
    '_measure_consolidation_vs_members', 'process_consolidation',
    'realign_consolidation_to_members',
]
