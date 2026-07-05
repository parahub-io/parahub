"""
Import a município PDM bundle (ordenamento + condicionantes) into PostGIS.

Source: a normalized GeoJSON-feature bundle produced by a município ETL adapter
(see the Caminha adapter run from skystore — PT egress). The adapter resolves
the SIG layer hierarchy into per-feature {classe/categoria/subcategoria} for
ordenamento and {grupo/tipo} for condicionantes, and converts source geometry
to GeoJSON. This command is source-agnostic: it just loads the bundle.

The whole (municipio, source) is reloaded on each run (version-stamped reference
data), so there is no per-row upsert — same pattern as import_drone_zones.

Bundle shape:
    {
      "meta": {"municipio","source","source_version","fetched_at"},
      "ordenamento":   [{"service_layer","classe","categoria","subcategoria",
                         "attributes","geometry"(GeoJSON)}, ...],
      "condicionantes":[{"service_layer","grupo","tipo","attributes",
                         "geometry"(GeoJSON)}, ...],
    }

Usage:
    python3 manage.py import_urban_pdm --bundle /path/to/bundle.json
    python3 manage.py import_urban_pdm --bundle ... --dry-run
"""

import json

from django.contrib.gis.geos import GEOSGeometry
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from geo.models import UrbanOrdenamento, UrbanCondicionante

POLYGONAL = ("Polygon", "MultiPolygon")


def _build_geom(gj):
    """GeoJSON dict → SRID-4326 GEOSGeometry, repairing invalid polygons.

    Returns (geom, note) where note is a non-fatal warning string or "".
    Raises ValueError if the geometry is unusable.
    """
    geom = GEOSGeometry(json.dumps(gj), srid=4326)
    if geom.empty:
        raise ValueError("empty geometry")
    if geom.geom_type in POLYGONAL and not geom.valid:
        fixed = geom.buffer(0)  # canonical GEOS self-intersection repair
        if fixed.empty or fixed.geom_type not in POLYGONAL:
            raise ValueError(f"invalid polygon, buffer(0) → {fixed.geom_type or 'empty'}")
        return fixed, "repaired(buffer0)"
    return geom, ""


class Command(BaseCommand):
    help = "Import a município PDM bundle (ordenamento + condicionantes) into PostGIS"

    def add_arguments(self, parser):
        parser.add_argument("--bundle", required=True, help="Path to the PDM bundle JSON")
        parser.add_argument("--dry-run", action="store_true", help="Parse and report; write nothing")

    def handle(self, *args, **opts):
        with open(opts["bundle"], "r", encoding="utf-8") as fh:
            bundle = json.load(fh)

        meta = bundle.get("meta") or {}
        municipio = meta.get("municipio")
        source = meta.get("source")
        version = meta.get("source_version", "") or ""
        if not municipio or not source:
            raise CommandError("bundle.meta must carry 'municipio' and 'source'")

        self.stdout.write(
            f"Bundle: municipio={municipio} source={source} version={version} "
            f"fetched={meta.get('fetched_at')}"
        )
        self.stdout.write(
            f"  ordenamento={len(bundle.get('ordenamento', []))} "
            f"condicionantes={len(bundle.get('condicionantes', []))}"
        )

        now = timezone.now()
        ord_rows, cnd_rows, skipped, repaired = [], [], [], 0

        for f in bundle.get("ordenamento", []):
            try:
                geom, note = _build_geom(f["geometry"])
            except (ValueError, KeyError, TypeError) as e:
                skipped.append((f.get("service_layer", "?"), str(e)))
                continue
            if note:
                repaired += 1
            ord_rows.append(UrbanOrdenamento(
                municipio=municipio, source=source, source_version=version,
                service_layer=f.get("service_layer", ""),
                classe=f.get("classe", ""), categoria=f.get("categoria", ""),
                subcategoria=f.get("subcategoria", ""),
                attributes=f.get("attributes", {}) or {},
                geometry=geom, ingested_at=now,
            ))

        for f in bundle.get("condicionantes", []):
            try:
                geom, note = _build_geom(f["geometry"])
            except (ValueError, KeyError, TypeError) as e:
                skipped.append((f.get("service_layer", "?"), str(e)))
                continue
            if note:
                repaired += 1
            cnd_rows.append(UrbanCondicionante(
                municipio=municipio, source=source, source_version=version,
                service_layer=f.get("service_layer", ""),
                grupo=f.get("grupo", ""), tipo=f.get("tipo", ""),
                attributes=f.get("attributes", {}) or {},
                geometry=geom, ingested_at=now,
            ))

        self.stdout.write(
            f"Prepared ordenamento={len(ord_rows)} condicionantes={len(cnd_rows)} "
            f"(repaired {repaired}, skipped {len(skipped)})"
        )
        for layer, err in skipped[:20]:
            self.stdout.write(self.style.WARNING(f"  skip {layer}: {err}"))

        if opts["dry_run"]:
            self.stdout.write(self.style.SUCCESS("Dry run: no changes written."))
            return

        with transaction.atomic():
            d_ord, _ = UrbanOrdenamento.objects.filter(municipio=municipio, source=source).delete()
            d_cnd, _ = UrbanCondicionante.objects.filter(municipio=municipio, source=source).delete()
            UrbanOrdenamento.objects.bulk_create(ord_rows, batch_size=200)
            UrbanCondicionante.objects.bulk_create(cnd_rows, batch_size=200)

        self.stdout.write(self.style.SUCCESS(
            f"Replaced {municipio}/{source}: ordenamento {d_ord}→{len(ord_rows)}, "
            f"condicionantes {d_cnd}→{len(cnd_rows)} (version {version})."
        ))
