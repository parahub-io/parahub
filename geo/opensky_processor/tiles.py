"""
Steps 4-5 — tile pyramid and the latest/ composite layer: Web Mercator grid
math, the remote tiling scripts (TMS→XYZ WebP, coverage, size-wins update),
ownership-guarded latest/ maintenance, OpenSkyTileLayer bookkeeping, overview
recomposites, the shared reclip+retile+publish tail, and mission deletion.
"""

import logging
import shlex

from django.contrib.gis.geos import Polygon
from django.db import models

from .common import _is_superseded
from .constants import (
    SKYSTORE_3DTILES, SKYSTORE_FAST_PROCESSING, SKYSTORE_OPENSKY,
    SKYSTORE_TILES, TILE_MAX_ZOOM, TILE_MIN_ZOOM, TILE_ZOOM_OVERVIEW_MAX,
    WEBP_QUALITY,
)
from .remote import _skystore_ssh

logger = logging.getLogger(__name__)


def _z17_tile_bounds_3857(z: int, x: int, y: int, buffer_m: float = 0) -> tuple[float, float, float, float]:
    """Web Mercator tile bounds in EPSG:3857 projected meters.

    Returns (xmin, ymin, xmax, ymax). Buffer expands the box outward in
    projected meters (not ground meters — at lat 42° they differ by cos(42°)
    factor, but for buffer=0 it doesn't matter).
    """
    n = 2 ** z
    tile_size = 40075016.686 / n  # Earth circumference / tiles per row
    half_circ = 20037508.342789244
    xmin = x * tile_size - half_circ
    xmax = (x + 1) * tile_size - half_circ
    # Y axis is flipped: y=0 is north pole, y increases south
    ymax = half_circ - y * tile_size
    ymin = half_circ - (y + 1) * tile_size
    return (xmin - buffer_m, ymin - buffer_m, xmax + buffer_m, ymax + buffer_m)


def _consolidation_union_bounds_3857(members) -> tuple[float, float, float, float] | None:
    """Bounding rectangle (EPSG:3857) of all member Z17 cells.

    Because every member is a Z17 cell on the same grid, this rectangle is
    Z17-aligned for free — so the union clip emits only whole-cell tiles
    (opaque inside a member cell, empty placeholder outside), never partial
    edge tiles. That is what guarantees no holes when the super-tile overrides
    members in latest/.
    """
    boxes = [
        _z17_tile_bounds_3857(m.tile_z, m.tile_x, m.tile_y, buffer_m=0)
        for m in members
        if m.tile_z and m.tile_x is not None and m.tile_y is not None
    ]
    if not boxes:
        return None
    return (
        min(b[0] for b in boxes), min(b[1] for b in boxes),
        max(b[2] for b in boxes), max(b[3] for b in boxes),
    )


def _build_tms_to_xyz_webp_script(tms_dir: str, xyz_dir: str, quality: int) -> str:
    """Build standalone Python script for TMS→XYZ WebP conversion on skystore."""
    return f'''
import os
from PIL import Image
tms_dir = "{tms_dir}"
xyz_dir = "{xyz_dir}"
quality = {quality}
tiles_count = 0
total_size = 0
for z_str in os.listdir(tms_dir):
    z_path = os.path.join(tms_dir, z_str)
    if not os.path.isdir(z_path) or not z_str.isdigit():
        continue
    z = int(z_str)
    max_y = (2 ** z) - 1
    for x_str in os.listdir(z_path):
        x_path = os.path.join(z_path, x_str)
        if not os.path.isdir(x_path) or not x_str.isdigit():
            continue
        for tile_file in os.listdir(x_path):
            if not tile_file.endswith(".png"):
                continue
            tms_y = int(tile_file.replace(".png", ""))
            xyz_y = max_y - tms_y
            out_dir = os.path.join(xyz_dir, z_str, x_str)
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"{{xyz_y}}.webp")
            try:
                img = Image.open(os.path.join(x_path, tile_file))
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                img.save(out_path, "WEBP", quality=quality)
                total_size += os.path.getsize(out_path)
                tiles_count += 1
            except Exception:
                pass
print(f"TILES_RESULT:{{tiles_count}}:{{total_size}}")
'''


def _build_coverage_script(tiles_dir: str) -> str:
    """Build standalone Python script for coverage polygon calculation on skystore.

    Uses the MAX zoom level tiles (z19) to compute a tight bounding box around
    actually photographed area. Past bug used MIN zoom (z13) where each tile is
    ~5km, producing a 13km² polygon for a 227m × 227m flight (the parent z13
    tile is huge). At z19 each tile is ~57m, so the bbox hugs the orthophoto
    accurately (~228m for a 1×1 z17 tile mission).
    """
    return f'''
import os, json, math
tiles_dir = "{tiles_dir}"
# Find MAX zoom level — gives the tightest bbox around actual content.
# (gdal2tiles writes the full pyramid; at low zooms, one parent tile covers
# many km even if the photo is only 200m wide.)
max_z = None
for z_str in os.listdir(tiles_dir):
    z_path = os.path.join(tiles_dir, z_str)
    if not os.path.isdir(z_path) or not z_str.isdigit():
        continue
    z = int(z_str)
    if max_z is None or z > max_z:
        max_z = z
if max_z is None:
    print("COVERAGE:{{}}")
else:
    def tile2ll(x, y, z):
        n = 2 ** z
        lon = x / n * 360.0 - 180.0
        lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
        return (lon, lat)
    min_x, min_y, max_x, max_y = float("inf"), float("inf"), float("-inf"), float("-inf")
    z_path = os.path.join(tiles_dir, str(max_z))
    for x_str in os.listdir(z_path):
        x_path = os.path.join(z_path, x_str)
        if not os.path.isdir(x_path) or not x_str.isdigit(): continue
        x = int(x_str)
        for tf in os.listdir(x_path):
            if not tf.endswith(".webp"): continue
            y = int(tf.replace(".webp",""))
            if x < min_x: min_x = x
            if x > max_x: max_x = x
            if y < min_y: min_y = y
            if y > max_y: max_y = y
    sw = tile2ll(min_x, max_y + 1, max_z)
    ne = tile2ll(max_x + 1, min_y, max_z)
    poly = [sw, (ne[0], sw[1]), ne, (sw[0], ne[1]), sw]
    bounds = [sw[0], sw[1], ne[0], ne[1]]
    print("COVERAGE:" + json.dumps({{"polygon": poly, "bounds": bounds}}))
'''


def _build_update_latest_script(mission_dir: str, latest_dir: str, mission_id: str) -> str:
    """Build standalone Python script for updating latest layer on skystore.

    Policy: a mission's tile replaces the latest/ tile only if it has more
    content (larger file). Reason: gdal2tiles produces edge tiles for
    neighboring Z17 coords when the input ortho is clipped close to a tile
    boundary — those edges are effectively empty placeholders (~200 B) and
    would otherwise overwrite a neighbor's real full tile (~tens of KB) at
    the same coord. Past incident: 2026-04-08 C9/R2 missions wiped NVY's
    real tile 17/62485/48643 via this path. Size-wins is a safe "data
    preservation" heuristic — the empty placeholder is ~200 B while any
    meaningful aerial content is >1 KB.
    """
    return f'''
import os
mission_dir = "{mission_dir}"
latest_dir = "{latest_dir}"
os.makedirs(latest_dir, exist_ok=True)
count_written = 0
count_skipped = 0
for z_str in os.listdir(mission_dir):
    z_path = os.path.join(mission_dir, z_str)
    if not os.path.isdir(z_path) or not z_str.isdigit():
        continue
    for x_str in os.listdir(z_path):
        x_path = os.path.join(z_path, x_str)
        if not os.path.isdir(x_path) or not x_str.isdigit():
            continue
        out_dir = os.path.join(latest_dir, z_str, x_str)
        os.makedirs(out_dir, exist_ok=True)
        for tile_file in os.listdir(x_path):
            if not tile_file.endswith(".webp"):
                continue
            src = os.path.join(x_path, tile_file)
            dst = os.path.join(out_dir, tile_file)
            src_size = os.path.getsize(src)
            if os.path.exists(dst):
                dst_size = os.path.getsize(dst)
                if src_size <= dst_size:
                    count_skipped += 1
                    continue
                os.unlink(dst)
            try:
                os.link(src, dst)
            except OSError:
                import shutil
                shutil.copy2(src, dst)
            count_written += 1
print(f"Updated {{count_written}} tiles, skipped {{count_skipped}} smaller-than-existing")
'''


def _clear_self_owned_latest_tiles(mission_id: str, r_tiles_latest: str, r_tiles_mission: str,
                                   override_tiles_dir: str = None, min_override_size: int = 500) -> int:
    """Delete latest/ tiles owned by this mission (per OpenSkyTileLayer DB).

    Must be called BEFORE retile, while `r_tiles_mission` still exists — the
    ownership check below compares latest/ against the mission's own tiles.
    Prevents the size-wins policy in `_build_update_latest_script` from
    keeping stale latest/ links when the new ortho (post-shift) produces
    marginally smaller WebPs at the same coord — without this, latest/ gets
    stuck on pre-shift imagery while the mission dir already has the new
    shifted tiles, yielding a patchwork mosaic across neighboring missions
    at the tile level.

    A latest/ tile is deleted ONLY if it is actually this mission's tile:
    same inode (hard link) or byte-identical (copy2 fallback) with
    `missions/{id}/{z}/{x}/{y}.webp`. OpenSkyTileLayer rows alone are NOT
    proof of ownership — `_record_tile_layers` records every webp in the
    pyramid, including ~200 B edge placeholders at coords where latest/
    holds a NEIGHBOR's real tile. Past incident (2026-06-05): unconditional
    delete by DB rows let each retiled mission wipe its neighbors' real
    latest/ tiles, then `update_latest` planted the mission's empty edge
    placeholders into the freed slots (size-wins passes vs nothing) — 265
    real tiles z17-22 replaced by ~200 B placeholders across the cluster.

    Safe to call on missions without prior tiles: returns 0 if no DB rows.
    Returns number of tile coords targeted for the ownership check.
    """
    from geo.models import OpenSkyTileLayer
    owned = list(
        OpenSkyTileLayer.objects.filter(mission_id=mission_id)
        .values_list('z', 'x', 'y')
    )
    if not owned:
        return 0
    coords_str = '\n'.join(f"{z}/{x}/{y}" for z, x, y in owned)
    # Composite guard (consolidation case): when override_tiles_dir is set, only
    # clear this member's coord if the overriding mission (the consolidation) has
    # REAL content there. If the consolidation tile is an empty ~200B nodata
    # placeholder (or missing), KEEP the member tile so its coverage survives —
    # the consolidation ortho's hole is then filled by the member instead of
    # wiping it (2026-06-18 regression: joint ODM left nodata where a member had
    # full data; clearing the member + planting the empty placeholder lost
    # coverage; the alignment gate does NOT check completeness so it shipped).
    ov_setup = (
        f'override_dir = "{override_tiles_dir}"\nmin_override = {int(min_override_size)}'
        if override_tiles_dir else 'override_dir = None\nmin_override = 0'
    )
    script = f'''
import os, filecmp
latest_dir = "{r_tiles_latest}"
mission_dir = "{r_tiles_mission}"
{ov_setup}
coords = """{coords_str}""".strip().split("\\n")
deleted = 0
kept = 0
composite_filled = 0
for c in coords:
    latest_p = os.path.join(latest_dir, c + ".webp")
    mission_p = os.path.join(mission_dir, c + ".webp")
    try:
        if not os.path.exists(latest_p):
            continue
        if not os.path.exists(mission_p):
            # Cannot prove ownership (mission dir lost this coord, e.g.
            # crashed previous run) — keep; a foreign tile must survive.
            kept += 1
            continue
        if override_dir is not None:
            ov_p = os.path.join(override_dir, c + ".webp")
            if not os.path.exists(ov_p) or os.path.getsize(ov_p) <= min_override:
                # Overriding mission has no real tile here (nodata hole) — keep
                # the member tile so coverage is never lost (composite-fill).
                composite_filled += 1
                continue
        if os.path.samefile(latest_p, mission_p) or filecmp.cmp(latest_p, mission_p, shallow=False):
            os.unlink(latest_p)
            deleted += 1
        else:
            kept += 1
    except Exception:
        pass
print(f"CLEARED:{{deleted}}:KEPT:{{kept}}:COMPOSITE_FILLED:{{composite_filled}}")
'''
    composite_filled = 0
    try:
        result = _skystore_ssh(f"python3 -c {shlex.quote(script)}", timeout=600)
        for line in (result.stdout or '').strip().splitlines():
            if line.startswith('CLEARED:'):
                logger.info(f"Pre-clear for {mission_id[:8]}: {line} (of {len(owned)} owned coords)")
                parts = line.split(':')
                if len(parts) >= 6 and parts[4] == 'COMPOSITE_FILLED':
                    composite_filled = int(parts[5])
    except Exception as e:
        logger.warning(f"Failed to clear self-owned latest tiles for {mission_id}: {e}")
    return composite_filled


def fill_consolidation_holes_from_members(consolidation_id: str, min_size: int = 500) -> int:
    """Restore member coverage in latest/ at z>=17 coords where a consolidation
    left an empty (nodata-hole) placeholder tile.

    Repairs consolidations published BEFORE the composite guard (2026-06-18): the
    old publish cleared each member's tiles then planted the consolidation's tiles,
    so wherever the joint ODM ortho had a nodata hole, latest/ got a ~200B
    transparent placeholder and the member's real coverage was lost. Re-plants the
    member's real tile into any latest/ slot that is currently empty/missing,
    WITHOUT touching real content (the consolidation weld is preserved). z<=16
    overviews already alpha-composite members under the consolidation, so only
    z>=17 (size-wins hard-link) needs this. Idempotent. Returns tiles restored.
    """
    from geo.models import OpenSkyMission
    con = OpenSkyMission.objects.filter(id=consolidation_id, is_consolidation=True).first()
    if not con:
        logger.error(f"fill_holes: {consolidation_id} is not a consolidation")
        return 0
    members = [link.member for link in con.members.select_related('member').order_by('order')]
    r_latest = f"{SKYSTORE_TILES}/latest"
    total = 0
    for m in members:
        r_mem = f"{SKYSTORE_TILES}/missions/{m.id}"
        script = f'''
import os, shutil
latest_dir = "{r_latest}"
mem_dir = "{r_mem}"
min_size = {int(min_size)}
restored = 0
if os.path.isdir(mem_dir):
    for z_str in os.listdir(mem_dir):
        if not z_str.isdigit() or int(z_str) < 17:
            continue
        zp = os.path.join(mem_dir, z_str)
        if not os.path.isdir(zp):
            continue
        for x_str in os.listdir(zp):
            xp = os.path.join(zp, x_str)
            if not os.path.isdir(xp):
                continue
            for tf in os.listdir(xp):
                if not tf.endswith(".webp"):
                    continue
                src = os.path.join(xp, tf)
                try:
                    if os.path.getsize(src) <= min_size:
                        continue  # member tile is also empty here
                except OSError:
                    continue
                dst_dir = os.path.join(latest_dir, z_str, x_str)
                dst = os.path.join(dst_dir, tf)
                if os.path.exists(dst) and os.path.getsize(dst) > min_size:
                    continue  # latest already has real content — never clobber the weld
                os.makedirs(dst_dir, exist_ok=True)
                if os.path.exists(dst):
                    os.unlink(dst)
                try:
                    os.link(src, dst)
                except OSError:
                    shutil.copy2(src, dst)
                restored += 1
print(f"RESTORED:{{restored}}")
'''
        try:
            res = _skystore_ssh(f"python3 -c {shlex.quote(script)}", timeout=600)
            for line in (res.stdout or '').strip().splitlines():
                if line.startswith("RESTORED:"):
                    n = int(line.split(":")[1])
                    total += n
                    if n:
                        logger.info(f"fill_holes {consolidation_id[:8]}: member {m.id[:8]} restored {n} tiles")
        except Exception as e:
            logger.warning(f"fill_holes: member {m.id[:8]} failed: {e}")
    logger.info(f"fill_holes {consolidation_id[:8]}: total {total} tiles restored from {len(members)} member(s)")
    return total


def _build_partial_composite_script(tiles: list, missions_dir: str, latest_dir: str,
                                    min_opaque: float) -> str:
    """Build a script that pixel-composites ONLY not-fully-opaque latest tiles.

    tiles: [{'z','x','y','contributors':[mid,...]}] ordered low→high layer_order.
    For each coord: if the current latest tile is already >= min_opaque opaque,
    leave it (keep the fast hard-link); else alpha-composite the contributors
    (members under, consolidation on top) into a standalone WebP so the
    consolidation's sub-tile nodata holes are filled per-pixel by the members.
    """
    import json as _json
    tiles_json = _json.dumps(tiles)
    return f'''
import os, json
from PIL import Image
tiles = json.loads({repr(tiles_json)})
missions_dir = "{missions_dir}"
latest_dir = "{latest_dir}"
min_opaque = {float(min_opaque)}
composited = 0
for t in tiles:
    z, x, y = t["z"], t["x"], t["y"]
    dst = os.path.join(latest_dir, str(z), str(x), f"{{y}}.webp")
    if os.path.exists(dst):
        try:
            ah = Image.open(dst).convert("RGBA").getchannel("A").histogram()
            tot = sum(ah)
            if tot and (sum(ah[11:]) / tot) >= min_opaque:
                continue  # already (near-)fully opaque — keep the hard link
        except Exception:
            pass
    result = None
    for mid in t["contributors"]:
        src = os.path.join(missions_dir, mid, str(z), str(x), f"{{y}}.webp")
        if not os.path.exists(src):
            continue
        try:
            im = Image.open(src).convert("RGBA")
        except Exception:
            continue
        result = im if result is None else Image.alpha_composite(result, im)
    if result is not None:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            os.remove(dst)  # break the hard link before a standalone save
        result.save(dst, "WEBP", quality=90)
        composited += 1
print(f"PARTIAL_COMPOSITE:{{composited}}")
'''


def composite_partial_consolidation_tiles(consolidation_id: str, min_opaque: float = 0.99) -> int:
    """Pixel-composite (consolidation over members) the consolidation's z>=17
    latest/ tiles that are NOT fully opaque.

    The tile-level composite (publish guard / fill_consolidation_holes_from_members)
    only restores FULLY-empty placeholder tiles. At middle zooms (z17/z18) a tile
    is LARGER than the hole, so the consolidation tile there has real data PLUS a
    transparent sub-tile hole — size-wins/fill leave it. This composites each such
    tile from its contributors (members under, consolidation on top), filling the
    sub-tile hole per-pixel with member content. Fully-opaque tiles keep their fast
    hard link (only the few partial tiles are rewritten). Idempotent. Returns count.
    """
    from geo.models import OpenSkyMission, OpenSkyTileLayer
    con = OpenSkyMission.objects.filter(id=consolidation_id, is_consolidation=True).first()
    if not con:
        logger.error(f"composite_partial: {consolidation_id} is not a consolidation")
        return 0
    coords = list(OpenSkyTileLayer.objects.filter(
        mission_id=consolidation_id, z__gte=17
    ).values_list('z', 'x', 'y'))
    tiles = []
    for z, x, y in coords:
        contributors = list(
            OpenSkyTileLayer.objects.filter(z=z, x=x, y=y)
            .order_by('layer_order')
            .values_list('mission_id', flat=True)
        )
        if len(contributors) < 2:
            continue  # only the consolidation here — nothing to fill from
        tiles.append({'z': z, 'x': x, 'y': y, 'contributors': contributors})
    if not tiles:
        return 0
    total = 0
    BATCH = 600
    for i in range(0, len(tiles), BATCH):
        batch = tiles[i:i + BATCH]
        script = _build_partial_composite_script(
            batch, f"{SKYSTORE_TILES}/missions", f"{SKYSTORE_TILES}/latest", min_opaque)
        try:
            res = _skystore_ssh(f"python3 -c {shlex.quote(script)}", timeout=1800)
            for line in (res.stdout or '').strip().splitlines():
                if line.startswith("PARTIAL_COMPOSITE:"):
                    total += int(line.split(":")[1])
        except Exception as e:
            logger.warning(f"composite_partial {consolidation_id[:8]} batch failed: {e}")
    logger.info(
        f"composite_partial {consolidation_id[:8]}: {total} partial tile(s) pixel-composited "
        f"(of {len(tiles)} z>=17 multi-contributor coords)")
    return total


def _record_tile_layers(mission_id: str, r_tiles_mission: str):
    """Scan mission tiles on skystore and create OpenSkyTileLayer records in DB."""
    from geo.models import OpenSkyTileLayer

    result = _skystore_ssh(
        f"find {r_tiles_mission} -name '*.webp' -printf '%P\\n'",
        timeout=120,
    )
    if not result.stdout.strip():
        return

    max_order = OpenSkyTileLayer.objects.aggregate(
        max_order=models.Max('layer_order')
    )['max_order'] or 0
    new_layer_order = max_order + 1

    records = []
    for line in result.stdout.strip().splitlines():
        # Format: z/x/y.webp
        parts = line.strip().split('/')
        if len(parts) != 3 or not parts[2].endswith('.webp'):
            continue
        try:
            z, x = int(parts[0]), int(parts[1])
            y = int(parts[2].replace('.webp', ''))
            records.append(OpenSkyTileLayer(
                z=z, x=x, y=y,
                mission_id=mission_id,
                layer_order=new_layer_order,
            ))
        except (ValueError, IndexError):
            continue

    if records:
        OpenSkyTileLayer.objects.bulk_create(records, ignore_conflicts=True)
        logger.info(f"Recorded {len(records)} tile contributions for mission {mission_id[:8]}")


def _build_rebuild_tiles_script(tiles_to_rebuild: list, missions_dir: str, latest_dir: str) -> str:
    """Build standalone script for rebuilding latest/ tiles on skystore after deletion.

    tiles_to_rebuild: list of dicts {'z': int, 'x': int, 'y': int, 'remaining_missions': [str]}
    """
    import json as _json
    tiles_json = _json.dumps(tiles_to_rebuild)
    return f'''
import os, json
from PIL import Image

tiles = json.loads({repr(tiles_json)})
missions_dir = "{missions_dir}"
latest_dir = "{latest_dir}"
rebuilt = 0
deleted = 0

for t in tiles:
    z, x, y = t["z"], t["x"], t["y"]
    dst = os.path.join(latest_dir, str(z), str(x), f"{{y}}.webp")

    if not t["remaining_missions"]:
        if os.path.exists(dst):
            os.remove(dst)
            deleted += 1
        continue

    result_img = None
    for mid in t["remaining_missions"]:
        src = os.path.join(missions_dir, mid, str(z), str(x), f"{{y}}.webp")
        if not os.path.exists(src):
            continue
        tile_img = Image.open(src).convert("RGBA")
        if result_img is None:
            result_img = tile_img
        else:
            result_img = Image.alpha_composite(result_img, tile_img)

    if result_img:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        # Break any existing hard link first: latest/ tiles are hard-linked to
        # a mission's source tile (same inode), and saving in place would
        # truncate that source. Unlink → write a fresh standalone composite.
        if os.path.exists(dst):
            os.remove(dst)
        result_img.save(dst, "WEBP", quality=90)
        rebuilt += 1
    elif os.path.exists(dst):
        os.remove(dst)
        deleted += 1

print(f"REBUILD_RESULT:{{rebuilt}}:{{deleted}}")
'''


def rebuild_tiles_after_deletion(mission_id: str):
    """
    Rebuild affected tiles in latest/ on skystore after a mission is deleted.

    Queries DB for tile contributions, then runs rebuild script on skystore via SSH.
    """
    from geo.models import OpenSkyTileLayer

    # Find all tiles affected by this mission
    affected_tiles = list(OpenSkyTileLayer.objects.filter(
        mission_id=mission_id
    ).values_list('z', 'x', 'y', flat=False))

    if not affected_tiles:
        logger.info(f"No tiles to rebuild for mission {mission_id[:8]}")
        return

    logger.info(f"Rebuilding {len(affected_tiles)} tiles after deleting mission {mission_id[:8]}")

    # For each affected tile, find remaining missions (ordered by layer)
    tiles_to_rebuild = []
    for z, x, y in affected_tiles:
        remaining = list(
            OpenSkyTileLayer.objects.filter(z=z, x=x, y=y)
            .exclude(mission_id=mission_id)
            .order_by('layer_order')
            .values_list('mission_id', flat=True)
        )
        tiles_to_rebuild.append({
            'z': z, 'x': x, 'y': y,
            'remaining_missions': remaining,
        })

    # Run rebuild on skystore in batches: the script embeds every coord in ONE
    # ssh argument, and Linux caps a single argv string at MAX_ARG_STRLEN
    # (128KB) — ~17k coords blew it up during the 2026-06-09 spill recovery
    # (healed manually back then; batching is now the code path).
    REBUILD_BATCH = 600
    for i in range(0, len(tiles_to_rebuild), REBUILD_BATCH):
        batch = tiles_to_rebuild[i:i + REBUILD_BATCH]
        script = _build_rebuild_tiles_script(
            batch, f"{SKYSTORE_TILES}/missions", f"{SKYSTORE_TILES}/latest"
        )
        _skystore_ssh(f"python3 -c {shlex.quote(script)}", timeout=1800)
        if len(tiles_to_rebuild) > REBUILD_BATCH:
            logger.info(f"Rebuilt {min(i + REBUILD_BATCH, len(tiles_to_rebuild))}/{len(tiles_to_rebuild)} tiles")

    # Clean up DB records
    OpenSkyTileLayer.objects.filter(mission_id=mission_id).delete()

    logger.info(f"Tile rebuild complete for mission {mission_id[:8]}")


def rebuild_overview_latest(mission_id: str, max_overview_zoom: int = None):
    """Recomposite latest/ overview tiles (z TILE_MIN_ZOOM..TILE_ZOOM_OVERVIEW_MAX).

    gdal2tiles builds a FULL per-mission pyramid clipped to the mission's Z17
    cell, so every overview tile holds that mission's content in only its own
    sub-region (one Z16 tile spans up to 4 Z17 missions; Z15 up to 16; Z14 up
    to 64). `_build_update_latest_script` uses a size-wins hard-link, which
    keeps just ONE mission's partial overview tile and drops the rest — so the
    zoomed-out map (z<=16) shows holes even though every Z17 tile is full.

    Here each overview coord this mission touches is rebuilt as the
    alpha-composite of ALL contributing missions (ordered by layer_order, so
    newest renders on top), i.e. the true union. Transparent placeholder
    regions stay transparent (genuinely unflown sub-cells show the basemap).
    Z17+ tiles are 1 mission = 1 tile and keep their fast size-wins hard link.
    """
    from geo.models import OpenSkyTileLayer

    if max_overview_zoom is None:
        max_overview_zoom = TILE_ZOOM_OVERVIEW_MAX

    overview_coords = list(
        OpenSkyTileLayer.objects.filter(
            mission_id=mission_id, z__lte=max_overview_zoom
        ).values_list('z', 'x', 'y')
    )
    if not overview_coords:
        return

    tiles_to_rebuild = []
    for z, x, y in overview_coords:
        contributors = list(
            OpenSkyTileLayer.objects.filter(z=z, x=x, y=y)
            .order_by('layer_order')
            .values_list('mission_id', flat=True)
        )
        tiles_to_rebuild.append({
            'z': z, 'x': x, 'y': y,
            'remaining_missions': contributors,
        })

    script = _build_rebuild_tiles_script(
        tiles_to_rebuild, f"{SKYSTORE_TILES}/missions", f"{SKYSTORE_TILES}/latest"
    )
    try:
        _skystore_ssh(f"python3 -c {shlex.quote(script)}", timeout=1800)
        logger.info(
            f"Recomposited {len(tiles_to_rebuild)} overview tiles for mission {mission_id[:8]}"
        )
    except Exception as e:
        # Non-fatal: overview holes are a degradation, not a publish blocker.
        logger.warning(f"Overview recomposite failed for {mission_id[:8]}: {e}")


def _reclip_retile_publish(mission_id: str, r_ortho: str, r_tmp: str) -> int:
    """Shared tail after an in-place georef correction of the saved ortho.

    Clip r_ortho to the mission's Z17 cell, retile z11-22, plant into latest/
    (self-clear then size-wins), record tile layers, recomposite overviews,
    update coverage + DB. Used by both the consensus (translation) and the
    similarity (scale+rotation+translation) apply paths. Returns tiles_count.
    """
    from geo.models import OpenSkyMission, OpenSkyTileLayer
    r_tiles_mission = f"{SKYSTORE_TILES}/missions/{mission_id}"
    r_tiles_latest = f"{SKYSTORE_TILES}/latest"
    mission = OpenSkyMission.objects.get(id=mission_id)

    # Clip before tiling (saved ortho is intentionally unclipped; a rotated
    # geotransform from the similarity warp is de-rotated by this same warp).
    # Plain missions clip to their Z17 cell; consolidations (NULL tile coords)
    # clip to the member-cells union rectangle — tiling UNCLIPPED is what
    # caused the 2026-06-09 spill, so a consolidation without resolvable
    # bounds is an error, never a fall-through.
    r_src = r_ortho
    clip_bounds = None
    if mission.tile_z and mission.tile_x is not None and mission.tile_y is not None:
        clip_bounds = _z17_tile_bounds_3857(
            mission.tile_z, mission.tile_x, mission.tile_y, buffer_m=0
        )
    elif mission.is_consolidation:
        members = [link.member for link in mission.members.select_related('member')]
        clip_bounds = _consolidation_union_bounds_3857(members)
        if not clip_bounds:
            raise RuntimeError(
                f"Consolidation {mission_id} has no member tile bounds — refusing unclipped retile")
    if clip_bounds:
        xmin, ymin, xmax, ymax = clip_bounds
        r_clipped = f"{r_tmp}/orthophoto_clipped.tif"
        _skystore_ssh(
            f"gdalwarp -te {xmin} {ymin} {xmax} {ymax} -te_srs EPSG:3857 "
            f"-r lanczos -co COMPRESS=LZW -co TILED=YES -dstnodata 0 "
            f"-overwrite {r_ortho} {r_clipped}",
            timeout=600,
        )
        r_src = r_clipped

    r_tms = f"{r_tmp}/tiles_tms"
    _skystore_ssh(
        f"gdal2tiles.py -z {TILE_MIN_ZOOM}-{TILE_MAX_ZOOM} -w none -r lanczos"
        f" --processes=3 {r_src} {r_tms}",
        timeout=28800,
    )

    _clear_self_owned_latest_tiles(mission_id, r_tiles_latest, r_tiles_mission)
    _skystore_ssh(f"rm -rf {r_tiles_mission}")
    _skystore_ssh(f"mkdir -p {r_tiles_mission}")
    convert_script = _build_tms_to_xyz_webp_script(r_tms, r_tiles_mission, WEBP_QUALITY)
    tile_result = _skystore_ssh(f"python3 -c {shlex.quote(convert_script)}", timeout=3600)
    tiles_count = tiles_size = 0
    for line in tile_result.stdout.strip().splitlines():
        if line.startswith("TILES_RESULT:"):
            parts = line.split(":")
            tiles_count, tiles_size = int(parts[1]), int(parts[2])

    latest_script = _build_update_latest_script(r_tiles_mission, r_tiles_latest, mission_id)
    _skystore_ssh(f"python3 -c {shlex.quote(latest_script)}", timeout=600)

    OpenSkyTileLayer.objects.filter(mission_id=mission_id).delete()
    _record_tile_layers(mission_id, r_tiles_mission)
    rebuild_overview_latest(mission_id)

    coverage_script = _build_coverage_script(r_tiles_mission)
    cov_result = _skystore_ssh(f"python3 -c {shlex.quote(coverage_script)}", timeout=300)
    coverage_polygon = None
    for line in cov_result.stdout.strip().splitlines():
        if line.startswith("COVERAGE:"):
            import json as _json
            data = _json.loads(line[9:])
            if data.get('polygon'):
                coverage_polygon = Polygon(data['polygon'])
    mission.tiles_count = tiles_count
    mission.tiles_size_mb = round(tiles_size / 1024 / 1024, 2)
    if coverage_polygon:
        mission.area = coverage_polygon
    mission.save(update_fields=['tiles_count', 'tiles_size_mb', 'area'])
    return tiles_count


def retile_mission_skystore(mission_id: str, zoom_range: str = None, clean: bool = False):
    """Retile a published mission on skystore from its saved ortho.

    clean=True wipes the mission tiles dir before retiling (full rebuild).
    The wipe happens AFTER the latest/ pre-clear below — the ownership check
    in `_clear_self_owned_latest_tiles` needs the old mission tiles on disk;
    deleting the dir first (as `retile_opensky --full` used to) makes every
    owned coord unprovable, leaving orphaned latest/ links behind.
    """
    from geo.models import OpenSkyMission

    if _is_superseded(mission_id):
        return (0, 0)

    r_ortho = f"{SKYSTORE_OPENSKY}/orthos/{mission_id}.tif"
    r_tmp = f"{SKYSTORE_FAST_PROCESSING}/_retile_{mission_id}"
    r_tiles_mission = f"{SKYSTORE_TILES}/missions/{mission_id}"
    r_tiles_latest = f"{SKYSTORE_TILES}/latest"

    if not zoom_range:
        zoom_range = f"{TILE_MIN_ZOOM}-{TILE_MAX_ZOOM}"

    try:
        _skystore_ssh(f"mkdir -p {r_tmp}")

        # Mirror Step 3.7 of process_mission: clip the saved (unclipped) ortho
        # to the planned Z17 tile bounds before tiling. The /skystore/opensky/
        # orthos/ copy is intentionally unclipped (kept for cross-mission ORB
        # alignment via the 37m flight overlap), but tiling MUST run on the
        # clipped version to keep tiles confined to one Z17 cell — otherwise
        # retile would generate boundary tiles at neighbor Z17 coords and
        # break newest-wins stitching.
        mission = OpenSkyMission.objects.get(id=mission_id)
        if mission.tile_z and mission.tile_x is not None and mission.tile_y is not None:
            r_clipped = f"{r_tmp}/orthophoto_clipped.tif"
            xmin, ymin, xmax, ymax = _z17_tile_bounds_3857(
                mission.tile_z, mission.tile_x, mission.tile_y, buffer_m=0
            )
            logger.info(
                f"Retile clip: Z{mission.tile_z}/{mission.tile_x}/{mission.tile_y} "
                f"({xmin:.1f},{ymin:.1f},{xmax:.1f},{ymax:.1f} EPSG:3857)"
            )
            _skystore_ssh(
                f"gdalwarp -te {xmin} {ymin} {xmax} {ymax} -te_srs EPSG:3857 "
                f"-r lanczos -co COMPRESS=LZW -co TILED=YES -dstnodata 0 "
                f"-overwrite {r_ortho} {r_clipped}",
                timeout=600,
            )
            r_tile_source = r_clipped
        else:
            logger.warning(f"Mission {mission_id} has no tile_z/x/y — tiling unclipped ortho")
            r_tile_source = r_ortho

        # Generate TMS tiles
        r_tms = f"{r_tmp}/tiles_tms"
        _skystore_ssh(
            f"gdal2tiles.py -z {zoom_range} -w none -r lanczos"
            f" --processes=3 {r_tile_source} {r_tms}",
            timeout=28800,  # 8h
        )

        # Convert TMS→XYZ WebP
        # Clear stale latest/ tiles owned by this mission BEFORE generating
        # new tiles — else size-wins policy keeps older tiles when new ones
        # are marginally smaller (common after retile with different clip).
        _clear_self_owned_latest_tiles(mission_id, r_tiles_latest, r_tiles_mission)
        if clean:
            _skystore_ssh(f"rm -rf {r_tiles_mission}")
        _skystore_ssh(f"mkdir -p {r_tiles_mission}")
        convert_script = _build_tms_to_xyz_webp_script(r_tms, r_tiles_mission, WEBP_QUALITY)
        _skystore_ssh(f"python3 -c {shlex.quote(convert_script)}", timeout=3600)

        # Count the FULL mission pyramid, not just the zooms converted above —
        # partial retile (e.g. adding z11-12 after a TILE_MIN_ZOOM bump) would
        # otherwise persist tiles_count=2 to the DB and break mission cards.
        result = _skystore_ssh(
            f"find {r_tiles_mission} -name '*.webp' -printf '%s\\n' "
            f"| awk '{{c++; s+=$1}} END {{print \"TILES_RESULT:\" c \":\" s}}'",
            timeout=300,
        )
        tiles_count = 0
        tiles_size = 0
        for line in result.stdout.strip().splitlines():
            if line.startswith("TILES_RESULT:"):
                parts = line.split(":")
                tiles_count = int(parts[1])
                tiles_size = int(parts[2])

        # Update latest layer
        latest_script = _build_update_latest_script(r_tiles_mission, r_tiles_latest, mission_id)
        _skystore_ssh(f"python3 -c {shlex.quote(latest_script)}", timeout=600)

        # Update tile records
        from geo.models import OpenSkyTileLayer
        OpenSkyTileLayer.objects.filter(mission_id=mission_id).delete()
        _record_tile_layers(mission_id, r_tiles_mission)
        # Overview tiles (z<=16) span multiple Z17 missions; size-wins above
        # keeps only one mission's partial tile, so recomposite from all
        # contributors here (the union) — otherwise zoomed-out map has holes.
        rebuild_overview_latest(mission_id)

        return tiles_count, tiles_size

    finally:
        try:
            _skystore_ssh(f"rm -rf {r_tmp}")
        except Exception:
            pass


def delete_skystore_mission_files(mission_id: str):
    """Remove all mission data from skystore: images, ortho, tiles, mesh, 3d tiles."""
    dirs = [
        f"{SKYSTORE_OPENSKY}/missions/{mission_id}",
        f"{SKYSTORE_FAST_PROCESSING}/{mission_id}",
        f"{SKYSTORE_OPENSKY}/meshes/{mission_id}",
        f"{SKYSTORE_TILES}/missions/{mission_id}",
        f"{SKYSTORE_3DTILES}/missions/{mission_id}",
    ]
    ortho = f"{SKYSTORE_OPENSKY}/orthos/{mission_id}.tif"
    rm_cmd = " ".join(f"rm -rf {d}" for d in dirs) + f" && rm -f {ortho}"
    try:
        _skystore_ssh(rm_cmd, timeout=120)
        logger.info(f"Deleted skystore files for mission {mission_id}")
        # Regenerate root 3D Tiles tileset (mission removed).
        # Pass exclude_id because the endpoint deletes the DB row AFTER this
        # cleanup runs — without it the regenerated root would still link
        # the about-to-be-deleted child.
        try:
            from geo.tiles3d_generator import regenerate_root_tileset
            regenerate_root_tileset(exclude_id=mission_id)
        except Exception:
            pass
        # If no missions remain, clean up latest/ tiles
        from geo.models import OpenSkyMission
        remaining = OpenSkyMission.objects.exclude(id=mission_id).filter(
            status=OpenSkyMission.Status.PUBLISHED
        ).count()
        if remaining == 0:
            try:
                _skystore_ssh(f"find {SKYSTORE_TILES}/latest/ -type f -delete && "
                              f"find {SKYSTORE_TILES}/latest/ -mindepth 1 -type d -empty -delete",
                              timeout=300)
                logger.info("Last mission deleted — cleaned up latest/ tiles on skystore")
            except Exception as e:
                logger.error(f"Failed to clean up latest/ tiles: {e}")
    except Exception as e:
        logger.error(f"Failed to delete skystore files for {mission_id}: {e}")
