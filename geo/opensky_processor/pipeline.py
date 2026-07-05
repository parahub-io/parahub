"""
The per-mission pipeline orchestrator (Steps 1-7): upload → ODM → reproject →
satellite + consensus alignment → save unclipped ortho → Z17 clip → tile →
latest/ + overviews → mesh + 3D Tiles → publish → cleanup.
"""

import logging
import os
import shlex
import shutil
import subprocess

from django.contrib.gis.geos import Polygon
from django.utils import timezone

from .common import _publish_mission_update, reverse_geocode_place
from .consensus import _build_apply_shift_script, compute_consensus_shift
from .constants import (
    MAX_CONSENSUS_SHIFT_M, MESHES_LOCAL_DIR, MIN_CONSENSUS_SHIFT_M,
    OPENSKY_BASE, SATELLITE_CACHE_DIR, SKYSTORE_FAST_PROCESSING,
    SKYSTORE_OPENSKY, SKYSTORE_TILES, TILE_MAX_ZOOM, TILE_MIN_ZOOM,
    WEBP_QUALITY,
)
from .ingest import upload_to_skystore
from .mesh import _compute_mesh_ground_z, _extract_odm_origin, _process_mesh_artifacts
from .odm import run_odm_skystore
from .pose_graph import (
    _build_multi_neighbor_alignment_script, _parse_alignment_output,
    _write_orb_edges, _write_satellite_anchor,
)
from .remote import _skystore_ssh
from .satellite import _build_satellite_alignment_script
from .tiles import (
    _build_coverage_script, _build_tms_to_xyz_webp_script,
    _build_update_latest_script, _clear_self_owned_latest_tiles,
    _record_tile_layers, _z17_tile_bounds_3857, rebuild_overview_latest,
)

logger = logging.getLogger(__name__)


def process_mission(mission_id: str, dry_run: bool = False) -> bool:
    """
    Full pipeline for processing an OpenSky mission.

    Args:
        mission_id: ULID of the mission to process
        dry_run: If True, only log what would be done

    Returns:
        True on success, False on failure
    """
    from geo.models import OpenSkyMission

    logger.info(f"Starting processing for mission {mission_id}")

    try:
        mission = OpenSkyMission.objects.get(id=mission_id)
    except OpenSkyMission.DoesNotExist:
        logger.error(f"Mission {mission_id} not found")
        return False

    if mission.status != OpenSkyMission.Status.QUEUED:
        logger.warning(f"Mission {mission_id} is not in QUEUED status (current: {mission.status})")
        return False

    # Update status to PROCESSING (clear previous error if retrying)
    mission.status = OpenSkyMission.Status.PROCESSING
    mission.processing_started_at = timezone.now()
    mission.processing_step = OpenSkyMission.ProcessingStep.ODM
    mission.error_message = ''

    # Set area + center NOW from the planned Z17 tile bounds (clean rectangle).
    # tile_z/x/y are known at upload time, so we don't need to wait for any
    # processing output. Setting area early is critical because
    # generate_3d_tiles_for_mission() → regenerate_root_tileset() filters by
    # `area__isnull=False`; if we set area only at Step 6, the root tileset
    # gets generated WITHOUT this mission and is then deleted. Legacy missions
    # without tile_z/x/y still fall back to coverage_polygon at Step 6.
    if mission.tile_z and mission.tile_x is not None and mission.tile_y is not None:
        from pyproj import Transformer
        xmin_3857, ymin_3857, xmax_3857, ymax_3857 = _z17_tile_bounds_3857(
            mission.tile_z, mission.tile_x, mission.tile_y, buffer_m=0
        )
        t = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
        sw_lng, sw_lat = t.transform(xmin_3857, ymin_3857)
        ne_lng, ne_lat = t.transform(xmax_3857, ymax_3857)
        mission.area = Polygon((
            (sw_lng, sw_lat),
            (ne_lng, sw_lat),
            (ne_lng, ne_lat),
            (sw_lng, ne_lat),
            (sw_lng, sw_lat),
        ))
        mission.center_lat = (sw_lat + ne_lat) / 2
        mission.center_lng = (sw_lng + ne_lng) / 2

    mission.save(update_fields=[
        'status', 'processing_started_at', 'processing_step', 'error_message',
        'area', 'center_lat', 'center_lng',
    ])
    _publish_mission_update(mission.id, {
        'status': 'PROCESSING',
        'processing_step': 'odm',
        'processing_started_at': mission.processing_started_at.isoformat(),
    })

    # Processing temp on SSD, permanent storage on HDD (ZFS)
    local_images = f"{OPENSKY_BASE}/missions/{mission_id}/images"
    r_images = f"{SKYSTORE_OPENSKY}/missions/{mission_id}/images"
    r_processing = f"{SKYSTORE_FAST_PROCESSING}/{mission_id}"
    r_orthos = f"{SKYSTORE_OPENSKY}/orthos"
    r_tiles_mission = f"{SKYSTORE_TILES}/missions/{mission_id}"
    r_tiles_latest = f"{SKYSTORE_TILES}/latest"

    try:
        if dry_run:
            logger.info(f"[DRY RUN] Would process mission {mission_id}")
            return True

        # Check if images already on skystore (e.g. retry after previous partial failure)
        remote_count_result = _skystore_ssh(f"ls {r_images}/*.JPG {r_images}/*.jpg 2>/dev/null | wc -l")
        remote_image_count = int(remote_count_result.stdout.strip())

        if os.path.exists(local_images):
            image_count = len([f for f in os.listdir(local_images) if f.lower().endswith(('.jpg', '.jpeg'))])
            if image_count == 0 and remote_image_count == 0:
                raise ValueError("No JPG images found in images directory")
            logger.info(f"Found {image_count} images locally")
            # Step 1: Upload photos to skystore, delete local
            logger.info("Step 1: Uploading photos to skystore...")
            upload_to_skystore(mission_id)
        elif remote_image_count > 0:
            logger.info(f"Step 1: Skipped — {remote_image_count} images already on skystore")
        else:
            raise FileNotFoundError(f"Images not found locally ({local_images}) or on skystore ({r_images})")

        # Step 2: Run ODM on skystore (GPU)
        logger.info("Step 2: Running ODM on skystore (GPU)...")
        remote_ortho = run_odm_skystore(mission_id)
        logger.info(f"ODM completed on skystore: {remote_ortho}")

        # Step 3: Reproject to Web Mercator (on skystore via SSH)
        mission.processing_step = OpenSkyMission.ProcessingStep.REPROJECTION
        mission.save(update_fields=['processing_step'])
        _publish_mission_update(mission.id, {'status': 'PROCESSING', 'processing_step': 'reprojection'})
        logger.info("Step 3: Reprojecting on skystore...")
        r_reprojected = f"{r_processing}/orthophoto_3857.tif"
        # Skip if already done (from previous partial run)
        check = _skystore_ssh(f"test -f {r_reprojected} && echo exists || echo missing")
        if "exists" in check.stdout:
            logger.info(f"Reprojected orthophoto already exists, skipping: {r_reprojected}")
        else:
            _skystore_ssh(
                f"gdalwarp -t_srs EPSG:3857 -r lanczos -co COMPRESS=LZW -co TILED=YES"
                f" {remote_ortho} {r_reprojected}",
                timeout=1800,
            )
        r_final_ortho = r_reprojected

        # Step 3.4: Satellite alignment (always — absolute reference).
        # Every mission is aligned to ESRI World Imagery so all tiles share
        # one global reference frame.  Eliminates chain-dependency on the
        # first-ever mission's raw GPS and prevents inter-mission seams.
        mission.processing_step = OpenSkyMission.ProcessingStep.ALIGNMENT
        mission.save(update_fields=['processing_step'])
        _publish_mission_update(mission.id, {'status': 'PROCESSING', 'processing_step': 'alignment'})

        r_sat_aligned = f"{r_processing}/orthophoto_sat_aligned.tif"
        logger.info("Step 3.4: Satellite alignment (absolute reference)...")
        sat_script = _build_satellite_alignment_script(r_reprojected, r_sat_aligned, SATELLITE_CACHE_DIR)
        sat_result = _skystore_ssh(f"python3 -c {shlex.quote(sat_script)}", timeout=1800)
        sat_dx = sat_dy = sat_cc = sat_offset = 0.0
        for line in (sat_result.stdout or '').strip().splitlines():
            if line.startswith('SAT_RESULT:'):
                logger.info(f"Step 3.4: {line}")
                try:
                    parts = line.split(':')
                    sat_dx = float(parts[1])
                    sat_dy = float(parts[2])
                    sat_cc = float(parts[3])
                    sat_offset = float(parts[4])
                except (ValueError, IndexError):
                    pass
        sat_check = _skystore_ssh(f"test -f {r_sat_aligned} && echo aligned || echo identity")
        if "aligned" in sat_check.stdout:
            r_after_sat = r_sat_aligned
            mission.satellite_align = True
            mission.save(update_fields=['satellite_align'])
            _write_satellite_anchor(mission_id, sat_dx, sat_dy, sat_cc)
            logger.info("Satellite-aligned (absolute reference)")
        else:
            r_after_sat = r_reprojected
            logger.info("Satellite alignment skipped (low correlation or negligible offset)")

        # Step 3.5: Multi-neighbor consensus alignment (refinement).
        # See PK/opensky-system.md § Pose Graph Architecture. Measures ORB
        # shift vs EVERY overlapping published neighbor, writes ORB_PAIR pose
        # edges to DB, applies weighted-average shift to this mission only.
        ref_check = _skystore_ssh(f"ls {r_orthos}/*.tif 2>/dev/null | wc -l")
        has_references = int(ref_check.stdout.strip()) > 0

        if has_references:
            logger.info("Step 3.5: Multi-neighbor consensus alignment...")
            r_aligned = f"{r_processing}/orthophoto_aligned.tif"
            measurement_script = _build_multi_neighbor_alignment_script(
                mission_id, r_after_sat, r_orthos,
            )
            result = _skystore_ssh(f"python3 -c {shlex.quote(measurement_script)}", timeout=3600)
            edges = _parse_alignment_output(mission_id, result.stdout or '')
            _write_orb_edges(mission_id, edges)
            cs = compute_consensus_shift(mission_id, edges)
            logger.info(
                f"Step 3.5: edges_measured={len(edges)} used={cs['n_used']} "
                f"outliers_filtered={cs['n_filtered_outliers']} "
                f"shift=({cs['avg_dx']:+.2f},{cs['avg_dy']:+.2f})m |s|={cs['shift_m']:.2f}m"
            )
            if MIN_CONSENSUS_SHIFT_M <= cs['shift_m'] <= MAX_CONSENSUS_SHIFT_M:
                apply_script = _build_apply_shift_script(
                    r_after_sat, r_aligned, cs['avg_dx'], cs['avg_dy'],
                )
                _skystore_ssh(f"python3 -c {shlex.quote(apply_script)}", timeout=300)
                r_final_ortho = r_aligned
                logger.info("Consensus-refined against neighbors")
            else:
                r_final_ortho = r_after_sat
                if cs['shift_m'] > MAX_CONSENSUS_SHIFT_M:
                    logger.warning(
                        f"Step 3.5: shift {cs['shift_m']:.2f}m exceeds MAX_CONSENSUS_SHIFT_M — "
                        f"not applying (safety cap)"
                    )
        else:
            r_final_ortho = r_after_sat

        # Step 3.6: Save FULL (unclipped) orthophoto for future neighbor
        # alignment. Cross-mission alignment uses ORB feature matching across
        # the 37m flight buffer overlap — needs the unclipped ortho to find
        # features in the overlap region. Clipping happens AFTER this save.
        _skystore_ssh(f"mkdir -p {r_orthos} && cp {r_final_ortho} {r_orthos}/{mission_id}.tif")

        # Step 3.7: Clip orthophoto to mission's planned Z17 tile bounds
        # (no buffer). With current newest-wins tile composition (no blending),
        # buffer=0 is mathematically optimal: each mission writes EXACTLY its
        # own tiles, no overlap, no overhead, no quality degradation when a
        # neighbor's oblique-edge pixels would otherwise overwrite this
        # mission's nadir tiles. ODM source overlap (BUFFER_M=37 in
        # mission_generator) is preserved at the flight planning level for
        # ODM stitching, but is NOT carried into the final tile output.
        if mission.tile_z and mission.tile_x is not None and mission.tile_y is not None:
            r_clipped = f"{r_processing}/orthophoto_clipped.tif"
            # Skip if already done (from previous partial run) — same pattern as Step 3.
            check = _skystore_ssh(f"test -f {r_clipped} && echo exists || echo missing")
            if "exists" in check.stdout:
                logger.info(f"Clipped orthophoto already exists, skipping: {r_clipped}")
            else:
                xmin, ymin, xmax, ymax = _z17_tile_bounds_3857(
                    mission.tile_z, mission.tile_x, mission.tile_y, buffer_m=0
                )
                logger.info(
                    f"Step 3.7: Clipping ortho to Z{mission.tile_z}/{mission.tile_x}/{mission.tile_y} "
                    f"({xmin:.1f},{ymin:.1f},{xmax:.1f},{ymax:.1f} EPSG:3857)..."
                )
                _skystore_ssh(
                    f"gdalwarp -te {xmin} {ymin} {xmax} {ymax} -te_srs EPSG:3857 "
                    f"-r lanczos -co COMPRESS=LZW -co TILED=YES -dstnodata 0 "
                    f"-overwrite {r_final_ortho} {r_clipped}",
                    timeout=600,
                )
            r_final_ortho = r_clipped
        else:
            logger.warning(f"Mission {mission_id} has no tile_z/x/y — skipping clip")

        # Step 4: Generate tiles on skystore
        mission.processing_step = OpenSkyMission.ProcessingStep.TILING
        mission.save(update_fields=['processing_step'])
        _publish_mission_update(mission.id, {'status': 'PROCESSING', 'processing_step': 'tiling'})
        logger.info("Step 4: Generating tiles on skystore...")
        r_tms = f"{r_processing}/tiles_tms"
        # Timeout 8h: gdal2tiles z11-z22 on a Z17-clipped ortho takes ~3 min
        # for ~600-photo missions. Headroom kept for edge cases (large missions,
        # disk contention, retry).
        _skystore_ssh(
            f"gdal2tiles.py -z {TILE_MIN_ZOOM}-{TILE_MAX_ZOOM} -w none -r lanczos"
            f" --processes=3 {r_final_ortho} {r_tms}",
            timeout=28800,
        )

        # Step 4.1: Convert TMS→XYZ WebP on skystore
        logger.info("Step 4.1: Converting to XYZ WebP on skystore...")
        # Reprocess of a PUBLISHED mission (append-photos flow): the new
        # pyramid may be shifted by Step 3.4/3.5, leaving latest/ links to
        # the old tiles at coords the new pyramid no longer covers, or
        # marginally-smaller new tiles losing to old ones via size-wins.
        # Clear this mission's own latest/ tiles before overwriting its dir
        # (ownership-guarded — neighbors' tiles survive). No-op for fresh
        # missions (no OpenSkyTileLayer rows yet).
        _clear_self_owned_latest_tiles(mission_id, r_tiles_latest, r_tiles_mission)
        _skystore_ssh(f"mkdir -p {r_tiles_mission}")
        convert_script = _build_tms_to_xyz_webp_script(r_tms, r_tiles_mission, WEBP_QUALITY)
        result = _skystore_ssh(f"python3 -c {shlex.quote(convert_script)}", timeout=3600)
        # Parse tiles_count and tiles_size from script output
        for line in result.stdout.strip().splitlines():
            if line.startswith("TILES_RESULT:"):
                parts = line.split(":")
                tiles_count = int(parts[1])
                tiles_size = int(parts[2])
                break
        else:
            tiles_count = 0
            tiles_size = 0
        logger.info(f"Generated {tiles_count} tiles ({tiles_size / 1024 / 1024:.2f} MB)")

        # Sanity check: reject empty-placeholder pyramids. A legitimate aerial
        # mission produces WebP tiles averaging tens of KB (NVY baseline: ~27KB
        # at Z17). A ~200 B placeholder pyramid (1500 tiles × 202 B = 0.29 MB)
        # means the clipped ortho has zero real pixels — usually because Step
        # 3.5 alignment moved the ortho outside the target tile bounds (past
        # incident: 01KNQ3C9NA5CJ7VKQP6PAEBMFY, 01KNQ3R21JZYNQEJRDYM0KSNRB
        # on 2026-04-08). Fail loud here instead of publishing an empty tile.
        if tiles_count > 0:
            avg_tile_bytes = tiles_size / tiles_count
            if avg_tile_bytes < 1024:
                raise RuntimeError(
                    f"Empty tile pyramid: {tiles_count} tiles averaging "
                    f"{avg_tile_bytes:.0f} B (< 1 KB). Clipped ortho contains "
                    f"no real pixels — check Step 3.5 alignment logs."
                )

        # Step 5: Calculate coverage polygon (on skystore)
        logger.info("Step 5: Calculating coverage polygon on skystore...")
        coverage_script = _build_coverage_script(r_tiles_mission)
        result = _skystore_ssh(f"python3 -c {shlex.quote(coverage_script)}", timeout=300)
        coverage_polygon = None
        bounds = None
        for line in result.stdout.strip().splitlines():
            if line.startswith("COVERAGE:"):
                import json as _json
                data = _json.loads(line[9:])
                if data.get('polygon'):
                    coverage_polygon = Polygon(data['polygon'])
                if data.get('bounds'):
                    bounds = data['bounds']

        # Step 5.1: Update latest layer on skystore
        mission.processing_step = OpenSkyMission.ProcessingStep.FINALIZING
        mission.save(update_fields=['processing_step'])
        _publish_mission_update(mission.id, {'status': 'PROCESSING', 'processing_step': 'finalizing'})
        logger.info("Step 5.1: Updating latest layer on skystore...")
        latest_script = _build_update_latest_script(r_tiles_mission, r_tiles_latest, mission_id)
        result = _skystore_ssh(f"python3 -c {shlex.quote(latest_script)}", timeout=600)
        # Surface update_latest result (written vs skipped) for debugging
        for line in (result.stdout or '').strip().splitlines():
            if line.startswith('Updated '):
                logger.info(f"Step 5.1: {line}")

        # Step 5.2: Record tile contributions in DB for deletion support
        logger.info("Step 5.2: Recording tile contributions...")
        _record_tile_layers(mission_id, r_tiles_mission)
        # Overview tiles (z<=16) span multiple Z17 missions; size-wins above
        # keeps only one mission's partial tile, so recomposite from all
        # contributors here (the union) — otherwise zoomed-out map has holes.
        rebuild_overview_latest(mission_id)

        # Step 5.5: 3D Mesh generation (merged pipeline — ODM already produced mesh)
        mission.processing_step = OpenSkyMission.ProcessingStep.MESH
        mission.save(update_fields=['processing_step'])
        _publish_mission_update(mission.id, {'status': 'PROCESSING', 'processing_step': 'mesh'})
        mesh_ok = False
        try:
            # Verify ODM produced mesh output
            remote_texturing = f"{r_processing}/odm_texturing"
            check = _skystore_ssh(f"test -f {remote_texturing}/odm_textured_model_geo.obj && echo ok || echo no")
            if "ok" in check.stdout:
                logger.info("Step 5.5: Processing 3D mesh artifacts...")

                # Extract ODM origin for georeferencing (before cleanup!)
                odm_origin = _extract_odm_origin(r_processing)
                if odm_origin:
                    mission.odm_origin = odm_origin
                    mission.save(update_fields=['odm_origin'])

                # Download, convert OBJ→GLB, optimize, upload to skystore
                glb_size_mb, local_mesh = _process_mesh_artifacts(mission_id, r_processing)

                # Compute mesh ground level (p5 of vertex z) and shift origin
                # so the mesh's ground sits at WGS84 ellipsoid altitude 0,
                # matching the flat OSM base layer. Otherwise the mesh appears
                # to "float in the sky" because vertex z values encode altitude
                # relative to ODM's local frame anchor (not ellipsoid).
                if odm_origin:
                    ground_z = _compute_mesh_ground_z(mission_id)
                    if ground_z is not None:
                        odm_origin['z'] = -ground_z
                        mission.odm_origin = odm_origin
                        mission.save(update_fields=['odm_origin'])
                        logger.info(f"Shifted origin by ground_z={ground_z:.2f} (mesh p5)")

                # Persist coords.txt + proj.txt + odm_georeferencing_model_geo.txt
                # into meshes/ so future tileset regeneration can recompute the
                # ECEF transform without re-running ODM. MUST run AFTER
                # _process_mesh_artifacts because that function does
                # `rsync --delete` to meshes/ and would otherwise wipe these files.
                remote_meshes = f"{SKYSTORE_OPENSKY}/meshes/{mission_id}"
                try:
                    _skystore_ssh(
                        f"mkdir -p {remote_meshes} && "
                        f"cp -f {r_processing}/odm_georeferencing/coords.txt {remote_meshes}/coords.txt 2>/dev/null; "
                        f"cp -f {r_processing}/odm_georeferencing/proj.txt {remote_meshes}/proj.txt 2>/dev/null; "
                        f"cp -f {r_processing}/odm_georeferencing/odm_georeferencing_model_geo.txt {remote_meshes}/odm_georeferencing_model_geo.txt 2>/dev/null; "
                        f"true"
                    )
                except Exception as e:
                    logger.warning(f"Could not persist coords/proj.txt: {e}")

                mission.mesh_status = OpenSkyMission.MeshStatus.MESH_READY
                mission.mesh_size_mb = glb_size_mb
                mission.mesh_glb_size_mb = glb_size_mb
                mission.mesh_completed_at = timezone.now()
                mission.mesh_error_message = ''
                # IMPORTANT: persist MESH_READY BEFORE generate_3d_tiles_for_mission,
                # because its regenerate_root_tileset() queries the DB for MESH_READY missions.
                # Without this, the root tileset gets deleted right after it's created.
                mission.save(update_fields=[
                    'mesh_status', 'mesh_size_mb', 'mesh_glb_size_mb',
                    'mesh_completed_at', 'mesh_error_message',
                ])
                mesh_ok = True
                logger.info(f"Mesh generation complete: {glb_size_mb} MB GLB")

                # Step 5.6: Generate 3D Tiles (LODs + tileset.json)
                try:
                    from geo.tiles3d_generator import generate_3d_tiles_for_mission
                    glb_on_skystore = f"{SKYSTORE_OPENSKY}/meshes/{mission_id}/model.glb"
                    # GLB was just uploaded to skystore, use local copy if still available
                    local_glb = os.path.join(local_mesh, "model.glb")
                    if os.path.exists(local_glb):
                        generate_3d_tiles_for_mission(mission, glb_path=local_glb)
                    else:
                        generate_3d_tiles_for_mission(mission)
                    logger.info("3D Tiles generated successfully")
                except Exception as e:
                    logger.error(f"3D Tiles generation failed (non-fatal): {e}", exc_info=True)
            else:
                logger.warning("ODM did not produce mesh output — skipping mesh step")
        except Exception as e:
            logger.error(f"Mesh generation failed (non-fatal): {e}", exc_info=True)
            mission.mesh_status = OpenSkyMission.MeshStatus.MESH_FAILED
            mission.mesh_error_message = str(e)[:1000]
        finally:
            # Cleanup local mesh temp dir
            local_mesh_dir = f"{MESHES_LOCAL_DIR}/{mission_id}"
            if os.path.exists(local_mesh_dir):
                shutil.rmtree(local_mesh_dir, ignore_errors=True)

        # Step 6: Update mission record
        mission.status = OpenSkyMission.Status.PUBLISHED
        mission.published_at = timezone.now()
        # A fresh ortho was saved (Step 3.6, possibly consensus-shifted AFTER
        # the Step 3.5 edges were measured) — mark the frame as new so Phase-2
        # only consumes edges measured against it (measure_opensky_edges).
        mission.georef_changed_at = timezone.now()
        mission.tiles_count = tiles_count
        mission.tiles_size_mb = round(tiles_size / 1024 / 1024, 2)
        mission.min_zoom = TILE_MIN_ZOOM
        mission.max_zoom = TILE_MAX_ZOOM

        # area + center for tile-based missions are already set at the top of
        # process_mission. Legacy missions without tile_z/x/y fall back to
        # coverage_polygon computed in Step 5.
        if not (mission.tile_z and mission.tile_x is not None and mission.tile_y is not None):
            if coverage_polygon:
                mission.area = coverage_polygon
                if bounds:
                    mission.center_lat = (bounds[1] + bounds[3]) / 2
                    mission.center_lng = (bounds[0] + bounds[2]) / 2

        # Reverse-geocode the survey location once, at publish — durable + present
        # in SSR. Cards read these stored fields; the client lookup is only a fallback.
        mission.place_label, mission.place_region = reverse_geocode_place(
            mission.center_lat, mission.center_lng)

        mission.processing_step = ''
        mission.save()
        _publish_mission_update(mission.id, {
            'status': 'PUBLISHED',
            'processing_step': '',
            'published_at': mission.published_at.isoformat(),
            'tiles_count': mission.tiles_count,
            'center_lat': mission.center_lat,
            'center_lng': mission.center_lng,
        })

        # Step 7: Cleanup skystore processing dir (images stay for mesh pipeline)
        logger.info("Step 7: Cleaning up skystore processing dir...")
        _skystore_ssh(f"sudo rm -rf {r_processing}")

        logger.info(f"Mission {mission_id} processed successfully!")
        return True

    except Exception as e:
        logger.error(f"Error processing mission {mission_id}: {e}", exc_info=True)

        # Build detailed error message with stderr context
        error_parts = [str(e)]
        if isinstance(e, subprocess.CalledProcessError):
            if e.stderr:
                error_parts.append(f"STDERR(last 500): {e.stderr[-500:]}")
            if e.stdout:
                error_parts.append(f"STDOUT(last 500): {e.stdout[-500:]}")
        error_msg = ' | '.join(error_parts)

        mission.status = OpenSkyMission.Status.FAILED
        mission.processing_step = ''
        mission.error_message = error_msg[:2000]
        mission.save(update_fields=['status', 'processing_step', 'error_message'])
        _publish_mission_update(mission.id, {
            'status': 'FAILED',
            'processing_step': '',
            'error_message': mission.error_message,
        })

        # Keep processing dir on failure for diagnostics (cleanup manually or on retry)
        logger.error(f"Processing dir preserved for diagnostics: {r_processing}")

        return False
