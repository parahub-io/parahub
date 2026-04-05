<template>
  <Teleport to="body">
    <Transition name="update-banner">
      <div
        v-if="newVersionAvailable && !dismissed"
        class="fixed bottom-4 left-1/2 -translate-x-1/2 z-[100] flex items-center gap-3 px-4 py-2.5 rounded-lg shadow-lg border bg-secondary-50 dark:bg-secondary-900 border-secondary-300 dark:border-secondary-700"
      >
        <RefreshCw class="w-4 h-4 text-secondary dark:text-secondary-400 flex-shrink-0" />
        <span class="text-sm text-secondary-800 dark:text-secondary-200">
          {{ $t('update.new_version') }}
        </span>
        <button
          @click="reload"
          class="btn-secondary px-3 py-1 text-xs rounded-md"
        >
          {{ $t('update.refresh') }}
        </button>
        <button
          @click="dismissed = true"
          class="text-secondary-400 hover:text-secondary dark:hover:text-secondary-300 transition-colors"
          :aria-label="$t('common.cancel')"
        >
          <X class="w-4 h-4" />
        </button>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { RefreshCw, X } from 'lucide-vue-next'

const newVersionAvailable = useState('newVersionAvailable', () => false)
const dismissed = ref(false)

const reload = () => {
  window.location.reload()
}
</script>

<style scoped>
.update-banner-enter-active,
.update-banner-leave-active {
  transition: all 0.3s ease;
}

.update-banner-enter-from,
.update-banner-leave-to {
  opacity: 0;
  transform: translate(-50%, 100%);
}
</style>
