"""
Urban analysis — entry point of the automated urbanistic-analysis platform
(Portugal: per-município PDM-based viability/zoning assessment from a plot
geometry).

L1 — Territorial framing. From a plot polygon, intersect the ingested PDM layers
in PostGIS and report:
  - ordenamento: classe / categoria / subcategoria do solo covering the plot
    (with the % of the plot in each — a plot may straddle a zoning boundary),
  - condicionantes: servidões / restrições (REN, RAN, domínio hídrico, Rede
    Natura, património, infra-estruturas…) the plot intersects.
Every row carries its provenance (source portal + version + service layer) so
the answer is traceable to the SIG it came from.

Core invariant (PK/.todo urban ТЗ §2): the system never invents. Outside the
ingested coverage it says so; it does NOT guess a qualification. L1 does not yet
validate the intended `use_type` against the regulamento (that is L2/L3, which
needs the rules engine) — the field is accepted and echoed, never adjudicated.

The deterministic rules-engine (índices, área máxima, implantação, cércea…) and
legal-engine (applicable artigos) are layered on this L1 contract later.
"""

import logging

from django.contrib.gis.db.models.functions import Area, PointOnSurface, Transform
from django.contrib.gis.geos import GEOSException, Polygon
from django.db.models import CharField, Func
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from geo.models import UrbanCondicionante, UrbanOrdenamento, UrbanRule, UrbanRuleSignoff
from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip

logger = logging.getLogger(__name__)

router = Router(tags=["Geo / Urban"])

# Official metric CRS for continental Portugal (ETRS89 / PT-TM06) — the CRS PDM
# vector deposits are mandated in (RJIGT art. 193). Valid on the continent only:
# resolve the CRS per plot via metric_srid_for(), never apply this constant to
# geometry that may lie elsewhere (Azores/Madeira, or another jurisdiction
# reusing this engine). Intersection topology itself is computed in 4326 where
# degrees are exact; only areas need a metric CRS.
PT_TM06_SRID = 3763

# Continental-Portugal bounding box (lon/lat) — the validity area of PT-TM06.
_PT_CONTINENT_BBOX = (-9.6, 36.8, -6.1, 42.2)


def metric_srid_for(geom) -> int:
    """Metric SRID for computing real-m² areas of a SRID-4326 geometry.

    Continental Portugal → EPSG:3763 (the official PT-TM06). Everywhere else —
    the archipelagos (PT-TM06 applied ~1500 km off-shore would distort areas)
    and any other jurisdiction reusing this engine — the WGS84/UTM zone of the
    centroid, so areas stay accurate with zero per-country configuration.
    """
    c = geom.centroid
    lon, lat = c.x, c.y
    if (_PT_CONTINENT_BBOX[0] <= lon <= _PT_CONTINENT_BBOX[2]
            and _PT_CONTINENT_BBOX[1] <= lat <= _PT_CONTINENT_BBOX[3]):
        return PT_TM06_SRID
    zone = min(60, max(1, int((lon + 180.0) // 6) + 1))
    return (32600 if lat >= 0 else 32700) + zone

# Intended building / land-use types, grounded in the Portuguese PDM vocabulary
# ("categorias de uso do solo" / quadro de usos of a regulamento do Plano Diretor
# Municipal). Stored as English slugs; the UI localizes via map.urban.types.*.
# Informed placeholder — real per-município categorias/usos get extracted from the
# PDM regulamento and validated with a licensed urbanista when the rules engine
# lands. NOT verbatim from a specific regulamento; do not treat as authoritative.
URBAN_USE_TYPES = {
    "residential",   # Habitação
    "commercial",    # Comércio
    "services",      # Serviços
    "industrial",    # Indústria
    "warehouse",     # Armazenagem / Logística
    "tourism",       # Turismo
    "facility",      # Equipamento de utilização coletiva
    "agricultural",  # Agrícola
    "livestock",     # Pecuária / Agropecuária
    "forestry",      # Florestal
    "mixed",         # Uso misto
}


class UrbanAnalyzeRequest(Schema):
    # Plot boundary as [[lng, lat], ...] — an open ring with >= 3 vertices, in the
    # GeoJSON axis order the map draw tool emits.
    polygon: list[list[float]]
    use_type: str


def _geom_kind(geom_type: str) -> str:
    """Coarse geometry class for display: area | line | point.

    Accepts both GEOS spellings ('Polygon') and PostGIS GeometryType() output
    ('POLYGON' / 'MULTIPOLYGON' / 'LINESTRING' …)."""
    t = (geom_type or "").upper()
    if "POLY" in t:
        return "area"
    if "LINE" in t:
        return "line"
    return "point"


def _build_plot(poly: list[list[float]]) -> Polygon:
    """Validate the raw ring and build a closed SRID-4326 GEOS Polygon."""
    if len(poly) < 3:
        raise HttpError(400, "Polygon must have at least 3 vertices")
    ring = []
    for vertex in poly:
        if len(vertex) != 2:
            raise HttpError(400, "Each vertex must be [lng, lat]")
        lng, lat = vertex[0], vertex[1]
        if not (-180 <= lng <= 180) or not (-90 <= lat <= 90):
            raise HttpError(400, "Vertex coordinates out of range")
        ring.append((float(lng), float(lat)))
    if ring[0] != ring[-1]:
        ring.append(ring[0])  # close the ring
    try:
        plot = Polygon(ring, srid=4326)
        if not plot.valid:
            plot = plot.buffer(0)
        if plot.empty or plot.geom_type not in ("Polygon", "MultiPolygon"):
            raise HttpError(400, "Degenerate polygon")
    except (GEOSException, ValueError, TypeError):
        raise HttpError(400, "Invalid polygon geometry")
    return plot


def _adjudicate_use(dom_rule, use_type):
    """Regime of the chosen `use_type` against the dominant qualification's quadro
    de usos: permitido (a dominant use of the espaço) | for a non-listed use, the
    rule's curated `uso_default_regime` — regulamentos differ («outros usos, desde
    que compatíveis» → condicionado; «são interditos os usos não previstos» →
    interdito) | interdito (the zone itself is non-edificável) | None (quadro de
    usos or default regime not curated → don't adjudicate). The non-listed regime
    is data, never a code-level assumption (invariant 1)."""
    if dom_rule is None:
        return None
    if dom_rule.get("edificavel") is False:
        return "interdito"
    usos = dom_rule.get("usos_dominantes")
    if not usos:
        return None
    if use_type in usos:
        return "permitido"
    return dom_rule.get("uso_default_regime") or None


def _compute_viability(ordenamento, condicionantes, uncovered_pct, use_type):
    """L3 viability synthesis — a justified Sim / Condicionado / Não verdict.

    Built from the curated edificabilidade flag of the *dominant* qualification
    (highest coverage), the chosen use_type's regime against its quadro de usos,
    the condicionantes that bite, and any straddled non-edificável part. Output is
    an automatic indication, never a parecer (invariant 4); the panel labels it
    *não constitui parecer*.

    Verdicts: edificavel | condicionado | nao_edificavel | sem_dados (L1-only).
    Confidence (grau de confiança): alta | media | baixa.
    """
    dominant = ordenamento[0] if ordenamento else None
    dom_rule = dominant.get("rule") if dominant else None
    any_non_edificavel = any(
        o.get("rule") and o["rule"].get("edificavel") is False for o in ordenamento)
    use_regime = _adjudicate_use(dom_rule, use_type)
    reasons = []
    # No curated rule for the dominant qualification (e.g. solo rústico) → L1 only.
    if dom_rule is None:
        return {"verdict": "sem_dados", "confidence": "baixa", "reasons": reasons,
                "use_regime": None}
    # The land itself is non-edificável (artigo-cited) — solid regardless of use.
    if dom_rule.get("edificavel") is False:
        reasons.append({"code": "regime_restrito", "artigo": dom_rule.get("artigo")})
        return {"verdict": "nao_edificavel", "confidence": "alta", "reasons": reasons,
                "use_regime": use_regime}
    artigo_usos = dom_rule.get("artigo_usos") or dom_rule.get("artigo")
    # The chosen use is interdito by the espaço's curated quadro-de-usos default
    # («são interditos os usos não previstos») — a Não for this use, artigo-cited,
    # even though the land itself is edificável for the listed uses.
    if use_regime == "interdito":
        reasons.append({"code": "uso_interdito", "use_type": use_type, "artigo": artigo_usos})
        return {"verdict": "nao_edificavel", "confidence": "alta", "reasons": reasons,
                "use_regime": use_regime}
    # Dominant is edificável. Lead with the use regime (the user's question), then
    # let edificability constraints downgrade the verdict.
    verdict = "edificavel"
    if use_regime == "permitido":
        reasons.append({"code": "uso_permitido", "use_type": use_type, "artigo": artigo_usos})
    elif use_regime == "condicionado":
        verdict = "condicionado"
        reasons.append({"code": "uso_condicionado", "use_type": use_type, "artigo": artigo_usos})
    elif use_regime is None:
        reasons.append({"code": "uso_nao_adjudicado", "use_type": use_type})
    if any_non_edificavel:
        verdict = "condicionado"
        reasons.append({"code": "parte_nao_edificavel"})
    if condicionantes:
        verdict = "condicionado"
        reasons.append({"code": "condicionante", "count": len(condicionantes)})
    if verdict == "edificavel":
        reasons.append({"code": "edificavel_parametros", "artigo": dom_rule.get("artigo")})
    # Humble by default: Gate-L2 pending → never "alta" for an edificável verdict.
    confidence = "baixa" if uncovered_pct >= 10 else "media"
    return {"verdict": verdict, "confidence": confidence, "reasons": reasons,
            "use_regime": use_regime}


def run_urban_analysis(plot: Polygon, use_type: str) -> dict:
    """Core L1–L3 analysis for a validated SRID-4326 plot polygon and use_type.

    Pure — no request / auth / HTTP. The API view (`urban_analyze`) and the
    offline validation dossiê (`urban_validation` command) both call this, so
    they exercise the identical code path: the validation a licensed urbanista
    signs off reflects exactly what production computes, never a re-implementation.

    Returns the covered=False shape outside ingested coverage (never a guess),
    else the full L1/L2 + viability dict.
    """
    # Metric area of the plot (m²) for coverage fractions, in the plot's own
    # metric CRS (PT continent → PT-TM06, else the centroid's UTM zone).
    metric_srid = metric_srid_for(plot)
    plot_m = plot.clone()
    plot_m.transform(metric_srid)
    plot_area = plot_m.area or 0.0

    # ---- Ordenamento (classe/categoria do solo), with plot-coverage % ----
    # A single qualification can be split across several polygons; aggregate by
    # (classe, categoria, subcategoria) and sum each one's share of the plot.
    agg = {}
    covered_area = 0.0
    src = None
    for o in UrbanOrdenamento.objects.filter(geometry__intersects=plot):
        inter_area, computed = 0.0, False
        try:
            g = o.geometry.clone()
            g.transform(metric_srid)
            inter_area = g.intersection(plot_m).area
            computed = True
            covered_area += inter_area
        except (GEOSException, ValueError):
            pass
        key = (o.classe, o.categoria, o.subcategoria)
        entry = agg.get(key)
        if entry is None:
            entry = agg[key] = {
                "classe": o.classe, "categoria": o.categoria,
                "subcategoria": o.subcategoria,
                "_area": 0.0, "_computed": False, "_layers": [],
            }
        entry["_area"] += inter_area
        entry["_computed"] = entry["_computed"] or computed
        if o.service_layer and o.service_layer not in entry["_layers"]:
            entry["_layers"].append(o.service_layer)
        if src is None:
            src = (o.municipio, o.source, o.source_version, o.ingested_at)

    ordenamento = [{
        "classe": e["classe"], "categoria": e["categoria"], "subcategoria": e["subcategoria"],
        "coverage_pct": round(e["_area"] / plot_area * 100, 1) if (plot_area and e["_computed"]) else None,
        "service_layer": ", ".join(e["_layers"]),
    } for e in agg.values()]
    ordenamento.sort(key=lambda r: (r["coverage_pct"] is None, -(r["coverage_pct"] or 0)))

    covered = bool(ordenamento)
    if not covered:
        # Outside ingested coverage — say so, never guess a qualification (§2).
        municipios = sorted(
            UrbanOrdenamento.objects.values_list("municipio", flat=True).distinct()
        )
        return {
            "covered": False,
            "municipio": None,
            "ordenamento": [],
            "condicionantes": [],
            "plot_area_m2": round(plot_area, 1),
            "uncovered_pct": 100.0,
            "use_type": use_type,
            "use_type_checked": False,
            "level": "L1",
            "source": None,
            "available_municipios": municipios,
        }

    # ---- Condicionantes (servidões / restrições), deduped by type ----
    # Read only labels + the geometry's type from the DB (GeometryType): never
    # pull the heavy geometries (e.g. the whole-município REN) into Python.
    condicionantes = {}
    cond_rows = (
        UrbanCondicionante.objects
        .filter(geometry__intersects=plot)
        .annotate(gtype=Func("geometry", function="GeometryType", output_field=CharField()))
        .values("grupo", "tipo", "service_layer", "gtype")
    )
    for c in cond_rows:
        key = c["service_layer"] or f"{c['grupo']}|{c['tipo']}"
        entry = condicionantes.get(key)
        if entry:
            entry["features"] += 1
        else:
            condicionantes[key] = {
                "grupo": c["grupo"],
                "tipo": c["tipo"],
                "kind": _geom_kind(c["gtype"]),
                "features": 1,
                "service_layer": c["service_layer"],
            }
    condicionantes = sorted(condicionantes.values(), key=lambda r: (r["grupo"], r["tipo"]))

    municipio, source_portal, source_version, ingested_at = src
    uncovered_pct = round(max(0.0, 100.0 - (covered_area / plot_area * 100)), 1) if plot_area else 0.0

    # ---- L2: edificability parameters per qualification (curated rules) ----
    # Attach the regulamento parameters (índices, pisos, cércea + artigo) to each
    # ordenamento hit and compute, for that part of the plot:
    #   área máxima de construção = índice de utilização       × área do solo
    #   área máxima impermeável   = índice de impermeabilização × área do solo
    # Numbers come from the rules table only (invariant §2.4) — never computed
    # when the category fixes no índice (e.g. Espaços centrais → no IU, not a guess).
    rules = {
        (r.categoria, r.subcategoria): r
        for r in UrbanRule.objects.filter(municipio=municipio)
    }
    diploma = None
    area_max_total = 0.0
    area_imperm_total = 0.0
    area_computed = False
    imperm_computed = False
    for o in ordenamento:
        r = rules.get((o["categoria"], o["subcategoria"]))
        if r is None:
            o["rule"] = None
            continue
        diploma = diploma or (r.diploma or None)
        # Plot area (m²) inside this qualification — the base for both the buildable
        # (índice util) and the impermeable (índice imperm) maxima.
        area_in_categoria = (
            plot_area * o["coverage_pct"] / 100.0
            if o["coverage_pct"] is not None and plot_area else None)
        area_max = None
        if r.indice_utilizacao is not None and area_in_categoria is not None:
            area_max = round(float(r.indice_utilizacao) * area_in_categoria, 1)
            area_max_total += area_max
            area_computed = True
        if r.indice_impermeabilizacao_pct is not None and area_in_categoria is not None:
            area_imperm_total += float(r.indice_impermeabilizacao_pct) / 100.0 * area_in_categoria
            imperm_computed = True
        o["rule"] = {
            "artigo": r.artigo,
            "indice_utilizacao": float(r.indice_utilizacao) if r.indice_utilizacao is not None else None,
            "indice_utilizacao_max": r.indice_utilizacao_max,
            "indice_impermeabilizacao_pct": (
                float(r.indice_impermeabilizacao_pct) if r.indice_impermeabilizacao_pct is not None else None),
            "num_pisos_max": r.num_pisos_max,
            "cercea_max_m": float(r.cercea_max_m) if r.cercea_max_m is not None else None,
            "edificavel": r.edificavel,
            "usos_dominantes": r.usos_dominantes or [],
            "uso_default_regime": r.uso_default_regime or None,
            "artigo_usos": r.artigo_usos,
            "source_quote": r.source_quote,
            "notes": r.notes,
            "area_max_construcao_m2": area_max,
        }
    level = "L2" if diploma is not None else "L1"
    viability = _compute_viability(ordenamento, condicionantes, uncovered_pct, use_type)

    return {
        "covered": True,
        "municipio": municipio,
        "ordenamento": ordenamento,
        "condicionantes": condicionantes,
        "plot_area_m2": round(plot_area, 1),
        "uncovered_pct": uncovered_pct,
        "area_max_construcao_total_m2": round(area_max_total, 1) if area_computed else None,
        "area_impermeavel_total_m2": round(area_imperm_total, 1) if imperm_computed else None,
        "diploma": diploma,
        "use_type": use_type,
        "use_type_checked": viability.get("use_regime") is not None,
        "level": level,
        "viability": viability,
        "source": {
            "portal": source_portal,
            "version": source_version,
            "ingested_at": ingested_at.isoformat() if ingested_at else None,
        },
    }


@router.post("/urban/analyze/", auth=ProfileAuth())
@ratelimit(group="urban:analyze", key=user_or_ip, rate="30/m")
def urban_analyze(request, payload: UrbanAnalyzeRequest):
    """L1–L3 urban analysis for a drawn plot (thin wrapper over run_urban_analysis).

    Validates the use_type + polygon, runs the shared analysis, logs, returns."""
    if payload.use_type not in URBAN_USE_TYPES:
        raise HttpError(400, f"Unknown use_type: {payload.use_type}")
    plot = _build_plot(payload.polygon)
    result = run_urban_analysis(plot, payload.use_type)
    who = getattr(request.auth, "id", "?")
    if not result["covered"]:
        logger.info("[urban.analyze] profile=%s use_type=%s → no coverage", who, payload.use_type)
    else:
        logger.info(
            "[urban.analyze] profile=%s municipio=%s use_type=%s ord=%d cond=%d "
            "area=%.0fm² level=%s verdict=%s",
            who, result["municipio"], payload.use_type, len(result["ordenamento"]),
            len(result["condicionantes"]), result["plot_area_m2"], result["level"],
            result["viability"]["verdict"],
        )
    return result


# ---- Gate-L2 validation dossiê (staff) -------------------------------------
# A reviewable package that lets a licensed urbanista check-mark the curated
# rules against their verbatim regulamento source, instead of auditing from
# scratch. It runs the *production* analysis (run_urban_analysis) on a
# representative plot per qualification, so what the urbanista signs off is
# exactly what the tool computes. Não constitui parecer (invariant §2.5).

_SAMPLE_HALF_M = 11.3  # ~510 m² square sample plot per qualification

# Least-privilege access to the dossiê: staff, or a member of this group — a
# licensed urbanista invited to sign off Gate-L2 gets *only* this surface, never
# is_staff (which would grant the public Django admin + every staff feature).
URBAN_VALIDATOR_GROUP = "urban_validators"

# Verdict scenarios — (regime-branch label, categoria, subcategoria, use_type)
# chosen to exercise each use-adjudication branch end-to-end. Derived from
# ingested categorias (no hardcoded coords); the dossiê shows the branch + the
# live verdict/reasons so the urbanista can sanity-check the L3 logic.
_VALIDATION_SCENARIOS = [
    ("uso dominante → permitido", "Espaços de atividades económicas",
     "Espaços de atividades económicas", "industrial"),
    ("uso não dominante → condicionado", "Espaços de atividades económicas",
     "Espaços de atividades económicas", "residential"),
    ("zona não edificável → interdito", "Espaços verdes", "Espaços verdes", "residential"),
]


def _sample_plot(municipio: str, categoria: str, subcategoria: str):
    """A ~510 m² square around an interior point of the largest polygon of this
    qualification — a representative plot to exercise run_urban_analysis on. None
    if the qualification has no ingested geometry."""
    qs = UrbanOrdenamento.objects.filter(
        municipio=municipio, categoria=categoria, subcategoria=subcategoria)
    # Resolve the metric CRS from a light DB-computed probe point (never pull a
    # whole ordenamento geometry into Python just to locate the município).
    probe = (qs.annotate(_pt=PointOnSurface("geometry"))
             .values_list("_pt", flat=True).first())
    if probe is None:
        return None
    srid = metric_srid_for(probe)
    o = qs.annotate(_a=Area(Transform("geometry", srid))).order_by("-_a").first()
    p = o.geometry.point_on_surface  # interior point, SRID 4326
    pm = p.clone()
    pm.transform(srid)
    x, y, h = pm.x, pm.y, _SAMPLE_HALF_M
    square = Polygon([(x - h, y - h), (x + h, y - h), (x + h, y + h),
                      (x - h, y + h), (x - h, y - h)], srid=srid)
    square.transform(4326)
    return square


def _validator_account(request):
    """The signed-in Account iff it may access the dossiê — staff, or a member of
    the urban_validators group (least-privilege). None otherwise. Authorization
    lives on the Account (login + group), so that is who a sign-off is attributed to."""
    account = getattr(request.auth, "account", None)
    if account is not None and (
            account.is_staff
            or account.groups.filter(name=URBAN_VALIDATOR_GROUP).exists()):
        return account
    return None


def _rule_signable(r: UrbanRule) -> dict:
    """The exact parameters a validator confirms — the content of a sign-off.
    Snapshotted at sign time and compared to the live rule on the dossiê, so any
    later reimport that changes a value flips the sign-off to *stale* (usos sorted
    for order-independent comparison)."""
    return {
        "indice_utilizacao": float(r.indice_utilizacao) if r.indice_utilizacao is not None else None,
        "indice_utilizacao_max": r.indice_utilizacao_max,
        "indice_impermeabilizacao_pct": (
            float(r.indice_impermeabilizacao_pct) if r.indice_impermeabilizacao_pct is not None else None),
        "num_pisos_max": r.num_pisos_max,
        "cercea_max_m": float(r.cercea_max_m) if r.cercea_max_m is not None else None,
        "edificavel": r.edificavel,
        "usos_dominantes": sorted(r.usos_dominantes or []),
        "uso_default_regime": r.uso_default_regime,
        "artigo": r.artigo,
        "artigo_usos": r.artigo_usos,
        "source_quote": r.source_quote,
    }


def _signoff_view(s: UrbanRuleSignoff, current: dict, me_id) -> dict:
    """Serialize a sign-off for the dossiê: who + when, whether it is the viewer's
    own, and whether the rule changed since it was signed (stale → reconfirm)."""
    return {
        "who": s.account.get_full_name() or s.account.username,
        "signed_at": s.signed_at.isoformat(),
        "mine": s.account_id == me_id,
        "stale": s.signed_snapshot != current,
    }


class SignoffRequest(Schema):
    # The curated rule to confirm, by its natural key within the município.
    categoria: str
    subcategoria: str = ""
    confere: bool  # True = record/refresh the confirmation, False = withdraw it


@router.get("/urban/validation/{municipio}", auth=ProfileAuth())
def urban_validation(request, municipio: str):
    """Gate-L2 validation dossiê (staff only).

    Per curated rule: our transcribed parameters + the verbatim regulamento
    `source_quote` that fixes them + a live run of the production analysis on a
    representative plot (area → área máxima / impermeável, verdict). Plus a few
    scenarios exercising the use-adjudication branches. The urbanista verifies
    each row against the quoted artigo and check-marks it. Não constitui parecer."""
    me = _validator_account(request)
    if me is None:
        raise HttpError(403, "Not authorized")

    rules = list(
        UrbanRule.objects.filter(municipio=municipio).order_by("artigo", "subcategoria"))
    if not rules:
        raise HttpError(404, f"No curated rules for município '{municipio}'")

    # Existing sign-offs for this município, grouped by the rule's natural key.
    signoff_map = {}
    for s in UrbanRuleSignoff.objects.filter(municipio=municipio).select_related("account"):
        signoff_map.setdefault((s.categoria, s.subcategoria), []).append(s)
    me_id = me.id

    diploma = next((r.diploma for r in rules if r.diploma), None)
    version = next((r.source_version for r in rules if r.source_version), None)
    source = next((r.source for r in rules if r.source), None)

    rows = []
    for r in rules:
        sample = None
        plot = _sample_plot(municipio, r.categoria, r.subcategoria)
        if plot is not None:
            use = (r.usos_dominantes or ["residential"])[0]
            res = run_urban_analysis(plot, use)
            if res["covered"] and res["ordenamento"]:
                dom = res["ordenamento"][0]
                sample = {
                    "use_type": use,
                    "plot_area_m2": res["plot_area_m2"],
                    "coverage_pct": dom["coverage_pct"],
                    "matched": (dom["categoria"] == r.categoria
                                and dom["subcategoria"] == r.subcategoria),
                    "area_max_construcao_m2": (dom.get("rule") or {}).get("area_max_construcao_m2"),
                    "area_impermeavel_m2": res["area_impermeavel_total_m2"],
                    "verdict": res["viability"]["verdict"],
                    "confidence": res["viability"]["confidence"],
                }
        rows.append({
            "categoria": r.categoria, "subcategoria": r.subcategoria,
            "artigo": r.artigo, "artigo_usos": r.artigo_usos,
            "edificavel": r.edificavel,
            "indice_utilizacao": float(r.indice_utilizacao) if r.indice_utilizacao is not None else None,
            "indice_utilizacao_max": r.indice_utilizacao_max,
            "indice_impermeabilizacao_pct": (
                float(r.indice_impermeabilizacao_pct) if r.indice_impermeabilizacao_pct is not None else None),
            "num_pisos_max": r.num_pisos_max,
            "cercea_max_m": float(r.cercea_max_m) if r.cercea_max_m is not None else None,
            "usos_dominantes": r.usos_dominantes or [],
            "uso_default_regime": r.uso_default_regime,
            "source_quote": r.source_quote,
            "notes": r.notes,
            "sample": sample,
            "signoffs": [
                _signoff_view(s, _rule_signable(r), me_id)
                for s in signoff_map.get((r.categoria, r.subcategoria), [])
            ],
        })

    scenarios = []
    for label, cat, subcat, use in _VALIDATION_SCENARIOS:
        plot = _sample_plot(municipio, cat, subcat)
        if plot is None:
            continue
        res = run_urban_analysis(plot, use)
        v = res["viability"] if res["covered"] else None
        scenarios.append({
            "label": label, "categoria": cat, "subcategoria": subcat, "use_type": use,
            "verdict": v["verdict"] if v else "sem_dados",
            "use_regime": v["use_regime"] if v else None,
            "reasons": v["reasons"] if v else [],
        })

    logger.info("[urban.validation] staff=%s municipio=%s rules=%d scenarios=%d",
                getattr(request.auth, "id", "?"), municipio, len(rows), len(scenarios))
    return {
        "municipio": municipio,
        "generated_at": timezone.now().isoformat(),
        "rule_source": source,
        "rule_version": version,
        "diploma": diploma,
        "rules": rows,
        "scenarios": scenarios,
        "gate": "L2",
        "disclaimer": (
            "Indicação automática de apoio à decisão, gerada a partir de dados públicos "
            "(PDM em vigor). Não constitui parecer nem ato administrativo. Pende validação "
            "por urbanista licenciado (Gate-L2)."),
    }


@router.post("/urban/validation/{municipio}/signoff", auth=ProfileAuth())
def urban_validation_signoff(request, municipio: str, payload: SignoffRequest):
    """Record or withdraw a validator's Gate-L2 confirmation of one curated rule.

    confere=True upserts the sign-off stamped with who + when + a snapshot of the
    parameters as shown (so a later reimport that changes them reads as stale on
    the dossiê); confere=False withdraws it. Same least-privilege gate as the GET.
    Returns the refreshed sign-off list for that rule."""
    account = _validator_account(request)
    if account is None:
        raise HttpError(403, "Not authorized")

    rule = (UrbanRule.objects
            .filter(municipio=municipio, categoria=payload.categoria,
                    subcategoria=payload.subcategoria)
            .first())
    if rule is None:
        raise HttpError(404, "Unknown rule for this município")

    key = dict(municipio=municipio, source=rule.source, categoria=rule.categoria,
               subcategoria=rule.subcategoria, account=account)
    if payload.confere:
        UrbanRuleSignoff.objects.update_or_create(
            **key, defaults={"signed_snapshot": _rule_signable(rule),
                             "signed_at": timezone.now()})
    else:
        UrbanRuleSignoff.objects.filter(**key).delete()

    current = _rule_signable(rule)
    views = [
        _signoff_view(s, current, account.id)
        for s in (UrbanRuleSignoff.objects
                  .filter(municipio=municipio, source=rule.source,
                          categoria=rule.categoria, subcategoria=rule.subcategoria)
                  .select_related("account"))
    ]
    logger.info("[urban.validation.signoff] account=%s municipio=%s rule=%s/%s confere=%s",
                account.username, municipio, rule.categoria, rule.subcategoria, payload.confere)
    return {"ok": True, "signoffs": views}
