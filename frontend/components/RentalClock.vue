<script setup lang="ts">
// Live "current date & time" readout for the rental/booking pages — ticks every
// second so a renter can orient the availability windows against the present
// moment. Client-only (wrapped below) to avoid an SSR/hydration time mismatch.
// No leading icon: it sits opposite headings that already carry a Clock icon.
const props = defineProps<{
  // Optional IANA zone (e.g. the bookable's timezone). Omitted → viewer's local zone.
  timezone?: string
}>()

const { locale } = useI18n()

const now = ref(new Date())
let timer: ReturnType<typeof setInterval> | undefined

onMounted(() => {
  now.value = new Date()
  timer = setInterval(() => { now.value = new Date() }, 1000)
})
onBeforeUnmount(() => { if (timer) clearInterval(timer) })

const dateFmt = computed(() => new Intl.DateTimeFormat(locale.value, {
  weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
  ...(props.timezone ? { timeZone: props.timezone } : {}),
}))
const timeFmt = computed(() => new Intl.DateTimeFormat(locale.value, {
  hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  ...(props.timezone ? { timeZone: props.timezone } : {}),
}))

// Capitalize only the leading character — `text-transform: capitalize` would
// wrongly upper-case every word (ru month abbrev + the "г." year suffix).
const dateStr = computed(() => {
  const s = dateFmt.value.format(now.value)
  return s.charAt(0).toUpperCase() + s.slice(1)
})
const timeStr = computed(() => timeFmt.value.format(now.value))
</script>

<template>
  <ClientOnly>
    <!-- Yellow accent pill — dark text (yellow is unreadable as text per design system) -->
    <div class="inline-flex items-center gap-2 text-sm px-2.5 py-1 rounded-lg bg-primary text-neutral-900">
      <span>{{ dateStr }}</span>
      <!-- tabular-nums keeps the seconds from jittering the width each tick -->
      <span class="font-mono tabular-nums font-semibold">{{ timeStr }}</span>
    </div>
  </ClientOnly>
</template>
