<template>
  <div v-if="result">
    <!-- Drawn plot: rotating polygon blueprint with rulers + real-world area
         (same MapFeatureImage building preview used for OSM building features). -->
    <MapFeatureImage
      :building-geometry="ring"
      class="flex-shrink-0"
    />

    <!-- L3 viability verdict — Sim / Condicionado / Não, justified, with grau de
         confiança. Automatic indication, não constitui parecer. -->
    <div v-if="result.viability" class="urban-verdict" :class="'v-' + result.viability.verdict">
      <div class="urban-verdict-head">
        <span class="urban-verdict-label">{{ $t('map.urban.viab_' + result.viability.verdict) }}</span>
        <span class="urban-verdict-conf">{{ $t('map.urban.viab_conf_' + result.viability.confidence) }}</span>
      </div>
      <ul v-if="result.viability.reasons.length" class="urban-verdict-reasons">
        <li v-for="(r, i) in result.viability.reasons" :key="'vr' + i">{{ reasonText(r) }}</li>
      </ul>
      <div class="urban-verdict-disclaimer">{{ $t('map.urban.viab_disclaimer') }}</div>
    </div>

    <div class="px-4 pt-3 urban-panel-body">
      <template v-if="result.covered">
        <!-- Ordenamento — classe/categoria do solo + L2 edificability params -->
        <div class="urban-sec-label">{{ $t('map.urban.sec_ordenamento') }}</div>
        <div v-for="(o, i) in result.ordenamento" :key="'o' + i" class="urban-ord-item">
          <div class="urban-ord">
            <span class="urban-dot" :class="classeClass(o.classe)" aria-hidden="true"></span>
            <div class="urban-ord-main">
              <div class="urban-ord-cat">{{ o.categoria || o.classe }}</div>
              <div class="urban-ord-sub">{{ o.classe }}<template v-if="o.subcategoria"> · {{ o.subcategoria }}</template></div>
            </div>
            <span v-if="o.coverage_pct != null" class="urban-cov">{{ o.coverage_pct }}%</span>
          </div>
          <!-- L2: edificability parameters (índices, pisos, artigo) -->
          <div v-if="o.rule" class="urban-rule">
            <span v-if="o.rule.indice_utilizacao != null" class="urban-chip" :title="$t('map.urban.iu_full')">
              IU {{ o.rule.indice_utilizacao.toFixed(2) }}<span v-if="!o.rule.indice_utilizacao_max" class="urban-chip-ref">{{ $t('map.urban.ref') }}</span>
            </span>
            <span v-if="o.rule.indice_impermeabilizacao_pct != null" class="urban-chip" :title="$t('map.urban.imperm_full')">Imp. {{ o.rule.indice_impermeabilizacao_pct }}%</span>
            <span v-if="o.rule.num_pisos_max != null" class="urban-chip">{{ o.rule.num_pisos_max }} {{ $t('map.urban.pisos') }}</span>
            <span v-if="o.rule.cercea_max_m != null" class="urban-chip" :title="$t('map.urban.cercea_full')">≤ {{ o.rule.cercea_max_m }} m</span>
            <span class="urban-chip urban-chip-art" :title="result.diploma || ''">art. {{ o.rule.artigo }}</span>
            <span v-if="o.rule.area_max_construcao_m2 != null" class="urban-chip urban-chip-area">≈ {{ fmtM2(o.rule.area_max_construcao_m2) }}</span>
          </div>
          <div v-if="o.rule && o.rule.area_max_construcao_m2 == null && o.rule.notes" class="urban-rule-note">{{ o.rule.notes }}</div>
        </div>

        <!-- L2: total buildable area -->
        <div v-if="result.area_max_construcao_total_m2 != null" class="urban-areamax-total">
          {{ $t('map.urban.area_max') }} <strong>≈ {{ fmtM2(result.area_max_construcao_total_m2) }}</strong>
        </div>
        <!-- L2: total impermeable (sealed) ground area -->
        <div v-if="result.area_impermeavel_total_m2 != null" class="urban-sealed-total">
          {{ $t('map.urban.area_impermeavel') }} <strong>≈ {{ fmtM2(result.area_impermeavel_total_m2) }}</strong>
        </div>

        <!-- Condicionantes — servidões / restrições -->
        <div class="urban-sec-label">
          {{ $t('map.urban.sec_condicionantes') }}
          <span v-if="result.condicionantes.length" class="urban-badge-count">{{ result.condicionantes.length }}</span>
        </div>
        <div v-if="result.condicionantes.length" class="urban-cnd-wrap">
          <span v-for="(c, i) in result.condicionantes" :key="'c' + i" class="urban-cnd" :class="'kind-' + c.kind" :title="c.grupo">
            {{ c.tipo }}<span v-if="c.features > 1" class="urban-cnd-n">×{{ c.features }}</span>
          </span>
        </div>
        <div v-else class="urban-muted-row">{{ $t('map.urban.no_condicionantes') }}</div>

        <!-- Footer — area, coverage caveat, provenance, scope note -->
        <div class="urban-foot">
          <span class="urban-area">{{ formattedArea }}</span>
          <span v-if="result.uncovered_pct >= 1" class="urban-warn">{{ $t('map.urban.uncovered', { pct: result.uncovered_pct }) }}</span>
        </div>
        <div v-if="result.source" class="urban-src">
          {{ $t('map.urban.source') }}: {{ result.source.portal }} · {{ result.source.version }}
        </div>
        <div v-if="result.diploma" class="urban-src urban-diploma">{{ result.diploma }}</div>
        <div class="urban-l1note">{{ result.level === 'L2' ? $t('map.urban.l2_note') : $t('map.urban.l1_note') }}</div>
      </template>

      <template v-else>
        <div class="urban-muted-row">{{ $t('map.urban.no_coverage_body') }}</div>
        <div v-if="result.available_municipios && result.available_municipios.length" class="urban-src">
          {{ $t('map.urban.available') }}: {{ result.available_municipios.map(municipioLabel).join(', ') }}
        </div>
      </template>

      <button class="urban-redraw-btn" @click="emit('redraw')">{{ $t('map.urban.redraw') }}</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import MapFeatureImage from '~/components/MapFeatureImage.vue'
import type { UrbanResult, UrbanViabilityReason } from '~/composables/useMapUrbanAnalysis'

const props = defineProps<{
  result: UrbanResult | null
  polygon: [number, number][]
  formattedArea: string
}>()

const emit = defineEmits<{ (e: 'redraw'): void }>()

const { t } = useI18n()

// Localized text for one L3 verdict reason (codes carry only data; text is i18n).
function reasonText(r: UrbanViabilityReason): string {
  switch (r.code) {
    case 'regime_restrito': return t('map.urban.viab_reason_regime', { artigo: r.artigo })
    case 'parte_nao_edificavel': return t('map.urban.viab_reason_parte')
    case 'condicionante': return t('map.urban.viab_reason_cond', { n: r.count })
    case 'edificavel_parametros': return t('map.urban.viab_reason_ok', { artigo: r.artigo })
    case 'uso_permitido': return t('map.urban.viab_reason_uso_permitido', { use: t('map.urban.types.' + r.use_type), artigo: r.artigo })
    case 'uso_condicionado': return t('map.urban.viab_reason_uso_condicionado', { use: t('map.urban.types.' + r.use_type), artigo: r.artigo })
    case 'uso_interdito': return t('map.urban.viab_reason_uso_interdito', { use: t('map.urban.types.' + r.use_type), artigo: r.artigo })
    case 'uso_nao_adjudicado': return t('map.urban.viab_reason_uso', { use: t('map.urban.types.' + r.use_type) })
    default: return ''
  }
}

// Closed ring (outer-only) for the rotating-polygon preview — MapFeatureImage
// expects GeoJSON-style rings: number[][][].
const ring = computed<number[][][] | null>(() => {
  const p = props.polygon
  if (!p || p.length < 3) return null
  return [[...p, p[0]]]
})

// município slug → display name (no per-município i18n yet → title-case).
function municipioLabel(slug: string | null): string {
  return slug ? slug.charAt(0).toUpperCase() + slug.slice(1) : ''
}
// Colour the classe dot: built land (urbano) vs rural land (rústico).
function classeClass(classe: string): string {
  return /urban/i.test(classe || '') ? 'is-urbano' : 'is-rustico'
}
// Compact m² / ha formatter for L2 buildable areas.
function fmtM2(n: number): string {
  return n >= 10000 ? `${(n / 10000).toFixed(2)} ha` : `${Math.round(n)} m²`
}
</script>

<style scoped>
.urban-panel-body {
  font-size: 13px;
  color: var(--color-text);
}
/* L3 viability verdict banner */
.urban-verdict {
  margin: 12px 16px 0;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--color-border);
  color: var(--color-text);
}
.urban-verdict-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.urban-verdict-label {
  font-size: 15px;
  font-weight: 800;
  letter-spacing: -0.01em;
}
.urban-verdict-conf {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  opacity: 0.7;
  white-space: nowrap;
}
.urban-verdict-reasons {
  margin: 6px 0 0;
  padding-left: 16px;
  font-size: 12px;
  line-height: 1.4;
}
.urban-verdict-reasons li {
  margin: 1px 0;
}
.urban-verdict-disclaimer {
  margin-top: 7px;
  font-size: 10px;
  font-style: italic;
  opacity: 0.7;
}
/* Verdict colors — only the headline word is tinted; reasons stay readable. */
.urban-verdict.v-edificavel {
  background: rgba(22, 163, 74, 0.07);
  border-color: rgba(22, 163, 74, 0.35);
}
.urban-verdict.v-edificavel .urban-verdict-label {
  color: #15803d;
}
.urban-verdict.v-condicionado {
  background: rgba(217, 119, 6, 0.07);
  border-color: rgba(217, 119, 6, 0.35);
}
.urban-verdict.v-condicionado .urban-verdict-label {
  color: #b45309;
}
.urban-verdict.v-nao_edificavel {
  background: rgba(220, 38, 38, 0.07);
  border-color: rgba(220, 38, 38, 0.35);
}
.urban-verdict.v-nao_edificavel .urban-verdict-label {
  color: #b91c1c;
}
.urban-verdict.v-sem_dados {
  background: rgba(120, 120, 120, 0.06);
}
.urban-verdict.v-sem_dados .urban-verdict-label {
  color: var(--color-text-muted);
}
:root.dark .urban-verdict.v-edificavel .urban-verdict-label {
  color: #4ade80;
}
:root.dark .urban-verdict.v-condicionado .urban-verdict-label {
  color: #fbbf24;
}
:root.dark .urban-verdict.v-nao_edificavel .urban-verdict-label {
  color: #f87171;
}
.urban-sec-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-text-muted);
  margin: 10px 0 5px;
}
.urban-badge-count {
  font-size: 10px;
  font-weight: 700;
  color: #fff;
  background: #7c3aed;
  border-radius: 10px;
  padding: 1px 6px;
}
.urban-ord-item {
  padding: 3px 0;
}
.urban-ord {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}
.urban-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.urban-dot.is-urbano {
  background: #d97706;
}
.urban-dot.is-rustico {
  background: #16a34a;
}
.urban-ord-main {
  flex: 1;
  min-width: 0;
}
.urban-ord-cat {
  font-weight: 600;
}
.urban-ord-sub {
  font-size: 11px;
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.urban-cov {
  font-size: 12px;
  font-weight: 700;
  color: #7c3aed;
  flex-shrink: 0;
}
/* L2 — edificability parameters */
.urban-rule {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin: 3px 0 4px 18px;
}
.urban-chip {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 6px;
  background: rgba(124, 58, 237, 0.06);
  color: var(--color-text);
  border: 1px solid var(--color-border);
}
:root.dark .urban-chip {
  background: rgba(124, 58, 237, 0.14);
}
.urban-chip-ref {
  font-weight: 400;
  opacity: 0.7;
  margin-left: 3px;
}
.urban-chip-art {
  color: #7c3aed;
  background: rgba(124, 58, 237, 0.08);
  border-color: rgba(124, 58, 237, 0.3);
}
.urban-chip-area {
  color: #16a34a;
  background: rgba(22, 163, 74, 0.08);
  border-color: rgba(22, 163, 74, 0.3);
  font-weight: 700;
}
.urban-rule-note {
  font-size: 11px;
  color: var(--color-text-muted);
  margin: 0 0 5px 18px;
  line-height: 1.35;
}
.urban-areamax-total {
  margin: 8px 0 2px;
  padding: 7px 10px;
  border-radius: 8px;
  background: rgba(22, 163, 74, 0.08);
  border: 1px solid rgba(22, 163, 74, 0.2);
  font-size: 13px;
}
.urban-areamax-total strong {
  color: #16a34a;
  font-size: 14px;
}
.urban-sealed-total {
  margin: 4px 0 2px;
  padding: 7px 10px;
  border-radius: 8px;
  background: rgba(217, 119, 6, 0.08);
  border: 1px solid rgba(217, 119, 6, 0.2);
  font-size: 13px;
}
.urban-sealed-total strong {
  color: #b45309;
  font-size: 14px;
}
.urban-cnd-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.urban-cnd {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 12px;
  background: rgba(217, 119, 6, 0.12);
  color: #b45309;
  border: 1px solid rgba(217, 119, 6, 0.25);
}
:root.dark .urban-cnd {
  color: #fbbf24;
  background: rgba(217, 119, 6, 0.18);
}
.urban-cnd.kind-line,
.urban-cnd.kind-point {
  background: transparent;
  color: var(--color-text-muted);
  border-color: var(--color-border);
}
.urban-cnd-n {
  opacity: 0.7;
  margin-left: 3px;
}
.urban-muted-row {
  font-size: 12px;
  color: var(--color-text-muted);
  padding: 2px 0;
}
.urban-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 10px;
  font-size: 12px;
}
.urban-area {
  font-weight: 600;
}
.urban-warn {
  font-size: 11px;
  color: #d97706;
}
.urban-src {
  font-size: 11px;
  color: var(--color-text-muted);
  margin-top: 4px;
  word-break: break-word;
}
.urban-diploma {
  font-style: italic;
  opacity: 0.85;
}
.urban-l1note {
  font-size: 11px;
  color: var(--color-text-muted);
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid var(--color-border);
  line-height: 1.35;
}
.urban-redraw-btn {
  width: 100%;
  margin-top: 14px;
  padding: 8px 14px;
  border: none;
  border-radius: 8px;
  background: #7c3aed;
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}
.urban-redraw-btn:hover {
  background: #6d28d9;
}
</style>
