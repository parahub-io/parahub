<template>
  <div>
    <!-- Page title -->
    <Head>
      <Title>{{ $t('profile.title') }}</Title>
      <Meta name="description" :content="$t('profile.description')" />
    </Head>

    <h1 class="sr-only">{{ $t('profile.title') }}</h1>

    <div class="space-y-4">
      <!-- Profile Header (outside accordion) -->
      <ProfileHeader
        :user-h-n-a="userHNA"
      />

      <!-- Preferences (always visible, no accordion) -->
      <PreferencesSection
        :animation-enabled="animationEnabled"
        @update:animation-enabled="(val) => { animationEnabled = val }"
      />

      <!-- Profile Completion (hide when 100%, closed by default) -->
      <ProfileCompletionSection
        v-if="profileProgress < 100"
        :actions="profileActions"
        :open-sections="openSections"
        :animation-enabled="animationEnabled"
        :profile-progress="profileProgress"
        :completed-count="completedSectionsCount"
        :total-count="totalSectionsCount"
        :achievements="achievements"
        :graph-size="graphSize"
        @toggle="toggleSection"
        @action-click="handleActionClick"
      />

      <PhotoSection
        :open-sections="openSections"
        :status="sectionStatuses.about"
        :animation-enabled="animationEnabled"
        @toggle="toggleSection"
        @hash-loaded="(val) => { psychHashCompleted = val }"
      />

      <SecuritySection
        :open-sections="openSections"
        :status="sectionStatuses.security"
        :animation-enabled="animationEnabled"
        @toggle="toggleSection"
      />

      <LightningWalletSection
        :open-sections="openSections"
        :status="sectionStatuses.lightning"
        :animation-enabled="animationEnabled"
        @toggle="toggleSection"
        @wallet-configured="(val) => { lightningConfigured = val }"
      />

      <MigrationSection
        :open-sections="openSections"
        :animation-enabled="animationEnabled"
        @toggle="toggleSection"
      />

      <CivicSection
        :open-sections="openSections"
        :animation-enabled="animationEnabled"
        @toggle="toggleSection"
      />

      <DataPrivacySection
        :open-sections="openSections"
        :animation-enabled="animationEnabled"
        @toggle="toggleSection"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { usePGP } from '~/composables/usePGP'
import ProfileHeader from '@/components/profile/ProfileHeader.vue'
import ProfileCompletionSection, { type ProfileAction } from '@/components/profile/ProfileCompletionSection.vue'
import PreferencesSection from '@/components/profile/PreferencesSection.vue'
import PhotoSection from '@/components/profile/PhotoSection.vue'
import SecuritySection from '@/components/profile/SecuritySection.vue'
import LightningWalletSection from '@/components/profile/LightningWalletSection.vue'
import MigrationSection from '@/components/profile/MigrationSection.vue'
import CivicSection from '@/components/profile/CivicSection.vue'
import DataPrivacySection from '@/components/profile/DataPrivacySection.vue'

// Set page metadata
definePageMeta({
  middleware: 'auth',
  order: 5,
  keepalive: true  // Enable KeepAlive caching for instant switching
})

const authStore = useAuthStore()
const { t } = useI18n()
const { hasKeys: pgpHasKeys, loadKeys: pgpLoadKeys } = usePGP()

const userHNA = ref('')
const publicProfileUrl = ref('')
const profileCRI = ref('')

// Accordion state
const openSections = ref(['profile']) // Profile open by default, completion closed
const toggleSection = (section: string) => {
  const index = openSections.value.indexOf(section)
  if (index > -1) {
    openSections.value.splice(index, 1)
  } else {
    openSections.value.push(section)
  }
}

// Animation enabled preference (localStorage, shared with PreferencesSection)
const animationEnabled = useLocalPref('animation_enabled', true)

// Psycho-hash
const psychHashCompleted = ref(false)

// Lightning wallet
const lightningConfigured = ref(false)

// Achievements (for pentagon graph)
interface Achievement {
  category: string
  level: number
  progress: number
  next_threshold: number | null
}
const achievements = ref<Achievement[]>([])

// Responsive graph size
const graphSize = computed(() => {
  if (typeof window === 'undefined') return 300
  return window.innerWidth < 640 ? 200 : 300
})

// Status indicators (only for sections that need them)
const sectionStatuses = computed(() => ({
  security: { complete: pgpHasKeys.value, icon: pgpHasKeys.value ? 'check' : 'alert' },
  about: { complete: psychHashCompleted.value, icon: psychHashCompleted.value ? 'check' : 'minus' },
  lightning: { complete: lightningConfigured.value, icon: lightningConfigured.value ? 'check' : 'minus' }
}))

// Profile completion tracking
const totalSectionsCount = 3 // Security, Personality, Lightning
const completedSectionsCount = computed(() => {
  let count = 0
  if (pgpHasKeys.value) count++
  if (psychHashCompleted.value) count++
  if (lightningConfigured.value) count++
  return count
})

const profileProgress = computed(() => {
  return Math.round((completedSectionsCount.value / totalSectionsCount) * 100)
})

// Recommended actions
const profileActions = computed<ProfileAction[]>(() => {
  const actions: ProfileAction[] = []

  if (!pgpHasKeys.value) {
    actions.push({
      id: 'security',
      title: t('profile.actions.generate_pgp_keys', 'Сгенерировать PGP ключи'),
      description: t('profile.actions.generate_pgp_keys_desc', 'Необходимо для подписания сделок и верификаций'),
      completed: false,
      priority: 10
    })
  }

  if (!psychHashCompleted.value) {
    actions.push({
      id: 'about',
      title: t('profile.actions.add_psychhash', 'Добавить психо-хеш (4 слова)'),
      description: t('profile.actions.add_psychhash_desc', 'Публичный профиль для подбора in Web of Trust'),
      completed: false,
      priority: 7
    })
  }

  if (!lightningConfigured.value) {
    actions.push({
      id: 'lightning',
      title: t('profile.actions.configure_lightning', 'Настроить Lightning кошелёк'),
      description: t('profile.actions.configure_lightning_desc', 'Необходимо для получения платежей из рекламной системы'),
      completed: false,
      priority: 5
    })
  }

  return actions
})

const handleActionClick = (actionId: string) => {
  // Open the corresponding section
  if (!openSections.value.includes(actionId)) {
    openSections.value.push(actionId)
  }

  // Scroll to section
  nextTick(() => {
    const element = document.querySelector(`[data-section-id="${actionId}"]`)
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  })
}

// Deep-link: /profile?section=civic opens + scrolls to that section
const route = useRoute()
onMounted(() => {
  const section = route.query.section
  if (typeof section === 'string' && section) {
    handleActionClick(section)
  }
})

const loadUserCredentials = async () => {
  // Ensure we have a JWT token
  await authStore.ensureToken()
  if (!authStore.token) return

  // Try to get profile CRI from session (only available right after OAuth signup)
  try {
    const response = await $fetch('/api/v1/auth/user-credentials/', {
      credentials: 'include'
    })
    // Get profile CRI if available
    if (response.profile_id) {
      profileCRI.value = response.profile_id
    }
  } catch (error) {
    // Credentials not available (normal for existing users)
  }

  // Load profile to get CRI, HNA and preferences
  try {
    const profile = await $fetch('/api/v1/profiles/me/', {
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })

    // Set HNA from profile (e.g., charlie@parahub.io, NOT charlie@test.parahub.io)
    if (profile.hna) {
      userHNA.value = profile.hna
    }

    // Set ID and build public profile URL immediately
    if (profile.id) {
      profileCRI.value = profile.id
      const config = useRuntimeConfig()
      const baseUrl = config.public.siteUrl || 'https://parahub.io'
      // Use short URL with nickname (extract from HNA: nickname@domain)
      const nickname = profile.hna?.split('@')[0] || profile.id
      publicProfileUrl.value = `${baseUrl}/u/${nickname}`
    }
  } catch (error) {
    console.error('Failed to load profile:', error)
  }
}

const loadAchievements = async () => {
  try {
    await authStore.ensureToken()
    if (!authStore.token) return

    const data = await $fetch<{ achievements: Achievement[] }>('/api/v1/dashboard/game', {
      credentials: 'include',
      headers: {
        Authorization: `Bearer ${authStore.token}`
      }
    })

    if (data.achievements) {
      achievements.value = data.achievements
    }
  } catch (error) {
    console.error('Error loading achievements:', error)
  }
}

// Load user on mount
onMounted(async () => {
  // Ensure JWT token before any authenticated requests
  await authStore.ensureToken()

  // Refresh user profile data from API (SSR may have stale data without photos)
  try {
    await authStore.fetchUser()
  } catch (error) {
    // User not authenticated - middleware should redirect
    return
  }

  // Load PGP keys status
  await pgpLoadKeys()

  // Load user credentials
  await loadUserCredentials()

  // Load achievements
  await loadAchievements()

  // Wait for next tick to ensure DOM is fully rendered
  await nextTick()
})
</script>
