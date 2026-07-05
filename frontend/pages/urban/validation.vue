<template>
  <div>
    <Head>
      <Title>{{ $t('map.urban.val_title') }} · {{ municipio }}</Title>
      <Meta name="robots" content="noindex,nofollow" />
    </Head>

    <div v-if="forbidden" class="text-center py-20">
      <ShieldAlert class="w-12 h-12 text-neutral-400 mx-auto mb-4" />
      <p class="text-neutral-500">{{ $t('dispatch.staff_only') }}</p>
    </div>

    <div v-else class="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-5">
      <!-- Header -->
      <div class="flex items-start gap-3">
        <div class="urban-val-icon"><ClipboardCheck class="w-5 h-5" /></div>
        <div>
          <h1 class="text-xl font-bold text-neutral-900 dark:text-neutral-100">
            {{ $t('map.urban.val_title') }}
          </h1>
          <p class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('map.urban.val_subtitle') }}</p>
        </div>
      </div>

      <!-- States -->
      <div v-if="loading" class="flex justify-center py-16">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" />
      </div>
      <div v-else-if="error" class="text-center py-16 space-y-3">
        <p class="text-red-600 dark:text-red-400 text-sm">{{ error }}</p>
        <UiButton variant="outline" size="sm" @click="load">{{ $t('map.urban.redraw') }}</UiButton>
      </div>

      <template v-else-if="data">
        <!-- Meta -->
        <div class="urban-val-meta">
          <span class="font-semibold text-neutral-700 dark:text-neutral-200 uppercase">{{ municipio }}</span>
          <span>{{ $t('map.urban.val_generated') }}: {{ fmtDate(data.generated_at) }}</span>
          <span v-if="data.rule_version">{{ $t('map.urban.val_rules_version') }}: {{ data.rule_version }}</span>
        </div>
        <div v-if="data.diploma" class="urban-val-diploma">{{ $t('map.urban.val_diploma') }}: {{ data.diploma }}</div>

        <!-- Disclaimer -->
        <div class="urban-val-disclaimer">{{ data.disclaimer }}</div>

        <!-- Section A: parameters vs source -->
        <section class="space-y-3">
          <div>
            <h2 class="text-sm font-semibold text-neutral-800 dark:text-neutral-200">{{ $t('map.urban.val_params_heading') }}</h2>
            <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">{{ $t('map.urban.val_params_note') }}</p>
          </div>

          <article v-for="(r, i) in data.rules" :key="i" class="urban-val-card">
            <header class="urban-val-card-head">
              <div class="min-w-0">
                <span class="font-semibold text-neutral-900 dark:text-neutral-100">{{ r.categoria }}</span>
                <span v-if="r.subcategoria && r.subcategoria !== r.categoria" class="text-neutral-500 dark:text-neutral-400"> / {{ r.subcategoria }}</span>
                <span class="urban-val-art">art. {{ r.artigo }}<template v-if="r.artigo_usos && r.artigo_usos !== r.artigo"> · {{ r.artigo_usos }}</template></span>
              </div>
              <label class="urban-val-confere">
                <input type="checkbox" :checked="isConfirmedByMe(r)" @change="toggleConfere(r, $event)" />
                <span>{{ $t('map.urban.val_confere') }}</span>
              </label>
            </header>

            <!-- Who confirmed this rule, and when (amber = rule changed since → reconfirm) -->
            <div v-if="r.signoffs && r.signoffs.length" class="urban-val-signers">
              <span v-for="(s, k) in r.signoffs" :key="k"
                    class="urban-val-signer" :class="{ 'is-stale': s.stale }">
                <component :is="s.stale ? AlertTriangle : CheckCircle2" class="w-3.5 h-3.5 shrink-0" />
                {{ s.who }} · {{ fmtDate(s.signed_at) }}<template v-if="s.stale"> · {{ $t('map.urban.val_stale') }}</template>
              </span>
            </div>

            <!-- Our parameters -->
            <div class="urban-val-block">
              <div class="urban-val-blabel">{{ $t('map.urban.val_our_params') }}</div>
              <div class="urban-val-chips">
                <span class="urban-val-chip" :title="$t('map.urban.iu_full')">IU {{ fmtIU(r.indice_utilizacao, r.indice_utilizacao_max) }}</span>
                <span class="urban-val-chip" :title="$t('map.urban.imperm_full')">
                  {{ r.indice_impermeabilizacao_pct != null ? r.indice_impermeabilizacao_pct + '%' : $t('map.urban.val_not_fixed') }}
                </span>
                <span v-if="r.num_pisos_max != null" class="urban-val-chip">≤ {{ r.num_pisos_max }} {{ $t('map.urban.pisos') }}</span>
                <span class="urban-val-chip" :class="r.edificavel ? 'is-ok' : 'is-no'">
                  {{ r.edificavel ? $t('map.urban.viab_edificavel') : $t('map.urban.viab_nao_edificavel') }}
                </span>
              </div>
              <div v-if="r.usos_dominantes && r.usos_dominantes.length" class="urban-val-usos">
                {{ $t('map.urban.val_usos') }}: {{ r.usos_dominantes.map((u: string) => $t('map.urban.types.' + u, u)).join(', ') }}
                <template v-if="r.uso_default_regime"> · {{ $t('map.urban.val_uso_default_' + r.uso_default_regime) }}</template>
              </div>
            </div>

            <!-- Verbatim source -->
            <div class="urban-val-block">
              <div class="urban-val-blabel">{{ $t('map.urban.val_source') }}</div>
              <blockquote class="urban-val-quote">{{ r.source_quote }}</blockquote>
            </div>

            <!-- Live sample -->
            <div v-if="r.sample" class="urban-val-block">
              <div class="urban-val-blabel">{{ $t('map.urban.val_sample') }} · {{ fmtM2(r.sample.plot_area_m2, false) }}</div>
              <div class="urban-val-chips">
                <span class="urban-val-chip">{{ $t('map.urban.area_max') }}: {{ fmtM2(r.sample.area_max_construcao_m2, true) }}</span>
                <span class="urban-val-chip">{{ $t('map.urban.area_impermeavel') }}: {{ fmtM2(r.sample.area_impermeavel_m2, true) }}</span>
                <span class="urban-val-verdict" :class="'v-' + r.sample.verdict">{{ $t('map.urban.viab_' + r.sample.verdict) }}</span>
              </div>
            </div>
          </article>
        </section>

        <!-- Section B: adjudication scenarios -->
        <section v-if="data.scenarios && data.scenarios.length" class="space-y-2">
          <h2 class="text-sm font-semibold text-neutral-800 dark:text-neutral-200">{{ $t('map.urban.val_scenarios_heading') }}</h2>
          <div v-for="(s, i) in data.scenarios" :key="i" class="urban-val-scenario">
            <span class="urban-val-scenario-label">{{ s.label }}</span>
            <span class="urban-val-scenario-ctx">
              {{ s.subcategoria !== s.categoria ? s.categoria + ' / ' + s.subcategoria : s.categoria }}
              · {{ $t('map.urban.types.' + s.use_type, s.use_type) }}
            </span>
            <span class="urban-val-verdict" :class="'v-' + s.verdict">{{ $t('map.urban.viab_' + s.verdict) }}</span>
          </div>
        </section>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ShieldAlert, ClipboardCheck, CheckCircle2, AlertTriangle } from 'lucide-vue-next'

const { t, locale } = useI18n()
const authStore = useAuthStore()

const municipio = ref('caminha')
const data = ref<any>(null)
const loading = ref(true)
const error = ref('')
const forbidden = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  forbidden.value = false
  try {
    await authStore.ensureToken()
    data.value = await $fetch(`/api/v1/geo/urban/validation/${municipio.value}`, {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
  } catch (e: any) {
    const status = e?.status ?? e?.statusCode ?? e?.response?.status
    if (status === 401 || status === 403) forbidden.value = true
    else error.value = e?.data?.detail || e?.message || 'Error'
  } finally {
    loading.value = false
  }
}

// The checkbox reflects the viewer's own live confirmation — a stale one (rule
// changed since) renders unchecked so ticking it re-signs against the new values.
function isConfirmedByMe(r: any) {
  return (r.signoffs || []).some((s: any) => s.mine && !s.stale)
}

async function toggleConfere(r: any, ev: Event) {
  const confere = (ev.target as HTMLInputElement).checked
  try {
    await authStore.ensureToken()
    const resp: any = await $fetch(`/api/v1/geo/urban/validation/${municipio.value}/signoff`, {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: { categoria: r.categoria, subcategoria: r.subcategoria, confere },
    })
    r.signoffs = resp.signoffs
  } catch (e: any) {
    ;(ev.target as HTMLInputElement).checked = !confere  // revert on failure
    error.value = e?.data?.detail || e?.message || 'Error'
  }
}

function fmtM2(v: number | null, approx: boolean) {
  if (v == null) return '—'
  const n = new Intl.NumberFormat(locale.value).format(Math.round(v))
  return `${approx ? '≈ ' : ''}${n} m²`
}
function fmtIU(v: number | null, isMax: boolean) {
  if (v == null) return t('map.urban.val_not_fixed')
  return (isMax ? '≤ ' : '') + v
}
function fmtDate(iso: string) {
  try { return new Date(iso).toLocaleString(locale.value) } catch { return iso }
}

onMounted(load)
</script>

<style scoped>
.urban-val-icon {
  display: flex; align-items: center; justify-content: center;
  width: 2.25rem; height: 2.25rem; border-radius: 0.6rem; flex-shrink: 0;
  background: rgba(59, 130, 246, 0.14); color: #2563eb;
}
.dark .urban-val-icon { color: #60a5fa; }

.urban-val-meta {
  display: flex; flex-wrap: wrap; gap: 0.25rem 1rem;
  font-size: 0.72rem; color: #6b7280;
}
.urban-val-diploma { font-size: 0.68rem; color: #9ca3af; }

.urban-val-disclaimer {
  font-size: 0.72rem; line-height: 1.5;
  padding: 0.6rem 0.8rem; border-radius: 0.55rem;
  background: rgba(180, 83, 9, 0.09); color: #b45309;
  border: 1px solid rgba(180, 83, 9, 0.2);
}
.dark .urban-val-disclaimer { color: #fbbf24; background: rgba(180, 83, 9, 0.14); }

.urban-val-card {
  border: 1px solid rgba(0, 0, 0, 0.08); border-radius: 0.7rem;
  padding: 0.85rem 0.95rem; background: #fff;
}
.dark .urban-val-card { background: #171717; border-color: rgba(255, 255, 255, 0.08); }

.urban-val-card-head {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 0.75rem; font-size: 0.85rem; margin-bottom: 0.55rem;
}
.urban-val-art {
  margin-left: 0.5rem; font-size: 0.68rem; color: #9ca3af;
  white-space: nowrap; font-variant-numeric: tabular-nums;
}
.urban-val-confere {
  display: inline-flex; align-items: center; gap: 0.35rem;
  font-size: 0.7rem; color: #6b7280; cursor: pointer; flex-shrink: 0; user-select: none;
}
.urban-val-confere input { width: 1rem; height: 1rem; accent-color: #16a34a; }

.urban-val-signers {
  display: flex; flex-wrap: wrap; gap: 0.35rem 0.55rem; margin-bottom: 0.55rem;
}
.urban-val-signer {
  display: inline-flex; align-items: center; gap: 0.3rem;
  font-size: 0.7rem; font-weight: 600; padding: 0.12rem 0.5rem; border-radius: 0.4rem;
  background: rgba(21, 128, 61, 0.12); color: #15803d; font-variant-numeric: tabular-nums;
}
.dark .urban-val-signer { color: #4ade80; background: rgba(21, 128, 61, 0.16); }
.urban-val-signer.is-stale { background: rgba(180, 83, 9, 0.13); color: #b45309; }
.dark .urban-val-signer.is-stale { color: #fbbf24; background: rgba(180, 83, 9, 0.18); }

.urban-val-block { margin-top: 0.5rem; }
.urban-val-blabel {
  font-size: 0.62rem; text-transform: uppercase; letter-spacing: 0.04em;
  color: #9ca3af; margin-bottom: 0.28rem;
}
.urban-val-chips { display: flex; flex-wrap: wrap; gap: 0.35rem; align-items: center; }
.urban-val-chip {
  font-size: 0.72rem; padding: 0.12rem 0.5rem; border-radius: 0.4rem;
  background: rgba(0, 0, 0, 0.05); color: #374151; font-variant-numeric: tabular-nums;
}
.dark .urban-val-chip { background: rgba(255, 255, 255, 0.07); color: #d1d5db; }
.urban-val-chip.is-ok { background: rgba(21, 128, 61, 0.12); color: #15803d; }
.urban-val-chip.is-no { background: rgba(185, 28, 28, 0.12); color: #b91c1c; }
.dark .urban-val-chip.is-ok { color: #4ade80; }
.dark .urban-val-chip.is-no { color: #f87171; }

.urban-val-usos { font-size: 0.72rem; color: #6b7280; margin-top: 0.4rem; }

.urban-val-quote {
  font-size: 0.75rem; line-height: 1.55; color: #4b5563;
  border-left: 2px solid rgba(37, 99, 235, 0.35); padding: 0.15rem 0 0.15rem 0.65rem;
}
.dark .urban-val-quote { color: #9ca3af; }

.urban-val-verdict {
  font-size: 0.72rem; font-weight: 600; padding: 0.12rem 0.5rem; border-radius: 0.4rem;
}
.urban-val-verdict.v-edificavel { background: rgba(21, 128, 61, 0.12); color: #15803d; }
.urban-val-verdict.v-condicionado { background: rgba(180, 83, 9, 0.13); color: #b45309; }
.urban-val-verdict.v-nao_edificavel { background: rgba(185, 28, 28, 0.12); color: #b91c1c; }
.urban-val-verdict.v-sem_dados { background: rgba(107, 114, 128, 0.13); color: #6b7280; }
.dark .urban-val-verdict.v-edificavel { color: #4ade80; }
.dark .urban-val-verdict.v-condicionado { color: #fbbf24; }
.dark .urban-val-verdict.v-nao_edificavel { color: #f87171; }

.urban-val-scenario {
  display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem;
  padding: 0.5rem 0.7rem; border-radius: 0.55rem;
  border: 1px solid rgba(0, 0, 0, 0.06); background: rgba(0, 0, 0, 0.015);
}
.dark .urban-val-scenario { border-color: rgba(255, 255, 255, 0.06); background: rgba(255, 255, 255, 0.02); }
.urban-val-scenario-label { font-size: 0.76rem; font-weight: 600; color: #374151; }
.dark .urban-val-scenario-label { color: #e5e7eb; }
.urban-val-scenario-ctx { font-size: 0.7rem; color: #9ca3af; flex: 1 1 auto; }
</style>
