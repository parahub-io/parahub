<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  Star, Heart, Zap, Shield, AlertTriangle, Check, X, Info,
  Bell, Settings, Search, Plus, Trash2, Download, Upload,
  ChevronRight, Mail, Eye, EyeOff, Calendar, Clock,
  CheckCircle, AlertCircle, XCircle, Loader2,
  Sun, Moon, Package, FileText, MapPin, LogOut,
} from 'lucide-vue-next'

const colorMode = useColorMode()

definePageMeta({ layout: 'default' })

// Interactive state
const activeUnderlineTab = ref('overview')
const activePillsTab = ref('lightning')
const activeIconTab = ref('send')
const activeFullTab = ref('all')
const loadingBtn = ref(false)
const toggleValue = ref(false)
const checkboxValue = ref(false)
const inputValue = ref('')
const selectValue = ref('')
const textareaValue = ref('')
const showDismissAlert = ref(true)
const demoPaginationPage = ref(3)
const demoLoading = ref(false)

function simulateFetch() {
  demoLoading.value = true
  setTimeout(() => { demoLoading.value = false }, 2000)
}

function simulateLoading() {
  loadingBtn.value = true
  setTimeout(() => { loadingBtn.value = false }, 2000)
}

// ── Confirm patterns demo ──
const showDeleteModal = ref(false)
const showWarningModal = ref(false)
const deleteConfirmPending = ref(false)
let deleteConfirmTimer: ReturnType<typeof setTimeout> | null = null

function handleTwoTapDelete() {
  if (!deleteConfirmPending.value) {
    deleteConfirmPending.value = true
    deleteConfirmTimer = setTimeout(() => {
      deleteConfirmPending.value = false
      deleteConfirmTimer = null
    }, 3000)
    return
  }
  if (deleteConfirmTimer) clearTimeout(deleteConfirmTimer)
  deleteConfirmPending.value = false
  // action executed
}

const colorScales = [
  { name: 'Primary', prefix: 'primary' },
  { name: 'Secondary', prefix: 'secondary' },
  { name: 'Success', prefix: 'success' },
  { name: 'Warning', prefix: 'warning' },
  { name: 'Error', prefix: 'error' },
  { name: 'Neutral', prefix: 'neutral' },
]

const shades = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900]

const buttonVariants = ['primary', 'secondary', 'success', 'warning', 'error', 'outline', 'outline-warning', 'outline-error', 'ghost'] as const
const badgeVariants = ['primary', 'secondary', 'success', 'warning', 'error', 'neutral'] as const
const badgeTypes = ['solid', 'soft', 'outline', 'dot'] as const

const underlineTabs = [
  { id: 'overview', label: 'Overview' },
  { id: 'details', label: 'Details', badge: 3 },
  { id: 'settings', label: 'Settings', icon: Settings },
  { id: 'disabled', label: 'History' },
]

const pillsTabs = [
  { id: 'lightning', label: 'Lightning' },
  { id: 'onchain', label: 'On-chain' },
  { id: 'spark', label: 'Spark' },
]

const iconTabs = [
  { id: 'send', label: 'Send', icon: Upload },
  { id: 'receive', label: 'Receive', icon: Download },
  { id: 'history', label: 'History', icon: Clock },
]

const fullWidthTabs = [
  { id: 'all', label: 'All', badge: 42 },
  { id: 'active', label: 'Active', badge: 12 },
  { id: 'pending', label: 'Pending', badge: 5 },
  { id: 'completed', label: 'Completed' },
]

const activeNavTab = ref('feed')
const navTabs = [
  { id: 'feed', label: 'Feed', icon: Star, to: '#' },
  { id: 'history', label: 'History', icon: Clock, to: '#' },
  { id: 'settings', label: 'Settings', icon: Settings, to: '#' },
]

// ── Pattern Constructor ──
const patternMode = ref<'grid' | 'phyllotaxis' | 'r2'>('grid')
const patternOpacity = ref(0.05)
const gridTileSize = ref(60)
const gridLogoScale = ref(0.22)
const phyllCount = ref(600)
const phyllSpread = ref(9)
const phyllLogoSize = ref(12)
const phyllXStretch = ref(1.8)
const phyllRotation = ref(false)
const phyllCenterY = ref(150)
const phyllSizeGrowth = ref(0.85)

const LOGO_PATH = 'm 91.961093,113.16417 c -5.172666,5.17267 -5.172666,13.65582 0,18.8285 l 2.275966,2.27596 6.621011,-4.13808 -3.517415,-3.51748 c -2.275965,-2.27595 -2.275965,-6.00027 0,-8.06931 2.275973,-2.27595 6.000285,-2.27595 8.069355,0 2.27597,2.27596 2.27597,6.00028 0,8.06931 l -23.587337,23.79426 -4.138123,-4.13808 c -5.172666,-5.17267 -13.655824,-5.17267 -18.82849,0 -5.172658,5.1726 -5.172658,13.65582 0,18.82842 5.172666,5.17267 13.655824,5.17267 18.82849,0 l 3.517404,-3.31048 -6.414097,-4.34499 -2.482877,2.48287 c -2.275973,2.27596 -6.000289,2.27596 -8.06935,0 -2.069062,-2.27603 -2.275974,-6.00035 -0.20692,-8.2763 2.275966,-2.27596 6.000281,-2.27596 8.069351,0 l 22.759701,22.75973 3.724316,-1.65528 -6.621,6.62103 c -5.172666,5.17268 -5.172666,13.65583 0,18.8285 5.172658,5.17267 13.655822,5.17267 18.828482,0 5.17266,-5.17267 5.17266,-13.65582 0,-18.8285 l -2.27597,-2.27595 -6.621,4.13807 3.5174,3.51748 c 2.27597,2.27595 2.27597,6.00027 0,8.06931 -2.27597,2.27596 -6.000281,2.27596 -8.06935,0 -2.275966,-2.27596 -2.275966,-6.00028 0,-8.06931 l 23.79424,-23.79426 4.13813,4.13808 c 5.17266,5.17267 13.65582,5.17267 18.82849,0 5.17265,-5.1726 5.17265,-13.65582 0,-18.82842 -5.17267,-5.17267 -13.65583,-5.17267 -18.82849,0 l -3.51741,3.5174 6.4141,4.13807 2.27597,-2.27595 c 2.27597,-2.27596 6.00028,-2.27596 8.06935,0 2.27597,2.27595 2.27597,6.00027 0,8.06939 -2.27597,2.27595 -6.00029,2.27595 -8.06935,0 l -22.5528,-22.55282 -3.93122,1.65528 6.82791,-6.82795 c 5.17266,-5.17268 5.17266,-13.65583 0,-18.8285 -5.17266,-5.17267 -13.655824,-5.17267 -18.828482,0 z m 26.897837,45.72631 -4.34504,-1.86212 -13.0351,13.03506 -17.17324,-17.38014 4.138131,1.8622 13.242009,-13.24198 z'

const GOLDEN_ANGLE_RAD = 137.508 * (Math.PI / 180)
const PLASTIC = 1.32471795724474602596

const patternElements = computed(() => {
  if (patternMode.value === 'grid') return []
  const els: { x: number; y: number; s: number; rot: number }[] = []
  const count = phyllCount.value
  const size = phyllLogoSize.value
  const useRot = phyllRotation.value

  const growth = phyllSizeGrowth.value
  const sqrtCount = Math.sqrt(count)

  if (patternMode.value === 'phyllotaxis') {
    const spread = phyllSpread.value
    const xStretch = phyllXStretch.value
    const cy = phyllCenterY.value
    for (let i = 1; i <= count; i++) {
      const a = i * GOLDEN_ANGLE_RAD
      const r = spread * Math.sqrt(i)
      const t = Math.sqrt(i) / sqrtCount          // 0→1 from center to edge
      const s = size * ((1 - growth) + growth * t) // grows outward
      els.push({
        x: 500 + r * Math.cos(a) * xStretch,
        y: cy + r * Math.sin(a),
        s,
        rot: useRot ? (i * 137.508) % 360 : 0,
      })
    }
  } else {
    for (let i = 1; i <= count; i++) {
      const t = i / count
      const s = size * ((1 - growth) + growth * t)
      els.push({
        x: ((0.5 + i / PLASTIC) % 1) * 1000,
        y: ((0.5 + i / (PLASTIC * PLASTIC)) % 1) * 400,
        s,
        rot: useRot ? (i * 137.508) % 360 : 0,
      })
    }
  }
  return els
})

const gridTransform = computed(() => {
  const s = gridLogoScale.value
  const half = gridTileSize.value / 2
  return `translate(${half},${half}) scale(${s}) translate(-46.5,-46.4)`
})
</script>

<template>
  <div class="max-w-5xl mx-auto px-4 py-8 space-y-16">
    <header class="flex items-start justify-between gap-4">
      <div>
        <h1 class="text-3xl font-bold text-neutral-900 dark:text-neutral-50 mb-2">
          Parahub Design System
        </h1>
        <p class="text-neutral-500 dark:text-neutral-400 text-lg">
          Component library and visual reference. All components support light/dark mode.
        </p>
      </div>
      <button
        class="flex-shrink-0 mt-1 p-2 rounded-lg border border-neutral-300 dark:border-neutral-600 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
        :aria-label="colorMode.value === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'"
        @click="colorMode.preference = colorMode.value === 'dark' ? 'light' : 'dark'"
      >
        <Sun v-if="colorMode.value === 'dark'" class="w-5 h-5 text-neutral-400" />
        <Moon v-else class="w-5 h-5 text-neutral-500" />
      </button>
    </header>

    <!-- ═══════════════════════════════════════════ -->
    <!-- COLORS -->
    <!-- ═══════════════════════════════════════════ -->
    <section>
      <h2 class="text-2xl font-semibold text-neutral-900 dark:text-neutral-50 mb-6">Colors</h2>
      <div class="space-y-4">
        <div v-for="scale in colorScales" :key="scale.prefix">
          <p class="text-sm font-medium text-neutral-600 dark:text-neutral-400 mb-2">{{ scale.name }}</p>
          <div class="flex gap-1">
            <div
              v-for="shade in shades"
              :key="shade"
              class="flex-1 h-10 rounded first:rounded-l-lg last:rounded-r-lg relative group"
              :class="`bg-${scale.prefix}-${shade}`"
            >
              <span class="absolute inset-0 flex items-center justify-center text-[10px] font-mono opacity-0 group-hover:opacity-100 transition-opacity"
                :class="shade >= 500 ? 'text-white' : 'text-neutral-900'"
              >
                {{ shade }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════ -->
    <!-- TYPOGRAPHY -->
    <!-- ═══════════════════════════════════════════ -->
    <section>
      <h2 class="text-2xl font-semibold text-neutral-900 dark:text-neutral-50 mb-6">Typography</h2>
      <div class="space-y-4 card p-6">
        <div>
          <span class="text-xs text-neutral-400 font-mono">h1 — text-3xl font-bold</span>
          <h1 class="text-3xl font-bold text-neutral-900 dark:text-neutral-50">Page Title</h1>
        </div>
        <div>
          <span class="text-xs text-neutral-400 font-mono">h2 — text-2xl font-semibold</span>
          <h2 class="text-2xl font-semibold text-neutral-900 dark:text-neutral-50">Section Heading</h2>
        </div>
        <div>
          <span class="text-xs text-neutral-400 font-mono">h3 — text-xl font-semibold</span>
          <h3 class="text-xl font-semibold text-neutral-900 dark:text-neutral-50">Card Title</h3>
        </div>
        <div>
          <span class="text-xs text-neutral-400 font-mono">body — text-base</span>
          <p class="text-base text-neutral-700 dark:text-neutral-300">Regular body text for content and descriptions.</p>
        </div>
        <div>
          <span class="text-xs text-neutral-400 font-mono">small — text-sm text-neutral-500</span>
          <p class="text-sm text-neutral-500">Secondary text, hints, and metadata.</p>
        </div>
        <div>
          <span class="text-xs text-neutral-400 font-mono">caption — text-xs text-neutral-400</span>
          <p class="text-xs text-neutral-400">Timestamps, labels, and fine print.</p>
        </div>
        <div>
          <span class="text-xs text-neutral-400 font-mono">mono — font-mono text-sm</span>
          <p class="font-mono text-sm text-neutral-700 dark:text-neutral-300">01K7M4MDWPFZ5WQ4A5GRPPVZR2</p>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════ -->
    <!-- BUTTONS -->
    <!-- ═══════════════════════════════════════════ -->
    <section>
      <h2 class="text-2xl font-semibold text-neutral-900 dark:text-neutral-50 mb-6">Buttons</h2>

      <!-- Variants -->
      <div class="space-y-6">
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Variants</h3>
          <div class="flex flex-wrap gap-3">
            <UiButton v-for="v in buttonVariants" :key="v" :variant="v">
              {{ v.charAt(0).toUpperCase() + v.slice(1) }}
            </UiButton>
          </div>
        </div>

        <!-- Sizes -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Sizes</h3>
          <div class="flex items-center gap-3">
            <UiButton size="sm">Small</UiButton>
            <UiButton size="md">Medium</UiButton>
            <UiButton size="lg">Large</UiButton>
          </div>
        </div>

        <!-- With icons -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">With Icons</h3>
          <div class="flex flex-wrap items-center gap-3">
            <UiButton :icon="Plus">Create</UiButton>
            <UiButton variant="error" :icon="Trash2">Delete</UiButton>
            <UiButton variant="outline" :icon="Download">Export</UiButton>
            <UiButton variant="ghost" :icon="Settings">Settings</UiButton>
          </div>
        </div>

        <!-- Icon-only -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Icon Only</h3>
          <div class="flex items-center gap-3">
            <UiButton :icon="Star" icon-only size="sm" aria-label="Star" />
            <UiButton :icon="Heart" icon-only variant="error" aria-label="Heart" />
            <UiButton :icon="Bell" icon-only variant="outline" size="lg" aria-label="Bell" />
            <UiButton :icon="Search" icon-only variant="ghost" aria-label="Search" />
          </div>
        </div>

        <!-- States -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">States</h3>
          <div class="flex flex-wrap items-center gap-3">
            <UiButton :loading="loadingBtn" @click="simulateLoading">
              {{ loadingBtn ? 'Loading...' : 'Click to load' }}
            </UiButton>
            <UiButton disabled>Disabled</UiButton>
            <UiButton variant="outline" disabled>Disabled Outline</UiButton>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════ -->
    <!-- TABS -->
    <!-- ═══════════════════════════════════════════ -->
    <section>
      <h2 class="text-2xl font-semibold text-neutral-900 dark:text-neutral-50 mb-6">Tabs</h2>
      <div class="space-y-8">
        <!-- Underline -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Underline (default)</h3>
          <UiTabs v-model="activeUnderlineTab" :tabs="underlineTabs" />
          <div class="mt-4 card p-4">
            <p class="text-sm text-neutral-600 dark:text-neutral-400">
              Active tab: <strong class="text-neutral-900 dark:text-neutral-100">{{ activeUnderlineTab }}</strong>
            </p>
          </div>
        </div>

        <!-- Pills -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Pills</h3>
          <div class="max-w-sm">
            <UiTabs v-model="activePillsTab" :tabs="pillsTabs" variant="pills" />
          </div>
          <div class="mt-4 card p-4">
            <p class="text-sm text-neutral-600 dark:text-neutral-400">
              Active tab: <strong class="text-neutral-900 dark:text-neutral-100">{{ activePillsTab }}</strong>
            </p>
          </div>
        </div>

        <!-- With icons -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">With Icons</h3>
          <UiTabs v-model="activeIconTab" :tabs="iconTabs" />
        </div>

        <!-- Full width with badges -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Full Width + Badges</h3>
          <UiTabs v-model="activeFullTab" :tabs="fullWidthTabs" full-width />
        </div>

        <!-- Nav (route-based) -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Nav (route-based, NuxtLink)</h3>
          <UiTabs v-model="activeNavTab" :tabs="navTabs" variant="nav" />
          <p class="mt-2 text-xs text-neutral-400">For page-level navigation with separate routes (e.g. /ads, /ads/history, /ads/settings)</p>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════ -->
    <!-- BADGES -->
    <!-- ═══════════════════════════════════════════ -->
    <section>
      <h2 class="text-2xl font-semibold text-neutral-900 dark:text-neutral-50 mb-6">Badges</h2>
      <div class="space-y-6">
        <!-- Solid -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Solid</h3>
          <div class="flex flex-wrap gap-2">
            <UiBadge v-for="v in badgeVariants" :key="v" :variant="v" type="solid">{{ v }}</UiBadge>
          </div>
        </div>

        <!-- Soft -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Soft</h3>
          <div class="flex flex-wrap gap-2">
            <UiBadge v-for="v in badgeVariants" :key="v" :variant="v" type="soft">{{ v }}</UiBadge>
          </div>
        </div>

        <!-- Outline -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Outline</h3>
          <div class="flex flex-wrap gap-2">
            <UiBadge v-for="v in badgeVariants" :key="v" :variant="v" type="outline">{{ v }}</UiBadge>
          </div>
        </div>

        <!-- Dot -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Dot Indicators</h3>
          <div class="flex items-center gap-4">
            <span v-for="v in badgeVariants" :key="v" class="flex items-center gap-1.5 text-sm text-neutral-600 dark:text-neutral-400">
              <UiBadge :variant="v" type="dot" :aria-label="`${v} status`" />
              {{ v }}
            </span>
          </div>
        </div>

        <!-- Sizes -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Sizes</h3>
          <div class="flex items-center gap-3">
            <UiBadge variant="primary" type="solid" size="sm">Small</UiBadge>
            <UiBadge variant="primary" type="solid" size="md">Medium</UiBadge>
            <UiBadge variant="primary" type="solid" size="lg">Large</UiBadge>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════ -->
    <!-- CARDS -->
    <!-- ═══════════════════════════════════════════ -->
    <section>
      <h2 class="text-2xl font-semibold text-neutral-900 dark:text-neutral-50 mb-6">Cards</h2>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <!-- Default -->
        <div class="card p-6">
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-50 mb-2">Default Card</h3>
          <p class="text-sm text-neutral-500">Standard card with <code class="text-xs bg-neutral-200 dark:bg-neutral-700 px-1 rounded">.card</code> class.</p>
        </div>

        <!-- Accented -->
        <div class="card p-6 border-primary">
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-50 mb-2">Accented Card</h3>
          <p class="text-sm text-neutral-500">Add <code class="text-xs bg-neutral-200 dark:bg-neutral-700 px-1 rounded">border-primary</code> for emphasis.</p>
        </div>

        <!-- Interactive -->
        <div class="card p-6 hover:border-primary transition-colors cursor-pointer">
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-50 mb-2">Interactive Card</h3>
          <p class="text-sm text-neutral-500">Hover to see the effect. Use for clickable items.</p>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════ -->
    <!-- FORM INPUTS -->
    <!-- ═══════════════════════════════════════════ -->
    <section>
      <h2 class="text-2xl font-semibold text-neutral-900 dark:text-neutral-50 mb-6">Form Inputs</h2>
      <div class="card p-6 space-y-6 max-w-lg">
        <!-- Text input -->
        <div>
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
            Username
          </label>
          <input
            v-model="inputValue"
            type="text"
            placeholder="Enter username"
            class="w-full px-3 py-2 bg-white dark:bg-neutral-900 border border-neutral-300 dark:border-neutral-600 rounded-lg text-sm text-neutral-900 dark:text-neutral-100 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          />
          <p class="mt-1 text-xs text-neutral-400">3-30 characters, letters and numbers only.</p>
        </div>

        <!-- Select -->
        <div>
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
            Category
          </label>
          <select
            v-model="selectValue"
            class="w-full px-3 py-2 bg-white dark:bg-neutral-900 border border-neutral-300 dark:border-neutral-600 rounded-lg text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          >
            <option value="" disabled>Select a category</option>
            <option value="goods">Goods</option>
            <option value="services">Services</option>
            <option value="skills">Skills</option>
          </select>
        </div>

        <!-- Textarea -->
        <div>
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
            Description
          </label>
          <textarea
            v-model="textareaValue"
            rows="3"
            placeholder="Describe your item..."
            class="w-full px-3 py-2 bg-white dark:bg-neutral-900 border border-neutral-300 dark:border-neutral-600 rounded-lg text-sm text-neutral-900 dark:text-neutral-100 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent resize-y"
          />
        </div>

        <!-- Checkbox -->
        <div class="flex items-center gap-2">
          <input
            id="design-checkbox"
            v-model="checkboxValue"
            type="checkbox"
            class="w-4 h-4 rounded border-neutral-300 dark:border-neutral-600 text-primary focus:outline-none focus:ring-0 bg-white dark:bg-neutral-900"
          />
          <label for="design-checkbox" class="text-sm text-neutral-700 dark:text-neutral-300">
            I agree to the terms
          </label>
        </div>

        <!-- Toggle -->
        <div class="flex items-center justify-between">
          <span class="text-sm text-neutral-700 dark:text-neutral-300">Enable notifications</span>
          <button
            type="button"
            role="switch"
            :aria-checked="toggleValue"
            class="relative w-10 h-6 rounded-full transition-colors focus:outline-none"
            :class="toggleValue ? 'bg-primary' : 'bg-neutral-300 dark:bg-neutral-600'"
            @click="toggleValue = !toggleValue"
          >
            <span
              class="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform"
              :class="toggleValue ? 'translate-x-4' : 'translate-x-0'"
            />
          </button>
        </div>

        <!-- Error state -->
        <div>
          <label class="block text-sm font-medium text-error mb-1">
            Email (error state)
          </label>
          <input
            type="email"
            value="invalid-email"
            class="w-full px-3 py-2 bg-white dark:bg-neutral-900 border border-error rounded-lg text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-error focus:border-transparent"
          />
          <p class="mt-1 text-xs text-error">Please enter a valid email address.</p>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════ -->
    <!-- ALERTS -->
    <!-- ═══════════════════════════════════════════ -->
    <section>
      <h2 class="text-2xl font-semibold text-neutral-900 dark:text-neutral-50 mb-6">Alerts</h2>
      <div class="space-y-6">
        <!-- With title -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">With Title</h3>
          <div class="space-y-3">
            <UiAlert variant="info" title="Information">
              Your profile is visible to verified members only.
            </UiAlert>
            <UiAlert variant="success" title="Success">
              Contract signed and recorded on the blockchain.
            </UiAlert>
            <UiAlert variant="warning" title="Warning">
              Your Web of Trust level is below the required threshold.
            </UiAlert>
            <UiAlert variant="error" title="Error">
              Transaction failed. Please check your wallet balance.
            </UiAlert>
          </div>
        </div>

        <!-- Without title -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Without Title</h3>
          <div class="space-y-3">
            <UiAlert variant="info">Your session will expire in 5 minutes.</UiAlert>
            <UiAlert variant="success">Payment received successfully.</UiAlert>
            <UiAlert variant="warning">You have unsaved changes.</UiAlert>
            <UiAlert variant="error">Network connection lost.</UiAlert>
          </div>
        </div>

        <!-- Dismissible -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Dismissible</h3>
          <UiAlert v-if="showDismissAlert" variant="info" title="Tip" dismissible @dismiss="showDismissAlert = false">
            Click the X to dismiss this alert.
          </UiAlert>
          <p v-else class="text-sm text-neutral-400">Alert dismissed. Reload page to see again.</p>
        </div>

        <!-- No icon -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">No Icon</h3>
          <UiAlert variant="warning" :icon="null">
            This alert has no icon — use <code class="text-xs bg-warning-100 dark:bg-warning-900/40 px-1 rounded">:icon="null"</code> to disable.
          </UiAlert>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════ -->
    <!-- PAGE HEADER -->
    <!-- ═══════════════════════════════════════════ -->
    <section>
      <h2 class="text-2xl font-semibold text-neutral-900 dark:text-neutral-50 mb-6">Page Header</h2>
      <p class="text-sm text-neutral-500 mb-6">
        Standard header for all list/CRUD pages. Uses <code class="text-xs bg-neutral-200 dark:bg-neutral-700 px-1 rounded">PageHeader</code> component.
        Container: <code class="text-xs bg-neutral-200 dark:bg-neutral-700 px-1 rounded">max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6</code>
      </p>
      <div class="space-y-6">
        <!-- Title only -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Title only</h3>
          <div class="card p-4">
            <PageHeader title="Barter Chains" />
          </div>
        </div>

        <!-- Title + subtitle -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Title + subtitle</h3>
          <div class="card p-4">
            <PageHeader title="Shipping" subtitle="Send packages through trusted community members" />
          </div>
        </div>

        <!-- Title + create (navigation) -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Title + create button (link)</h3>
          <div class="card p-4">
            <PageHeader title="Events" create-to="#" create-label="Create event" />
          </div>
        </div>

        <!-- Title + subtitle + create (modal) -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Title + subtitle + create button (modal)</h3>
          <div class="card p-4">
            <PageHeader title="Safety Groups" subtitle="Neighborhood mutual aid" create-label="Create group" />
          </div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════ -->
    <!-- EMPTY STATE -->
    <!-- ═══════════════════════════════════════════ -->
    <section>
      <h2 class="text-2xl font-semibold text-neutral-900 dark:text-neutral-50 mb-6">Empty State</h2>
      <p class="text-sm text-neutral-500 mb-6">
        Shown when a list has no items. Icon <code class="text-xs bg-neutral-200 dark:bg-neutral-700 px-1 rounded">w-12 h-12</code>,
        wrapper <code class="text-xs bg-neutral-200 dark:bg-neutral-700 px-1 rounded">text-center py-12</code>,
        heading <code class="text-xs bg-neutral-200 dark:bg-neutral-700 px-1 rounded">h3 text-lg font-semibold</code>.
      </p>
      <div class="space-y-6">
        <!-- Standard -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Standard (no CTA)</h3>
          <div class="card">
            <div class="text-center py-12">
              <FileText class="w-12 h-12 mx-auto text-neutral-300 dark:text-neutral-600 mb-4" />
              <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-2">No contracts yet</h3>
              <p class="text-sm text-neutral-500 dark:text-neutral-400">Contracts you create or receive will appear here.</p>
            </div>
          </div>
        </div>

        <!-- With CTA -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">With CTA button</h3>
          <div class="card">
            <div class="text-center py-12">
              <Calendar class="w-12 h-12 mx-auto text-neutral-300 dark:text-neutral-600 mb-4" />
              <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-2">No events found</h3>
              <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-4">Be the first to organize a community event.</p>
              <UiButton variant="primary" size="sm" :icon="Plus">Create event</UiButton>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════ -->
    <!-- LOADING STATE -->
    <!-- ═══════════════════════════════════════════ -->
    <section>
      <h2 class="text-2xl font-semibold text-neutral-900 dark:text-neutral-50 mb-6">Loading State</h2>
      <p class="text-sm text-neutral-500 mb-6">
        Spinner: <code class="text-xs bg-neutral-200 dark:bg-neutral-700 px-1 rounded">h-12 w-12 border-2 border-neutral-300 border-t-neutral-900</code>.
        Always include <code class="text-xs bg-neutral-200 dark:bg-neutral-700 px-1 rounded">role="status" aria-live="polite"</code>.
      </p>
      <div class="space-y-6">
        <!-- Standard -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Standard spinner</h3>
          <div class="card">
            <div class="text-center py-12" role="status" aria-live="polite">
              <div class="inline-block animate-spin rounded-full h-12 w-12 border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-white" aria-hidden="true"></div>
              <span class="sr-only">Loading...</span>
            </div>
          </div>
        </div>

        <!-- Interactive demo -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Interactive (click to simulate)</h3>
          <div class="card">
            <div v-if="demoLoading" class="text-center py-12" role="status" aria-live="polite">
              <div class="inline-block animate-spin rounded-full h-12 w-12 border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-white" aria-hidden="true"></div>
              <span class="sr-only">Loading...</span>
            </div>
            <div v-else class="text-center py-12">
              <UiButton variant="outline" size="sm" @click="simulateFetch">Simulate loading (2s)</UiButton>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════ -->
    <!-- PAGINATION -->
    <!-- ═══════════════════════════════════════════ -->
    <section>
      <h2 class="text-2xl font-semibold text-neutral-900 dark:text-neutral-50 mb-6">Pagination</h2>
      <p class="text-sm text-neutral-500 mb-6">
        Numbered buttons: <code class="text-xs bg-neutral-200 dark:bg-neutral-700 px-1 rounded">w-9 h-9 rounded-lg border</code>.
        Active: dark bg. Inactive: neutral with hover.
      </p>
      <div class="card p-6">
        <div class="flex justify-center gap-1">
          <button
            v-for="page in 7"
            :key="page"
            @click="demoPaginationPage = page"
            :class="demoPaginationPage === page
              ? 'bg-secondary text-white'
              : 'bg-white dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400 hover:bg-primary-100 dark:hover:bg-primary-900/40'"
            class="w-9 h-9 rounded-lg border border-neutral-200 dark:border-neutral-700 text-sm font-medium transition-colors"
          >
            {{ page }}
          </button>
        </div>
        <p class="text-center text-xs text-neutral-400 mt-3">Page {{ demoPaginationPage }} of 7</p>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════ -->
    <!-- ITEM LISTS -->
    <!-- ═══════════════════════════════════════════ -->
    <section>
      <h2 class="text-2xl font-semibold text-neutral-900 dark:text-neutral-50 mb-6">Item Lists</h2>
      <p class="text-sm text-neutral-500 mb-6">
        Flush pattern: shared outer border, <code class="text-xs bg-neutral-200 dark:bg-neutral-700 px-1 rounded">divide-y</code> separators,
        yellow hover <code class="text-xs bg-neutral-200 dark:bg-neutral-700 px-1 rounded">hover:bg-primary-100</code>. No per-item borders or gaps.
      </p>
      <div class="max-w-lg">
        <div class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
          <button class="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors">
            <MapPin class="w-5 h-5 text-neutral-400 shrink-0" />
            <div class="flex-1 min-w-0">
              <div class="text-sm font-medium text-neutral-900 dark:text-neutral-100">Rossio Station</div>
              <div class="text-xs text-neutral-500 dark:text-neutral-400">Lisbon, Portugal</div>
            </div>
            <ChevronRight class="w-4 h-4 text-neutral-400 shrink-0" />
          </button>
          <button class="w-full flex items-center gap-3 px-4 py-3 text-left bg-primary-100 dark:bg-primary-900/40 transition-colors">
            <MapPin class="w-5 h-5 text-neutral-400 shrink-0" />
            <div class="flex-1 min-w-0">
              <div class="text-sm font-medium text-neutral-900 dark:text-neutral-100">Cais do Sodre</div>
              <div class="text-xs text-neutral-500 dark:text-neutral-400">Lisbon, Portugal — selected</div>
            </div>
            <ChevronRight class="w-4 h-4 text-neutral-400 shrink-0" />
          </button>
          <button class="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors">
            <MapPin class="w-5 h-5 text-neutral-400 shrink-0" />
            <div class="flex-1 min-w-0">
              <div class="text-sm font-medium text-neutral-900 dark:text-neutral-100">Santa Apolonia</div>
              <div class="text-xs text-neutral-500 dark:text-neutral-400">Lisbon, Portugal</div>
            </div>
            <ChevronRight class="w-4 h-4 text-neutral-400 shrink-0" />
          </button>
          <button class="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors">
            <MapPin class="w-5 h-5 text-neutral-400 shrink-0" />
            <div class="flex-1 min-w-0">
              <div class="text-sm font-medium text-neutral-900 dark:text-neutral-100">Oriente</div>
              <div class="text-xs text-neutral-500 dark:text-neutral-400">Lisbon, Portugal</div>
            </div>
            <ChevronRight class="w-4 h-4 text-neutral-400 shrink-0" />
          </button>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════ -->
    <!-- STATUS PAGE (HERO SECTION) -->
    <!-- ═══════════════════════════════════════════ -->
    <section>
      <h2 class="text-2xl font-semibold text-neutral-900 dark:text-neutral-50 mb-6">Status Page (Hero Section)</h2>
      <p class="text-sm text-neutral-500 mb-6">
        Full-page centered messages: auth required, not found, error, success.
        Icon <code class="text-xs bg-neutral-200 dark:bg-neutral-700 px-1 rounded">w-8 h-8</code> inside a
        <code class="text-xs bg-neutral-200 dark:bg-neutral-700 px-1 rounded">w-16 h-16 rounded-full</code> colored circle.
        Different from Empty State — these communicate a <strong>status or action result</strong>, not "no data".
      </p>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <!-- Success -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Success</h3>
          <div class="card">
            <div class="text-center py-12">
              <div class="w-16 h-16 mx-auto mb-4 rounded-full bg-success-100 dark:bg-success-900/30 flex items-center justify-center">
                <Check class="w-8 h-8 text-success-600 dark:text-success-400" />
              </div>
              <h2 class="text-xl font-semibold text-neutral-900 dark:text-neutral-100 mb-2">Account created</h2>
              <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-4 max-w-sm mx-auto">Your account has been created successfully. You can now sign in.</p>
              <UiButton variant="primary">Sign in</UiButton>
            </div>
          </div>
        </div>

        <!-- Error -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Error / Not Found</h3>
          <div class="card">
            <div class="text-center py-12">
              <div class="w-16 h-16 mx-auto mb-4 rounded-full bg-error-100 dark:bg-error-900/30 flex items-center justify-center">
                <AlertTriangle class="w-8 h-8 text-error-600 dark:text-error-400" />
              </div>
              <h2 class="text-xl font-semibold text-neutral-900 dark:text-neutral-100 mb-2">Page not found</h2>
              <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-4 max-w-sm mx-auto">The page you're looking for doesn't exist or has been moved.</p>
              <UiButton variant="primary">Go home</UiButton>
            </div>
          </div>
        </div>

        <!-- Warning / Auth Required -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Warning / Auth Required</h3>
          <div class="card">
            <div class="text-center py-12">
              <div class="w-16 h-16 mx-auto mb-4 rounded-full bg-warning-100 dark:bg-warning-900/30 flex items-center justify-center">
                <Shield class="w-8 h-8 text-warning-600 dark:text-warning-400" />
              </div>
              <h2 class="text-xl font-semibold text-neutral-900 dark:text-neutral-100 mb-2">Sign in required</h2>
              <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-4 max-w-sm mx-auto">You need to sign in to access this feature.</p>
              <UiButton variant="primary">Sign in</UiButton>
            </div>
          </div>
        </div>

        <!-- Info / Onboarding -->
        <div>
          <h3 class="text-sm font-medium text-neutral-500 mb-3">Info / Onboarding</h3>
          <div class="card">
            <div class="text-center py-12">
              <div class="w-16 h-16 mx-auto mb-4 rounded-full bg-secondary-100 dark:bg-secondary-900/30 flex items-center justify-center">
                <Zap class="w-8 h-8 text-secondary-600 dark:text-secondary-400" />
              </div>
              <h2 class="text-xl font-semibold text-neutral-900 dark:text-neutral-100 mb-2">Set up your wallet</h2>
              <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-4 max-w-sm mx-auto">Configure your Lightning wallet to start sending and receiving payments.</p>
              <UiButton variant="primary">Get started</UiButton>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════ -->
    <!-- FORM PAGE LAYOUT -->
    <!-- ═══════════════════════════════════════════ -->
    <section>
      <h2 class="text-2xl font-semibold text-neutral-900 dark:text-neutral-50 mb-6">Form Page Layout</h2>
      <p class="text-sm text-neutral-500 mb-6">
        Create/edit pages use <code class="text-xs bg-neutral-200 dark:bg-neutral-700 px-1 rounded">max-w-2xl</code> (narrower than list pages).
        Back link with ArrowLeft, section cards for multi-section forms, full-width submit button.
      </p>
      <div class="max-w-2xl mx-auto">
        <div class="card p-6">
          <!-- Back link -->
          <a href="#" class="text-link text-sm flex items-center gap-1 mb-4" @click.prevent>
            <ChevronRight class="w-4 h-4 rotate-180" />
            Back to items
          </a>

          <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mb-6">Create new item</h1>

          <!-- Section card -->
          <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6 space-y-4 mb-6">
            <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">Basic information</h2>
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">Title</label>
              <input type="text" placeholder="Enter title..." class="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary focus:border-transparent" />
            </div>
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">Description</label>
              <textarea rows="3" placeholder="Describe your item..." class="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary focus:border-transparent"></textarea>
            </div>
          </div>

          <!-- Second section -->
          <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6 space-y-4 mb-6">
            <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">Pricing</h2>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">Price</label>
                <input type="number" placeholder="0" class="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary focus:border-transparent" />
              </div>
              <div>
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">Currency</label>
                <select class="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary focus:border-transparent">
                  <option>EUR</option>
                  <option>BTC (sats)</option>
                </select>
              </div>
            </div>
          </div>

          <!-- Submit -->
          <UiButton variant="primary" class="w-full">Create item</UiButton>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════ -->
    <!-- DETAIL PAGE LAYOUT -->
    <!-- ═══════════════════════════════════════════ -->
    <section>
      <h2 class="text-2xl font-semibold text-neutral-900 dark:text-neutral-50 mb-6">Detail Page Layout</h2>
      <p class="text-sm text-neutral-500 mb-6">
        Single entity pages use <code class="text-xs bg-neutral-200 dark:bg-neutral-700 px-1 rounded">max-w-4xl</code>.
        Back link to list, header with title + actions, content in <code class="text-xs bg-neutral-200 dark:bg-neutral-700 px-1 rounded">.card</code> sections.
      </p>
      <div class="max-w-4xl mx-auto">
        <div class="card p-6">
          <!-- Back link -->
          <a href="#" class="inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100 mb-4" @click.prevent>
            <ChevronRight class="w-4 h-4 rotate-180" />
            Events
          </a>

          <!-- Header: title + actions -->
          <div class="flex items-start justify-between gap-4 mb-6">
            <div>
              <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">Community Meetup</h1>
              <p class="text-sm text-neutral-500 dark:text-neutral-400 mt-1">March 28, 2026 · Lisbon, Portugal</p>
            </div>
            <div class="flex items-center gap-2">
              <UiButton variant="outline" size="sm" :icon="Settings">Edit</UiButton>
            </div>
          </div>

          <!-- Content sections -->
          <div class="space-y-4">
            <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4">
              <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-2">
                <Info class="w-5 h-5 text-neutral-400" />
                Details
              </h2>
              <p class="text-sm text-neutral-600 dark:text-neutral-400">
                Join us for a community meetup to discuss the future of decentralized civic infrastructure.
                We'll cover topics like liquid democracy, P2P energy, and mesh networking.
              </p>
            </div>

            <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4">
              <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-2">
                <MapPin class="w-5 h-5 text-neutral-400" />
                Location
              </h2>
              <p class="text-sm text-neutral-600 dark:text-neutral-400">Rua Augusta 42, Lisbon</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════ -->
    <!-- INLINE SPINNERS -->
    <!-- ═══════════════════════════════════════════ -->
    <section>
      <h2 class="text-2xl font-semibold text-neutral-900 dark:text-neutral-50 mb-6">Inline Spinners</h2>
      <p class="text-sm text-neutral-500 mb-6">
        All spinners use <strong>neutral colors</strong>
        <code class="text-xs bg-neutral-200 dark:bg-neutral-700 px-1 rounded">border-neutral-300 border-t-neutral-900</code>.
        Yellow (<code class="text-xs bg-neutral-200 dark:bg-neutral-700 px-1 rounded">border-primary</code>) is invisible on light backgrounds. Only size varies by context.
      </p>
      <div class="flex items-end gap-8">
        <div class="text-center">
          <div class="card p-6 flex items-center justify-center mb-2">
            <div class="animate-spin rounded-full h-4 w-4 border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-white"></div>
          </div>
          <p class="text-xs text-neutral-500">h-4 w-4<br />Inline with text</p>
        </div>
        <div class="text-center">
          <div class="card p-6 flex items-center justify-center mb-2">
            <div class="animate-spin rounded-full h-6 w-6 border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-white"></div>
          </div>
          <p class="text-xs text-neutral-500">h-6 w-6<br />In panel / cell</p>
        </div>
        <div class="text-center">
          <div class="card p-6 flex items-center justify-center mb-2">
            <div class="animate-spin rounded-full h-12 w-12 border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-white"></div>
          </div>
          <p class="text-xs text-neutral-500">h-12 w-12<br />Page-level</p>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════ -->
    <!-- PATTERN CONSTRUCTOR -->
    <!-- ═══════════════════════════════════════════ -->
    <section>
      <h2 class="text-2xl font-semibold text-neutral-900 dark:text-neutral-50 mb-6">Hero Pattern Constructor</h2>

      <!-- Controls -->
      <div class="card p-6 space-y-5">
        <!-- Mode -->
        <div>
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">Pattern Type</label>
          <select v-model="patternMode" class="w-full px-3 py-2 bg-white dark:bg-neutral-900 border border-neutral-300 dark:border-neutral-600 rounded-lg text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent">
            <option value="grid">Grid (tiling)</option>
            <option value="phyllotaxis">Phyllotaxis (sunflower)</option>
            <option value="r2">R2 Quasi-Random (golden ratio 2D)</option>
          </select>
        </div>

        <!-- Opacity (all modes) -->
        <div>
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
            Opacity: <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ patternOpacity }}</span>
          </label>
          <input type="range" v-model.number="patternOpacity" min="0.01" max="0.3" step="0.01" class="w-full" />
        </div>

        <!-- Grid controls -->
        <template v-if="patternMode === 'grid'">
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Tile Size: <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ gridTileSize }}px</span>
            </label>
            <input type="range" v-model.number="gridTileSize" min="30" max="120" step="5" class="w-full" />
          </div>
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Logo Scale: <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ gridLogoScale }}</span>
            </label>
            <input type="range" v-model.number="gridLogoScale" min="0.08" max="0.5" step="0.02" class="w-full" />
          </div>
        </template>

        <!-- Phyllotaxis / R2 controls -->
        <template v-if="patternMode !== 'grid'">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                Count: <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ phyllCount }}</span>
              </label>
              <input type="range" v-model.number="phyllCount" min="50" max="1200" step="10" class="w-full" />
            </div>
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                Logo Size: <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ phyllLogoSize }}</span>
              </label>
              <input type="range" v-model.number="phyllLogoSize" min="4" max="30" step="1" class="w-full" />
            </div>
          </div>

          <template v-if="patternMode === 'phyllotaxis'">
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                  Spread: <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ phyllSpread }}</span>
                </label>
                <input type="range" v-model.number="phyllSpread" min="3" max="25" step="0.5" class="w-full" />
              </div>
              <div>
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                  X Stretch: <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ phyllXStretch }}</span>
                </label>
                <input type="range" v-model.number="phyllXStretch" min="1" max="3.5" step="0.1" class="w-full" />
              </div>
            </div>
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                Center Y: <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ phyllCenterY }}</span>
              </label>
              <input type="range" v-model.number="phyllCenterY" min="50" max="350" step="10" class="w-full" />
            </div>
          </template>

          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Size Growth: <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ phyllSizeGrowth }}</span>
              <span class="text-neutral-400 text-xs ml-1">(0 = uniform, 1 = tiny→large from center)</span>
            </label>
            <input type="range" v-model.number="phyllSizeGrowth" min="0" max="1" step="0.05" class="w-full" />
          </div>

          <div class="flex items-center gap-2">
            <input id="pattern-rot" v-model="phyllRotation" type="checkbox" class="w-4 h-4 rounded border-neutral-300 dark:border-neutral-600 text-primary focus:outline-none focus:ring-0 bg-white dark:bg-neutral-900" />
            <label for="pattern-rot" class="text-sm text-neutral-700 dark:text-neutral-300">Golden angle rotation (137.5° per element)</label>
          </div>
        </template>
      </div>

      <!-- Preview -->
      <div class="relative overflow-hidden rounded-xl mt-6" style="background-color: #ffe216; height: 300px;">
        <div class="absolute inset-0 overflow-hidden pointer-events-none" :style="{ opacity: patternOpacity }">
          <!-- Grid mode -->
          <svg v-if="patternMode === 'grid'" class="absolute inset-0 w-full h-full" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <pattern id="preview-logo-grid" :width="gridTileSize" :height="gridTileSize" patternUnits="userSpaceOnUse">
                <g :transform="gridTransform">
                  <g transform="translate(-54.976568,-109.28466)">
                    <path :d="LOGO_PATH" fill="black" />
                  </g>
                </g>
              </pattern>
            </defs>
            <rect width="100%" height="100%" fill="url(#preview-logo-grid)" />
          </svg>

          <!-- Phyllotaxis / R2 mode -->
          <svg v-else class="absolute inset-0 w-full h-full" viewBox="0 0 1000 400" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <symbol id="preview-ph-logo" viewBox="0 0 93 93">
                <g transform="translate(-54.976568,-109.28466)">
                  <path :d="LOGO_PATH" fill="black" />
                </g>
              </symbol>
            </defs>
            <use v-for="(c, i) in patternElements" :key="i" href="#preview-ph-logo"
              :x="c.x - c.s / 2" :y="c.y - c.s / 2" :width="c.s" :height="c.s"
              :transform="c.rot ? `rotate(${c.rot},${c.x},${c.y})` : undefined" />
          </svg>
        </div>

        <!-- Center logo overlay -->
        <div class="absolute inset-0 flex items-center justify-center z-10">
          <img src="/logo.svg" alt="Parahub" class="h-16 w-16" />
        </div>
      </div>

      <!-- Current values -->
      <div class="mt-4 card p-4">
        <p class="text-xs font-mono text-neutral-500 dark:text-neutral-400">
          <template v-if="patternMode === 'grid'">
            mode: grid, tileSize: {{ gridTileSize }}, logoScale: {{ gridLogoScale }}, opacity: {{ patternOpacity }}
          </template>
          <template v-else-if="patternMode === 'phyllotaxis'">
            mode: phyllotaxis, count: {{ phyllCount }}, spread: {{ phyllSpread }}, logoSize: {{ phyllLogoSize }}, xStretch: {{ phyllXStretch }}, centerY: {{ phyllCenterY }}, sizeGrowth: {{ phyllSizeGrowth }}, rotation: {{ phyllRotation }}, opacity: {{ patternOpacity }}
          </template>
          <template v-else>
            mode: r2, count: {{ phyllCount }}, logoSize: {{ phyllLogoSize }}, sizeGrowth: {{ phyllSizeGrowth }}, rotation: {{ phyllRotation }}, opacity: {{ patternOpacity }}
          </template>
        </p>
      </div>
    </section>

    <!-- ═══════════ Destructive Confirmations ═══════════ -->
    <section>
      <h2 class="text-2xl font-semibold text-neutral-900 dark:text-neutral-50 mb-6">Destructive Confirmations</h2>
      <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-6">
        Never use native <code class="text-xs bg-neutral-200 dark:bg-neutral-700 px-1 rounded">confirm()</code> / <code class="text-xs bg-neutral-200 dark:bg-neutral-700 px-1 rounded">alert()</code>. Two patterns available:
      </p>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <!-- Two-Tap Pattern -->
        <div class="card p-6">
          <h3 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-1">Two-Tap (inline)</h3>
          <p class="text-xs text-neutral-500 dark:text-neutral-400 mb-4">For simple actions: logout, quick delete. First tap changes label, second executes. Auto-resets in 3s.</p>
          <div class="flex items-center gap-3">
            <UiButton
              :variant="deleteConfirmPending ? 'error' : 'outline-error'"
              size="sm"
              :icon="Trash2"
              @click="handleTwoTapDelete"
            >
              {{ deleteConfirmPending ? 'Sure?' : 'Delete' }}
            </UiButton>
            <span class="text-xs text-neutral-400">← try it</span>
          </div>
        </div>

        <!-- Confirm Modal Pattern -->
        <div class="card p-6">
          <h3 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-1">UiConfirmModal</h3>
          <p class="text-xs text-neutral-500 dark:text-neutral-400 mb-4">For actions needing context: what exactly is being deleted, consequences. Shows icon, title, message.</p>
          <div class="flex items-center gap-3">
            <UiButton variant="outline-error" size="sm" :icon="Trash2" @click="showDeleteModal = true">
              Delete item
            </UiButton>
            <UiButton variant="outline-warning" size="sm" :icon="AlertTriangle" @click="showWarningModal = true">
              Regenerate
            </UiButton>
          </div>
        </div>
      </div>

      <!-- Modals -->
      <UiConfirmModal
        v-model="showDeleteModal"
        title="Delete item"
        message="This action cannot be undone. The item and all associated data will be permanently removed."
        confirm-label="Delete"
        variant="error"
        :icon="Trash2"
        @confirm="showDeleteModal = false"
      />
      <UiConfirmModal
        v-model="showWarningModal"
        title="Regenerate token"
        message="The current invite link will stop working. Anyone with the old link will no longer be able to join."
        confirm-label="Regenerate"
        variant="warning"
        @confirm="showWarningModal = false"
      />
    </section>

    <footer class="text-center text-xs text-neutral-400 pt-8 pb-4">
      Parahub Design System v1.0
    </footer>
  </div>
</template>
