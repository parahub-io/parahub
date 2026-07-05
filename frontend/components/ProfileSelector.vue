<template>
  <div class="relative" ref="dropdownRef">
    <!-- Profile Selector Button -->
    <button
      @click.stop="toggleDropdown"
      class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
      :class="{ 'bg-neutral-100 dark:bg-neutral-800': isOpen }"
    >
      <div class="flex flex-col items-start">
        <span class="text-sm font-medium text-neutral-900 dark:text-neutral-100">{{ activeProfileName }}</span>
      </div>
      <ChevronDown
        class="w-4 h-4 text-neutral-500 dark:text-neutral-400"
        :class="[
          { 'rotate-180': isOpen },
          animationEnabled ? 'transition-transform duration-200' : ''
        ]"
      />
    </button>

    <!-- Dropdown Menu -->
    <Transition
      :enter-active-class="animationEnabled ? 'transition ease-out duration-100' : ''"
      :enter-from-class="animationEnabled ? 'transform opacity-0 scale-95' : ''"
      :enter-to-class="animationEnabled ? 'transform opacity-100 scale-100' : ''"
      :leave-active-class="animationEnabled ? 'transition ease-in duration-75' : ''"
      :leave-from-class="animationEnabled ? 'transform opacity-100 scale-100' : ''"
      :leave-to-class="animationEnabled ? 'transform opacity-0 scale-95' : ''"
    >
      <div
        v-if="isOpen"
        class="absolute right-0 mt-2 w-80 bg-white dark:bg-neutral-900 rounded-lg shadow-lg border border-neutral-200 dark:border-neutral-700 z-50"
        @click.stop
      >
        <!-- Authenticated User Menu -->
        <template v-if="authStore.isAuthenticated">
          <!-- Menu Items (Authenticated) -->
          <div class="p-2">
            <NuxtLink
              :to="localePath('/profile')"
              @click="isOpen = false"
              class="w-full flex items-center gap-2 px-3 py-2 text-sm rounded-md transition-colors"
              :class="route.path === '/profile' || route.path.startsWith('/profile/') ? 'bg-primary/10 text-neutral-900 dark:bg-primary/20 dark:text-neutral-100' : 'text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800'"
            >
              <Settings class="w-4 h-4" />
              {{ $t('profiles.settings') || 'Settings' }}
            </NuxtLink>


            <NuxtLink
              :to="localePath('/contracts')"
              @click="isOpen = false"
              class="w-full flex items-center gap-2 px-3 py-2 text-sm rounded-md transition-colors"
              :class="route.path === '/contracts' ? 'bg-primary/10 text-neutral-900 dark:bg-primary/20 dark:text-neutral-100' : 'text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800'"
            >
              <FileText class="w-4 h-4" />
              {{ $t('nav.contracts') || 'Contracts' }}
            </NuxtLink>

            <NuxtLink
              :to="localePath('/iot')"
              @click="isOpen = false"
              class="w-full flex items-center gap-2 px-3 py-2 text-sm rounded-md transition-colors"
              :class="route.path === '/iot' ? 'bg-primary/10 text-neutral-900 dark:bg-primary/20 dark:text-neutral-100' : 'text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800'"
            >
              <Cpu class="w-4 h-4" />
              {{ $t('nav.iot') || 'IoT' }}
            </NuxtLink>

            <NuxtLink
              :to="localePath('/projects')"
              @click="isOpen = false"
              class="w-full flex items-center gap-2 px-3 py-2 text-sm rounded-md transition-colors"
              :class="route.path === '/projects' ? 'bg-primary/10 text-neutral-900 dark:bg-primary/20 dark:text-neutral-100' : 'text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800'"
            >
              <FolderGit class="w-4 h-4" />
              {{ $t('nav.projects') || 'Projects' }}
            </NuxtLink>

            <div class="border-t border-neutral-200 dark:border-neutral-700 my-2"></div>

            <!-- Information & Legal -->
            <NuxtLink
              :to="localePath('/about')"
              @click="isOpen = false"
              class="w-full flex items-center gap-2 px-3 py-2 text-sm rounded-md transition-colors"
              :class="route.path.startsWith('/about') ? 'bg-primary/10 text-neutral-900 dark:bg-primary/20 dark:text-neutral-100' : 'text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800'"
            >
              <Info class="w-4 h-4" />
              {{ $t('about.title') || 'About' }}
            </NuxtLink>

            <div class="border-t border-neutral-200 dark:border-neutral-700 my-2"></div>

            <button
              @click="handleLogout"
              class="w-full flex items-center gap-2 px-3 py-2 text-sm text-error hover:bg-error-50 dark:hover:bg-error-900/20 rounded-md transition-colors"
            >
              <LogOut class="w-4 h-4" />
              {{ $t('profiles.logout') || 'Logout' }}
            </button>
          </div>
        </template>

        <!-- Guest Menu -->
        <template v-else>
          <div class="p-2">
            <!-- Login / Register Button -->
            <NuxtLink
              :to="localePath('/login')"
              @click="isOpen = false"
              class="w-full btn-secondary gap-2 px-4 py-2.5 mb-2 text-sm rounded-md"
            >
              <Lock class="w-4 h-4" />
              {{ $t('auth.login') || 'Login / Register' }}
            </NuxtLink>

            <div class="border-t border-neutral-200 dark:border-neutral-700 my-2"></div>

            <!-- Information & Legal -->
            <NuxtLink
              :to="localePath('/about')"
              @click="isOpen = false"
              class="w-full flex items-center gap-2 px-3 py-2 text-sm rounded-md transition-colors"
              :class="route.path.startsWith('/about') ? 'bg-primary/10 text-neutral-900 dark:bg-primary/20 dark:text-neutral-100' : 'text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800'"
            >
              <Info class="w-4 h-4" />
              {{ $t('about.title') || 'About' }}
            </NuxtLink>
          </div>
        </template>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '~/stores/auth'
import { ChevronDown, Check, Plus, Settings, Key, Cpu, LogOut, Info, FileText, FolderGit, Lock, Users, Trash2 } from 'lucide-vue-next'

const authStore = useAuthStore()
const router = useRouter()
const localePath = useLocalePath()
const route = useRoute()
const { t, locale } = useI18n()

const isOpen = ref(false)
// Check animation preference from active profile
// Default to true if not explicitly set to false
const animationEnabled = computed(() => {
  const value = authStore.activeProfile?.animation_enabled
  // If animation_enabled is explicitly false, return false
  // Otherwise (undefined, null, true) return true (default behavior)
  return value !== false
})
const showCreateDialog = ref(false)
const creatingProfile = ref(false)
const createError = ref('')
const showDeleteDialog = ref(false)
const deletingProfile = ref(false)
const deleteError = ref('')
const dropdownRef = ref<HTMLElement | null>(null)

// Success dialog
const showSuccessDialog = ref(false)
const createdProfileName = ref('')
const createdProfileHna = ref('')
const successMessage = computed(() => {
  const type = t('profiles.pseudonymous') || 'Pseudonymous'
  return t('profiles.createSuccessMessage', { type }) || `Your ${type.toLowerCase()} profile has been created and activated.`
})

const newProfile = ref({
  local_name: '',
  display_name: '',
})

const activeProfileName = computed(() => {
  if (!authStore.isAuthenticated) {
    return t('profiles.guest') || 'Guest'
  }
  return authStore.activeProfile?.display_name || authStore.user?.profile?.display_name || 'Profile'
})

const activeProfileType = computed(() => {
  if (!authStore.isAuthenticated) {
    return t('profiles.notLoggedIn') || 'Not logged in'
  }
  const type = authStore.activeProfile?.profile_type || authStore.user?.profile?.profile_type || 'PERSONAL'
  const labels: Record<string, string> = {
    'PERSONAL': t('profiles.personal'),
    'PSEUDONYMOUS': t('profiles.pseudonymous')
  }
  return labels[type] || type
})

// Helper computed properties for current profile type and primary status
const currentProfileType = computed(() => {
  return authStore.activeProfile?.profile_type || authStore.user?.profile?.profile_type || 'PERSONAL'
})

const currentProfileIsPrimary = computed(() => {
  return authStore.activeProfile?.is_primary ?? authStore.user?.profile?.is_primary ?? true
})

function getProfileTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    'PERSONAL': t('profiles.personal'),
    'PSEUDONYMOUS': t('profiles.pseudonymous')
  }
  return labels[type] || type
}

async function handleSwitchProfile(profileId: string) {
  if (profileId === authStore.activeProfile?.id) {
    isOpen.value = false
    return
  }

  try {
    await authStore.switchProfile(profileId)
    isOpen.value = false

    // Optionally reload page to refresh data
    // window.location.reload()
  } catch (error: any) {
    console.error('Failed to switch profile:', error)
    alert('Failed to switch profile: ' + (error.message || 'Unknown error'))
  }
}

async function handleCreateProfile() {
  creatingProfile.value = true
  createError.value = ''

  try {
    const data: any = {
      local_name: newProfile.value.local_name,
      display_name: newProfile.value.display_name
    }

    const createdProfile = await authStore.createProfile(data)

    // Store created profile info for success dialog
    createdProfileName.value = createdProfile.display_name
    createdProfileHna.value = createdProfile.hna

    // Reset form
    newProfile.value = {
      local_name: '',
      display_name: '',
    }

    // Close create dialog and show success
    showCreateDialog.value = false
    showSuccessDialog.value = true
  } catch (error: any) {
    console.error('Failed to create profile:', error)
    createError.value = error.data?.message || error.message || 'Failed to create profile'
  } finally {
    creatingProfile.value = false
  }
}

function handleGoToProfile() {
  showSuccessDialog.value = false
  router.push(localePath('/profile'))
}

function toggleDropdown() {
  isOpen.value = !isOpen.value
}

// Handle clicks outside to close dropdown
function handleClickOutside(event: MouseEvent) {
  if (dropdownRef.value && !dropdownRef.value.contains(event.target as Node)) {
    isOpen.value = false
  }
}

// Load profiles on mount
onMounted(async () => {
  // Only fetch if user is authenticated AND has a valid profile
  if (authStore.isAuthenticated && authStore.user?.profile) {
    try {
      await authStore.fetchManageableProfiles()
    } catch (error) {
      // Silently ignore - component will work with default profile
    }
  }

  // Add click outside listener
  if (process.client) {
    document.addEventListener('click', handleClickOutside)
  }
})

// Cleanup on unmount
onUnmounted(() => {
  if (process.client) {
    document.removeEventListener('click', handleClickOutside)
  }
})

// Logout handler
async function handleLogout() {
  isOpen.value = false
  try {
    await authStore.logout()
  } catch (error) {
    console.error('Logout error:', error)
  }
  // Hard redirect ensures fresh SSR render with anonymous state
  window.location.href = localePath('/')
}

// Delete profile handler
async function handleDeleteProfile() {
  if (!authStore.activeProfile) return

  deletingProfile.value = true
  deleteError.value = ''

  try {
    const profileId = authStore.activeProfile.id
    await authStore.deleteProfile(profileId)

    // Close dialog
    showDeleteDialog.value = false

  } catch (error: any) {
    console.error('Failed to delete profile:', error)
    deleteError.value = error.data?.message || error.message || t('profiles.deleteError') || 'Failed to delete profile'
  } finally {
    deletingProfile.value = false
  }
}
</script>
