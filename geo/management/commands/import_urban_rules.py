"""
Import a município's curated edificability rules (L2) into UrbanRule.

Source: a hand-curated JSON of rules transcribed from the consolidated PDM
regulamento (see geo/data/urban_rules_caminha.json). Each rule carries the
parameters the regulamento fixes for a (categoria, subcategoria) plus its
artigo; the diploma is shared in meta. Reloaded wholesale per (municipio,
source) — same version-stamped pattern as import_urban_pdm / import_drone_zones.

This is reference data an urbanista can audit (Gate-L2 / ТЗ §5.4): the JSON is
the reviewable source of truth, this command just loads it.

Usage:
    python3 manage.py import_urban_rules --file geo/data/urban_rules_caminha.json
    python3 manage.py import_urban_rules --file ... --dry-run
"""

import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from geo.models import UrbanRule


class Command(BaseCommand):
    help = "Import curated PDM edificability rules (L2) into UrbanRule"

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to the curated rules JSON")
        parser.add_argument("--dry-run", action="store_true", help="Parse and report; write nothing")

    def handle(self, *args, **opts):
        with open(opts["file"], "r", encoding="utf-8") as fh:
            doc = json.load(fh)

        meta = doc.get("meta") or {}
        municipio = meta.get("municipio")
        source = meta.get("source")
        version = meta.get("source_version", "") or ""
        diploma = meta.get("diploma", "") or ""
        if not municipio or not source:
            raise CommandError("meta must carry 'municipio' and 'source'")

        rules_in = doc.get("rules", [])
        self.stdout.write(
            f"Rules bundle: municipio={municipio} source={source} version={version} "
            f"count={len(rules_in)}"
        )

        now = timezone.now()
        rows = []
        for r in rules_in:
            if not r.get("categoria"):
                raise CommandError(f"rule missing 'categoria': {r}")
            regime = r.get("uso_default_regime") or ""
            if regime not in ("", "condicionado", "interdito"):
                raise CommandError(
                    f"invalid uso_default_regime '{regime}' for {r['categoria']}: "
                    "must be 'condicionado', 'interdito' or absent (= not curated)")
            rows.append(UrbanRule(
                municipio=municipio, source=source, source_version=version,
                categoria=r["categoria"], subcategoria=r.get("subcategoria", ""),
                diploma=diploma, artigo=r.get("artigo", ""),
                indice_utilizacao=r.get("indice_utilizacao"),
                indice_utilizacao_max=bool(r.get("indice_utilizacao_max", True)),
                indice_impermeabilizacao_pct=r.get("indice_impermeabilizacao_pct"),
                num_pisos_max=r.get("num_pisos_max"),
                cercea_max_m=r.get("cercea_max_m"),
                edificavel=bool(r.get("edificavel", True)),
                usos_dominantes=r.get("usos_dominantes") or [],
                uso_default_regime=regime,
                artigo_usos=r.get("artigo_usos", "") or "",
                source_quote=r.get("source_quote", "") or "",
                notes=r.get("notes", "") or "",
                ingested_at=now,
            ))

        for row in rows:
            self.stdout.write(
                f"  art {row.artigo:<7} {row.categoria} / {row.subcategoria}: "
                f"util={row.indice_utilizacao} imperm={row.indice_impermeabilizacao_pct}% "
                f"pisos={row.num_pisos_max} edif={row.edificavel}"
            )

        if opts["dry_run"]:
            self.stdout.write(self.style.SUCCESS("Dry run: no changes written."))
            return

        with transaction.atomic():
            deleted, _ = UrbanRule.objects.filter(municipio=municipio, source=source).delete()
            UrbanRule.objects.bulk_create(rows, batch_size=200)
        self.stdout.write(self.style.SUCCESS(
            f"Replaced {municipio}/{source}: rules {deleted}→{len(rows)} (version {version})."
        ))
