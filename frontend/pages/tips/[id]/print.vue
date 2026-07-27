<template>
  <div>
    <div v-if="!batch" class="p-8 text-center text-neutral-600">{{ $t('tips.batch.missing') }}</div>

    <template v-else>
      <div class="toolbar no-print">
        <NuxtLink :to="localePath(`/tips/${batch.id}`)">← {{ $t('tips.batch.back') }}</NuxtLink>
        <span>{{ $t('tips.print.hint') }}</span>
        <button type="button" @click="print">{{ $t('tips.batch.print') }}</button>
      </div>

      <div v-for="(page, p) in pages" :key="p" class="sheet">
        <article v-for="note in page" :key="note.code" class="note">
          <header class="n-head">
            <span class="n-mark" v-html="logo" />
            <span class="n-brand">parahub</span>
            <span class="n-kind">bitcoin tip</span>
          </header>
          <p class="n-message">{{ batch.message || $t('tips.print.defaultMessage') }}</p>
          <div class="n-amount">
            <div class="n-sats">{{ groupedSats }}<span class="n-unit">sats</span></div>
            <div class="n-fiat">≈ {{ batch.fiat }}</div>
            <div class="n-rate">{{ batch.rate }} · {{ $t('tips.print.issued') }} {{ issued }}</div>
          </div>
          <p class="n-about">{{ $t('tips.print.about') }}</p>
          <div class="n-claim">
            <div class="n-qr" v-html="qr[note.code]" />
            <div>
              <div class="n-scan">{{ $t('tips.print.scan') }}</div>
              <div class="n-url">parahub.io/t</div>
            </div>
          </div>
          <div class="n-code">{{ formatTipCode(note.code) }}</div>
          <footer class="n-foot">
            <span class="n-exp">{{ $t('tips.print.claimBefore') }} <b>{{ expires }}</b></span>
            <span class="n-return">{{ $t('tips.print.returns') }}</span>
          </footer>
          <span class="n-id">{{ String(note.index).padStart(3, '0') }}</span>
        </article>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { formatTipCode, tipClaimUrl } from '~/utils/tips'
import type { TipBatch } from '~/composables/useTipBatches'

// Standalone document: the printed sheet must not carry app chrome.
definePageMeta({ middleware: 'auth', layout: false })

const localePath = useLocalePath()
const route = useRoute()
const { t, locale } = useI18n()
const { get } = useTipBatches()

const batch = ref<TipBatch | undefined>()
const qr = ref<Record<string, string>>({})
const logo = ref('')

const NOTES_PER_SHEET = 9

const numbered = computed(() =>
  (batch.value?.notes ?? []).map((n, i) => ({ ...n, index: i + 1 })))

const pages = computed(() => {
  const out: (typeof numbered.value)[] = []
  for (let i = 0; i < numbered.value.length; i += NOTES_PER_SHEET) {
    out.push(numbered.value.slice(i, i + NOTES_PER_SHEET))
  }
  return out
})

const groupedSats = computed(() => (batch.value?.sats ?? 0).toLocaleString('en-US').replace(/,/g, ' '))
const fmtDate = (ms: number) => new Date(ms).toLocaleDateString(locale.value, { day: 'numeric', month: 'short', year: 'numeric' })
const issued = computed(() => batch.value ? fmtDate(batch.value.createdAt) : '')
const expires = computed(() => batch.value ? fmtDate(batch.value.createdAt + batch.value.expirySecs * 1000) : '')

const print = () => window.print()

onMounted(async () => {
  batch.value = get(String(route.params.id))
  if (!batch.value) return

  logo.value = await $fetch<string>('/logo.svg', { responseType: 'text' })
    .then(s => s.replace(/<\?xml[\s\S]*?\?>/, '').replace(/<!--[\s\S]*?-->/g, '')
      .replace(/\s+width="[^"]*"/, '').replace(/\s+height="[^"]*"/, '')
      .replace(/<svg/, '<svg fill="currentColor"'))
    .catch(() => '')

  const QRCode = (await import('qrcode')).default
  const origin = window.location.origin
  const entries = await Promise.all(batch.value.notes.map(async n => [
    n.code,
    await QRCode.toString(tipClaimUrl(n.code, origin), { type: 'svg', errorCorrectionLevel: 'M', margin: 0 }),
  ] as const))
  qr.value = Object.fromEntries(entries)
})

useHead({
  title: t('tips.print.title'),
  meta: [{ name: 'robots', content: 'noindex, nofollow' }],
})
</script>

<style>
/* Print-ready A4, 9 notes up. Mirrors public/print/tips.html — that file is the
   design reference, this one renders it with real secrets. Global (not scoped)
   so @page and the body reset apply. */
@page { size: A4; margin: 0; }

html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  color: #171717;
  background: #404040;
  margin: 0;
}

.toolbar {
  display: flex; align-items: center; gap: 16px; justify-content: center;
  padding: 16px; color: #fafafa; font-size: 14px;
}
.toolbar a { color: #FFE216; text-decoration: none; }
.toolbar button {
  background: #FFE216; color: #171717; border: 0; border-radius: 8px;
  padding: 8px 16px; font-weight: 700; cursor: pointer;
}

.sheet {
  width: 210mm; height: 297mm;
  background: #fff;
  padding: 6mm;
  display: grid;
  grid-template-columns: repeat(3, 64.6mm);
  grid-template-rows: repeat(3, 93.6mm);
  gap: 2mm;
  overflow: hidden;
  margin: 0 auto 24px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, .4);
  box-sizing: border-box;
}

@media print {
  body { background: #fff; }
  .no-print { display: none !important; }
  .sheet { margin: 0; box-shadow: none; break-after: page; }
  .sheet:last-child { break-after: auto; }
}

.note {
  position: relative;
  border: 0.3mm dashed #a3a3a3;
  display: flex; flex-direction: column;
  overflow: hidden;
  box-sizing: border-box;
}
.note > *:not(.n-foot):not(.n-id) { padding-left: 3.4mm; padding-right: 3.4mm; }
.note * { box-sizing: border-box; }

.n-head {
  display: flex; align-items: center; gap: 1.6mm;
  padding-top: 3mm; padding-bottom: 1.5mm;
  border-bottom: 0.8mm solid #FFE216;
  margin: 0;
}
.n-mark { width: 5mm; height: 5mm; display: block; color: #171717; }
.n-mark svg { width: 100%; height: 100%; display: block; }
.n-brand { font-size: 10pt; font-weight: 900; letter-spacing: -0.35pt; }
.n-kind {
  margin-left: auto; font-size: 6pt; font-weight: 800; text-transform: uppercase;
  letter-spacing: 0.5pt; color: #525252;
}

.n-message {
  font-size: 11pt; font-weight: 800; line-height: 1.15; letter-spacing: -0.2pt;
  padding-top: 2.4mm; padding-bottom: 2.2mm; margin: 0; hyphens: auto;
}

.n-amount {
  background: #FFFBE6; border-top: 0.25mm solid #F0DA4E; border-bottom: 0.25mm solid #F0DA4E;
  padding-top: 2.2mm; padding-bottom: 2.2mm;
}
.n-sats {
  font-size: 18pt; font-weight: 900; letter-spacing: -0.7pt; line-height: 1;
  display: flex; align-items: baseline; gap: 1.4mm;
}
.n-unit { font-size: 7.6pt; font-weight: 800; color: #525252; letter-spacing: 0; }
.n-fiat { font-size: 10pt; font-weight: 800; color: #4E4EC8; margin-top: 0.6mm; }
.n-rate { font-size: 5.6pt; color: #737373; margin-top: 0.9mm; }

.n-about {
  font-size: 5.8pt; line-height: 1.42; color: #525252;
  padding-top: 1.8mm; padding-bottom: 1.8mm;
  flex: 1 1 auto; min-height: 0; overflow: hidden; margin: 0;
}

.n-claim { display: flex; align-items: center; gap: 3mm; flex: none; }
.n-qr { width: 20mm; height: 20mm; flex: none; }
.n-qr svg { width: 100%; height: 100%; display: block; shape-rendering: crispEdges; }
.n-scan { font-size: 7.6pt; font-weight: 800; }
.n-url { font-size: 8.4pt; font-weight: 700; margin-top: 0.6mm; }

.n-code {
  font-family: ui-monospace, "SF Mono", "Cascadia Mono", Menlo, Consolas, monospace;
  font-size: 6.4pt; letter-spacing: 0.2pt; color: #404040;
  padding-top: 1.2mm; padding-bottom: 1.6mm;
  text-align: center; white-space: nowrap;
}

.n-foot { padding: 1.9mm 3.4mm 2.1mm; background: #171717; color: #fafafa; flex: none; }
.n-exp { display: block; font-size: 7pt; font-weight: 700; }
.n-exp b { color: #FFE216; }
.n-return { display: block; font-size: 5.5pt; line-height: 1.35; color: #d4d4d4; margin-top: 0.7mm; }

.n-id {
  position: absolute; top: 1mm; right: 1.6mm;
  font-size: 5pt; color: #a3a3a3; letter-spacing: 0.3pt;
}
</style>
