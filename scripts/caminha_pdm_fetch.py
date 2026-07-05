#!/usr/bin/env python3
"""
Caminha PDM ETL adapter (runs on skystore — needs PT egress).

Pulls the Planta de Ordenamento (land-use qualification) and Planta de
Condicionantes (servidões/restrições) from the Caminha MuniSIG (Geocortex
Essentials) anonymous proxy and writes one self-contained GeoJSON-feature
bundle for the Django loader on prod to ingest.

Quirks handled:
- The anonymous proxy refuses f=geojson ("Format geojson is not supported")
  and returns it as HTTP 200 with an {"error":...} body, so we request
  f=json (Esri JSON) and convert Esri→GeoJSON here, and we raise on any
  {"error"} body (never silently truncate).
- Esri polygon `rings` are a flat list (outer + holes by winding); we group
  them into proper GeoJSON Polygon/MultiPolygon. Condicionantes geometry is
  mixed (polygon/polyline/point), all converted.
- Paginates by maxRecordCount via resultOffset (supportsPagination=True).

Semantics:
- Ordenamento: only SOLO RÚSTICO / SOLO URBANO leaf layers; classe/categ/
  subcateg come from feature fields.
- Condicionantes: all leaf layers; tipo = layer name, grupo = top ancestor
  (attribute tables are CAD noise and carry no usable type field).

Usage (the SIG is geoblocked to PT, so fetch from skystore, then load on prod):
    scp scripts/caminha_pdm_fetch.py deploy@<SKYSTORE_IP>:/tmp/
    ssh deploy@<SKYSTORE_IP> 'python3 /tmp/caminha_pdm_fetch.py "munisig-YYYY-MM-DD"' > bundle.json
    # transfer bundle.json to prod, then:
    python3 manage.py import_urban_pdm --bundle bundle.json
See PK/urban-analysis-system.md § Data Pipeline.
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = ("https://sig.cm-caminha.pt/MuniSIG/REST/sites/"
        "01_Plano_Diretor_Municipal/map/mapservices")
MUNICIPIO = "caminha"
SOURCE = "caminha_munisig"
SVC_ORDENAMENTO = 1
SVC_CONDICIONANTES = 4
ORDENAMENTO_GROUPS = {"SOLO RÚSTICO", "SOLO URBANO"}


def get(url):
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "parahub-etl/1.0"})
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.load(r)
            if isinstance(d, dict) and d.get("error"):
                # Geocortex wraps auth/format errors in HTTP 200 — fail loudly.
                raise RuntimeError(f"service error: {d['error'].get('message')}")
            return d
        except Exception as e:  # noqa: BLE001 — transient network, retry
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"GET failed after retries: {url} :: {last}")


def mapserver_meta(svc):
    return get(f"{BASE}/{svc}/rest/services/x/MapServer?f=json")


def top_ancestor_name(idx, lid):
    cur = idx[lid]
    name = cur["name"]
    while cur.get("parentLayerId", -1) not in (-1, None):
        cur = idx[cur["parentLayerId"]]
        name = cur["name"]
    return name


def is_leaf(layer):
    return not layer.get("subLayerIds")


# ---------- Esri JSON → GeoJSON ----------

def _ring_is_clockwise(ring):
    total = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[i + 1][0], ring[i + 1][1]
        total += (x2 - x1) * (y2 + y1)
    return total > 0  # Esri convention: outer rings are clockwise


def _point_in_ring(pt, ring):
    x, y = pt[0], pt[1]
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-30) + xi):
            inside = not inside
        j = i
    return inside


def _close(ring):
    return ring + [ring[0]] if ring and ring[0] != ring[-1] else ring


def _esri_polygon(rings):
    rings = [_close([[float(p[0]), float(p[1])] for p in r]) for r in rings if len(r) >= 4]
    if not rings:
        return None
    outers = [r for r in rings if _ring_is_clockwise(r)]
    holes = [r for r in rings if not _ring_is_clockwise(r)]
    if not outers:  # degenerate: all CCW — treat each as outer
        outers, holes = [r[::-1] for r in rings], []
    polys = [[o] for o in outers]
    for h in holes:
        placed = False
        for poly in polys:
            if _point_in_ring(h[0], poly[0]):
                poly.append(h)
                placed = True
                break
        if not placed:
            polys.append([h[::-1]])  # orphan hole → its own outer
    if len(polys) == 1:
        return {"type": "Polygon", "coordinates": polys[0]}
    return {"type": "MultiPolygon", "coordinates": polys}


def esri_to_geojson(geom, gtype):
    if not geom:
        return None
    if gtype == "esriGeometryPolygon" and geom.get("rings"):
        return _esri_polygon(geom["rings"])
    if gtype == "esriGeometryPolyline" and geom.get("paths"):
        paths = [[[float(p[0]), float(p[1])] for p in path]
                 for path in geom["paths"] if len(path) >= 2]
        if not paths:
            return None
        return ({"type": "LineString", "coordinates": paths[0]} if len(paths) == 1
                else {"type": "MultiLineString", "coordinates": paths})
    if gtype == "esriGeometryPoint" and geom.get("x") is not None:
        return {"type": "Point", "coordinates": [float(geom["x"]), float(geom["y"])]}
    if gtype == "esriGeometryMultipoint" and geom.get("points"):
        pts = [[float(p[0]), float(p[1])] for p in geom["points"]]
        return {"type": "MultiPoint", "coordinates": pts} if pts else None
    return None


def query_layer(svc, lid, out_fields, max_records):
    """Page through a layer in Esri JSON; return (geometryType, [features])."""
    feats = []
    gtype = None
    offset = 0
    page = max(1, max_records)
    while True:
        params = {
            "where": "1=1", "outFields": out_fields, "returnGeometry": "true",
            "outSR": "4326", "f": "json",
            "resultOffset": offset, "resultRecordCount": page,
        }
        url = (f"{BASE}/{svc}/rest/services/x/MapServer/{lid}/query?"
               + urllib.parse.urlencode(params))
        d = get(url)
        gtype = d.get("geometryType") or gtype
        fs = d.get("features", []) or []
        feats.extend(fs)
        if len(fs) < page:
            break
        offset += page
        if offset > 500000:
            sys.stderr.write(f"  WARN layer {lid}: >500k feats, stopping\n")
            break
    return gtype, feats


def clean_ordenamento_attrs(a):
    out = {}
    for k in ("classe", "categ", "subcateg", "area_ha", "outros"):
        v = a.get(k)
        if v not in (None, "", " "):
            out[k] = v
    return out


def main():
    fetched_at = datetime.now(timezone.utc).isoformat()
    source_version = sys.argv[1] if len(sys.argv) > 1 else fetched_at[:10]
    bundle = {
        "meta": {"municipio": MUNICIPIO, "source": SOURCE,
                 "source_version": source_version, "fetched_at": fetched_at, "base": BASE},
        "ordenamento": [], "condicionantes": [],
    }
    dropped = 0

    # ---- ORDENAMENTO ----
    meta = mapserver_meta(SVC_ORDENAMENTO)
    max_rec = int(meta.get("maxRecordCount") or 1000)
    idx = {L["id"]: L for L in meta.get("layers", [])}
    sys.stderr.write(f"ORDENAMENTO maxRecordCount={max_rec}\n")
    for L in meta.get("layers", []):
        if not is_leaf(L) or top_ancestor_name(idx, L["id"]) not in ORDENAMENTO_GROUPS:
            continue
        lid = L["id"]
        gtype, feats = query_layer(SVC_ORDENAMENTO, lid, "*", max_rec)
        sys.stderr.write(f"  ORD {lid} {L['name']!r}: {len(feats)} feats ({gtype})\n")
        for f in feats:
            gj = esri_to_geojson(f.get("geometry"), gtype)
            if gj is None:
                dropped += 1
                continue
            a = f.get("attributes", {}) or {}
            bundle["ordenamento"].append({
                "service_layer": f"ORDENAMENTO/{lid}",
                "classe": (a.get("classe") or "").strip(),
                "categoria": (a.get("categ") or "").strip(),
                "subcategoria": (a.get("subcateg") or "").strip(),
                "attributes": clean_ordenamento_attrs(a),
                "geometry": gj,
            })

    # ---- CONDICIONANTES ----
    meta = mapserver_meta(SVC_CONDICIONANTES)
    max_rec = int(meta.get("maxRecordCount") or 1000)
    idx = {L["id"]: L for L in meta.get("layers", [])}
    sys.stderr.write(f"CONDICIONANTES maxRecordCount={max_rec}\n")
    for L in meta.get("layers", []):
        if not is_leaf(L):
            continue
        lid = L["id"]
        grupo, tipo = top_ancestor_name(idx, lid), L["name"]
        gtype, feats = query_layer(SVC_CONDICIONANTES, lid, "objectid", max_rec)
        sys.stderr.write(f"  CND {lid} {tipo!r} [{grupo}]: {len(feats)} feats ({gtype})\n")
        for f in feats:
            gj = esri_to_geojson(f.get("geometry"), gtype)
            if gj is None:
                dropped += 1
                continue
            bundle["condicionantes"].append({
                "service_layer": f"CONDICIONANTES/{lid}",
                "grupo": grupo.strip(), "tipo": tipo.strip(),
                "attributes": {}, "geometry": gj,
            })

    json.dump(bundle, sys.stdout)
    sys.stderr.write(
        f"DONE ordenamento={len(bundle['ordenamento'])} "
        f"condicionantes={len(bundle['condicionantes'])} dropped_no_geom={dropped}\n")


if __name__ == "__main__":
    main()
