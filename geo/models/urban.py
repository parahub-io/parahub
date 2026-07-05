from django.contrib.gis.db import models
from core.models import ULIDModel


class UrbanOrdenamento(ULIDModel):
    """PDM *ordenamento* (land-use qualification) polygon — one row per feature.

    The Planta de Ordenamento qualifies every parcel of a município into a
    `classe` (Solo Urbano / Solo Rústico) and a `categoria` / `subcategoria` de
    uso do solo. These polygons tile the município; intersecting a plot against
    them yields its land-use qualification — the core of an L1 territorial
    assessment (PK/.todo urban ТЗ §6 L1).

    Reference data: reloaded wholesale per (municipio, source) on import,
    version-stamped, so no per-row upsert is needed (cf. DroneZone). Provenance
    for the §2 "every statement has a source" invariant is carried per row by
    source + source_version + service_layer.
    """
    municipio = models.CharField(max_length=64, db_index=True,
        help_text="Município slug, e.g. 'caminha'")
    source = models.CharField(max_length=64, default='caminha_munisig', db_index=True,
        help_text="ETL adapter / SIG portal the data was ingested from")
    source_version = models.CharField(max_length=64, blank=True,
        help_text="Data snapshot / plan version stamp, e.g. 'munisig-2026-06-30'")
    service_layer = models.CharField(max_length=128, blank=True,
        help_text="Provenance: source service + layer id, e.g. 'ORDENAMENTO/12'")

    classe = models.CharField(max_length=128, blank=True, db_index=True,
        help_text="Classe do solo: 'Solo Urbano' | 'Solo Rústico'")
    categoria = models.CharField(max_length=255, blank=True,
        help_text="Categoria de uso do solo (regulamento quadro de usos)")
    subcategoria = models.CharField(max_length=255, blank=True)
    attributes = models.JSONField(default=dict, blank=True,
        help_text="Curated source attributes (e.g. area_ha) for traceability")

    # Plain geometry (not geography): the L1 operation is ST_Intersects — a
    # topological test where 4326 degrees are exact. Metric areas/distances are
    # obtained by transforming to the location's metric CRS at query time
    # (metric_srid_for(): PT continent → EPSG:3763, else the centroid's UTM zone).
    # Plain geometry also tolerates the minor invalidity common in plan data.
    geometry = models.GeometryField(srid=4326, help_text="Ordenamento polygon (WGS84)")
    ingested_at = models.DateTimeField(db_index=True, help_text="When this batch was loaded")

    class Meta:
        indexes = [models.Index(fields=['municipio', 'classe'])]

    def __str__(self):
        return f"{self.municipio}: {self.classe} / {self.categoria}"

class UrbanCondicionante(ULIDModel):
    """PDM *condicionante* (servidão / restrição de utilidade pública) feature.

    The Planta de Condicionantes overlays legal restrictions on the território —
    REN, RAN, domínio hídrico, Rede Natura, servidões de infraestruturas,
    património classificado, etc. Geometry is mixed (areas like REN/RAN; lines
    like roads and watercourses; points like geodesic markers), hence a generic
    geometry column. The condicionante *type* is the source layer identity (the
    underlying attribute tables are CAD-derived noise with no usable type
    field), so `grupo` / `tipo` are taken from the service layer hierarchy.

    Reference data: reloaded wholesale per (municipio, source) on import.
    """
    municipio = models.CharField(max_length=64, db_index=True)
    source = models.CharField(max_length=64, default='caminha_munisig', db_index=True)
    source_version = models.CharField(max_length=64, blank=True,
        help_text="Data snapshot / plan version stamp")
    service_layer = models.CharField(max_length=128, blank=True,
        help_text="Provenance: source service + layer id, e.g. 'CONDICIONANTES/23'")

    grupo = models.CharField(max_length=128, blank=True, db_index=True,
        help_text="Condicionante group, e.g. 'Recursos Naturais'")
    tipo = models.CharField(max_length=255, blank=True, db_index=True,
        help_text="Condicionante type = layer name, e.g. 'Reserva Ecológica Nacional'")
    attributes = models.JSONField(default=dict, blank=True)

    geometry = models.GeometryField(srid=4326,
        help_text="Condicionante geometry (mixed point/line/polygon, WGS84)")
    ingested_at = models.DateTimeField(db_index=True, help_text="When this batch was loaded")

    class Meta:
        indexes = [models.Index(fields=['municipio', 'tipo'])]

    def __str__(self):
        return f"{self.municipio}: {self.tipo}"

class UrbanRule(ULIDModel):
    """Edificability parameters for a PDM land-use (sub)category — the L2 rule.

    Joins to UrbanOrdenamento by (municipio, categoria, subcategoria): given the
    qualification L1 found for a plot, this carries the parameters the
    regulamento fixes for it — índice de utilização, índice de impermeabilização,
    nº máximo de pisos, cércea — each traced to its artigo + diploma (PK/.todo
    urban ТЗ §6 L2, invariant §2.3/§2.4).

    Curated, NOT machine-parsed: every number is transcribed by hand from the
    consolidated regulamento and tagged with its artigo, then loaded wholesale
    per (municipio, source) — so it can be audited and validated by a licensed
    urbanista (Gate-L2 / §5.4) before any production reliance. Parameters are
    nullable: a category may fix some and leave others to a non-numeric regime
    (e.g. alignment / moda da altura), captured in `notes`. The system reports
    these parameters; it does not issue a binding opinion (§2.5).
    """
    municipio = models.CharField(max_length=64, db_index=True)
    source = models.CharField(max_length=64, default='caminha_pdm_reg', db_index=True,
        help_text="Curation source key (regulamento the rules were transcribed from)")
    source_version = models.CharField(max_length=64, blank=True,
        help_text="Plan/regulamento version, e.g. 'aviso-4482-2024'")

    # Join key — matches UrbanOrdenamento.categoria / .subcategoria verbatim.
    categoria = models.CharField(max_length=255, db_index=True)
    subcategoria = models.CharField(max_length=255, blank=True, db_index=True)

    # Legal citation (§2.3): the exact artigo + the diploma it lives in.
    diploma = models.CharField(max_length=255, blank=True,
        help_text="e.g. 'DR 2.ª série N.º 41, 27-02-2024, Aviso n.º 4482/2024'")
    artigo = models.CharField(max_length=32, blank=True, help_text="e.g. '54.º'")

    # Parameters — nullable; not every category fixes every one.
    indice_utilizacao = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Índice de utilização do solo (m²/m²): área de construção / área do solo")
    indice_utilizacao_max = models.BooleanField(default=True,
        help_text="True = 'máximo'; False = 'de referência' (regulamento wording)")
    indice_impermeabilizacao_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Índice máximo de impermeabilização (%)")
    num_pisos_max = models.PositiveSmallIntegerField(null=True, blank=True,
        help_text="N.º máximo de pisos acima da cota de soleira")
    cercea_max_m = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Cércea máxima (m), where the plan fixes one")
    edificavel = models.BooleanField(default=True,
        help_text="False / restricted regime (e.g. espaços verdes — apoio only)")
    # Quadro de usos (L3 use-adjudication). usos_dominantes = the use slugs the
    # regulamento names as dominant/destined for this espaço (→ permitido). The
    # regime of a NON-listed use is itself curated per rule (uso_default_regime):
    # regulamentos differ — «outros usos, desde que compatíveis» → condicionado,
    # «são interditos os usos não previstos» → interdito. Blank = not curated →
    # non-listed uses stay un-adjudicated (invariant 1: never a guessed regime).
    usos_dominantes = models.JSONField(default=list, blank=True,
        help_text="Dominant/permitido use slugs (quadro de usos)")
    uso_default_regime = models.CharField(max_length=16, blank=True, choices=[
        ("condicionado", "condicionado"), ("interdito", "interdito")],
        help_text="Curated regime for uses NOT in usos_dominantes, per the regulamento's "
                  "own wording; blank = not curated (non-listed uses stay un-adjudicated)")
    artigo_usos = models.CharField(max_length=32, blank=True,
        help_text="Artigo of the Caracterização/usos provision (e.g. '53.º'), where it "
                  "differs from the Edificabilidade artigo")
    source_quote = models.TextField(blank=True,
        help_text="Verbatim regulamento sentence(s) establishing the índices/usos/edificável "
                  "above, artigo-prefixed — the provenance a licensed urbanista check-marks "
                  "(Gate-L2). Completes the citation: value sits next to the words that fix it")
    notes = models.TextField(blank=True,
        help_text="Source-derived regime text (PT) for non-numeric rules; authoritative")

    ingested_at = models.DateTimeField(db_index=True, help_text="When this batch was loaded")

    class Meta:
        indexes = [models.Index(fields=['municipio', 'categoria', 'subcategoria'])]

    def __str__(self):
        return f"{self.municipio}: {self.categoria} / {self.subcategoria} (art. {self.artigo})"

class UrbanRuleSignoff(ULIDModel):
    """A validator's Gate-L2 confirmation that one curated UrbanRule matches its
    verbatim regulamento source ("Confere?").

    Keyed by the rule's *stable* natural identity (municipio, source, categoria,
    subcategoria) + the signing account — NOT the UrbanRule PK, which is
    regenerated on every `import_urban_rules` (delete + bulk_create), so a PK-keyed
    sign-off would be silently orphaned on each reload. A snapshot of the exact
    parameters signed is stored, so a later reimport that changes any of them is
    detectable: the sign-off then reads *stale* on the dossiê and no longer vouches
    for the new values — a confirmation must only ever attest the content it saw.

    DB-only provenance for now (who + when + what). A PGP-signed, append-only
    court-grade sign-off is a later upgrade (Gate-L2 / audit-system).
    """
    municipio = models.CharField(max_length=64, db_index=True)
    source = models.CharField(max_length=64,
        help_text="Rule-bundle source key this confirmation attests (UrbanRule.source)")
    categoria = models.CharField(max_length=255)
    subcategoria = models.CharField(max_length=255, blank=True)

    account = models.ForeignKey('identity.Account', on_delete=models.CASCADE,
        related_name="urban_rule_signoffs", help_text="The validator who signed")
    signed_snapshot = models.JSONField(default=dict,
        help_text="Rule parameters as shown when signed; compared to current to flag staleness")
    signed_at = models.DateTimeField(help_text="When this confirmation was recorded / last refreshed")

    class Meta:
        unique_together = (("municipio", "source", "categoria", "subcategoria", "account"),)
        indexes = [models.Index(fields=["municipio", "source"])]

    def __str__(self):
        return f"{self.account_id} ✓ {self.municipio}: {self.categoria} / {self.subcategoria}"
