"""
Urban analysis (L1–L3) unit + integration tests.

Covers the two jurisdiction seams that must stay data-driven, not code-level
assumptions:
  - metric_srid_for(): metric CRS per plot location (PT continent → PT-TM06;
    Azores/Madeira/anywhere else → the centroid's WGS84/UTM zone). PT-TM06
    applied ~1500 km off-shore distorts areas by several percent — the Azores
    integration test pins that down with numbers.
  - uso_default_regime: the regime of a use NOT listed in usos_dominantes is
    curated per rule (regulamentos differ: «outros usos, desde que compatíveis»
    → condicionado vs «são interditos os usos não previstos» → interdito);
    blank = not curated → un-adjudicated, never a guess (invariant 1).
"""

from django.contrib.gis.geos import Point, Polygon
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from geo.endpoints.urban import (
    PT_TM06_SRID,
    _adjudicate_use,
    _compute_viability,
    metric_srid_for,
    run_urban_analysis,
)
from geo.models import UrbanOrdenamento, UrbanRule


def _square_4326(lon: float, lat: float, half_m: float, srid: int) -> Polygon:
    """Axis-aligned square of ±half_m metres around (lon, lat), built in the
    given metric SRID and returned in 4326 — a known-area test plot."""
    c = Point(lon, lat, srid=4326)
    c.transform(srid)
    x, y, h = c.x, c.y, half_m
    sq = Polygon([(x - h, y - h), (x + h, y - h), (x + h, y + h),
                  (x - h, y + h), (x - h, y - h)], srid=srid)
    sq.transform(4326)
    return sq


class MetricSridTests(SimpleTestCase):
    def test_continental_portugal_uses_official_pt_tm06(self):
        for lon, lat in [(-8.83, 41.87),   # Caminha
                         (-9.14, 38.71),   # Lisboa
                         (-7.93, 37.02)]:  # Faro
            self.assertEqual(metric_srid_for(Point(lon, lat, srid=4326)), PT_TM06_SRID)

    def test_azores_and_madeira_use_their_utm_zone(self):
        self.assertEqual(metric_srid_for(Point(-25.67, 37.74, srid=4326)), 32626)  # São Miguel
        self.assertEqual(metric_srid_for(Point(-31.13, 39.45, srid=4326)), 32625)  # Flores
        self.assertEqual(metric_srid_for(Point(-16.92, 32.65, srid=4326)), 32628)  # Madeira

    def test_other_jurisdictions_fall_back_to_centroid_utm(self):
        self.assertEqual(metric_srid_for(Point(13.40, 52.52, srid=4326)), 32633)   # Berlin
        self.assertEqual(metric_srid_for(Point(-46.63, -23.55, srid=4326)), 32723)  # São Paulo (S)

    def test_utm_zone_is_clamped_at_the_antimeridian(self):
        self.assertEqual(metric_srid_for(Point(180.0, 0.0, srid=4326)), 32660)


class AdjudicateUseTests(SimpleTestCase):
    def _rule(self, **kw):
        base = {"edificavel": True, "usos_dominantes": ["residential"],
                "uso_default_regime": None}
        base.update(kw)
        return base

    def test_no_rule_or_no_quadro_de_usos_is_not_adjudicated(self):
        self.assertIsNone(_adjudicate_use(None, "residential"))
        self.assertIsNone(_adjudicate_use(self._rule(usos_dominantes=[]), "residential"))

    def test_dominant_use_is_permitido(self):
        self.assertEqual(_adjudicate_use(self._rule(), "residential"), "permitido")

    def test_non_edificavel_zone_is_interdito(self):
        self.assertEqual(
            _adjudicate_use(self._rule(edificavel=False), "residential"), "interdito")

    def test_non_listed_use_follows_the_curated_default_regime(self):
        r = self._rule(uso_default_regime="condicionado")
        self.assertEqual(_adjudicate_use(r, "industrial"), "condicionado")
        r = self._rule(uso_default_regime="interdito")
        self.assertEqual(_adjudicate_use(r, "industrial"), "interdito")

    def test_non_listed_use_without_curated_default_is_not_adjudicated(self):
        # Invariant 1: no curated default regime → no guessed regime.
        self.assertIsNone(_adjudicate_use(self._rule(), "industrial"))


class ViabilityInterditoTests(SimpleTestCase):
    def test_uso_interdito_by_default_regime_yields_nao_edificavel(self):
        ordenamento = [{"rule": {
            "edificavel": True, "usos_dominantes": ["residential"],
            "uso_default_regime": "interdito", "artigo": "10.º", "artigo_usos": "9.º",
        }}]
        v = _compute_viability(ordenamento, [], 0.0, "industrial")
        self.assertEqual(v["verdict"], "nao_edificavel")
        self.assertEqual(v["use_regime"], "interdito")
        self.assertIn(
            {"code": "uso_interdito", "use_type": "industrial", "artigo": "9.º"},
            v["reasons"])


class AzoresAnalysisTests(TestCase):
    """End-to-end run_urban_analysis on an Azores plot: the metric CRS must be
    the local UTM zone, not continental PT-TM06 (which mis-measures areas there
    by several percent), and an 'interdito' default regime must reach the verdict."""

    LON, LAT = -25.67, 37.74  # Ponta Delgada, São Miguel
    UTM = 32626

    @classmethod
    def setUpTestData(cls):
        UrbanOrdenamento.objects.create(
            municipio="ponta-delgada", source="test", source_version="t1",
            service_layer="TEST/1", classe="Solo Urbano",
            categoria="Espaços habitacionais", subcategoria="",
            geometry=_square_4326(cls.LON, cls.LAT, 500, cls.UTM),
            ingested_at=timezone.now(),
        )
        UrbanRule.objects.create(
            municipio="ponta-delgada", source="test", source_version="t1",
            categoria="Espaços habitacionais", subcategoria="",
            diploma="test-diploma", artigo="10.º",
            indice_utilizacao="0.50", edificavel=True,
            usos_dominantes=["residential"], uso_default_regime="interdito",
            ingested_at=timezone.now(),
        )

    def test_plot_area_uses_local_utm_not_pt_tm06(self):
        plot = _square_4326(self.LON, self.LAT, 50, self.UTM)  # 100×100 m = 10 000 m²
        res = run_urban_analysis(plot, "residential")
        self.assertTrue(res["covered"])
        # Accurate in the local UTM zone (round-trip error well under 1%)...
        self.assertAlmostEqual(res["plot_area_m2"], 10_000, delta=100)
        self.assertAlmostEqual(res["area_max_construcao_total_m2"], 5_000, delta=50)
        # ...whereas continental PT-TM06 would be off by several percent here —
        # the number this seam exists to keep correct.
        wrong = plot.clone()
        wrong.transform(PT_TM06_SRID)
        self.assertGreater(abs(wrong.area - 10_000) / 10_000, 0.02)

    def test_interdito_default_regime_reaches_the_verdict(self):
        plot = _square_4326(self.LON, self.LAT, 50, self.UTM)
        res = run_urban_analysis(plot, "industrial")  # not in usos_dominantes
        self.assertEqual(res["viability"]["use_regime"], "interdito")
        self.assertEqual(res["viability"]["verdict"], "nao_edificavel")
        res_ok = run_urban_analysis(plot, "residential")
        self.assertEqual(res_ok["viability"]["use_regime"], "permitido")
