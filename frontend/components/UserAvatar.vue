<template>
  <div class="relative overflow-hidden" :style="{ width: `${size}px`, height: `${size}px` }">
    <!-- User uploaded photo -->
    <img
      v-if="photoUrl"
      :src="photoUrl"
      :alt="name || 'User avatar'"
      class="w-full h-full object-cover rounded-full"
    />

    <!-- Generated avatar (jdenticon) -->
    <svg
      v-else
      ref="avatarRef"
      :width="size"
      :height="size"
      :data-jdenticon-value="seed"
      class="rounded-full"
    ></svg>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue'
import * as jdenticon from 'jdenticon'

interface Props {
  photoUrl?: string | null
  name?: string
  seed?: string  // hna or profile id - используется для генерации
  size?: number
}

const props = withDefaults(defineProps<Props>(), {
  size: 64
})

// Use hna as seed if provided, otherwise fallback to name
const seedValue = computed(() => props.seed || props.name || 'anonymous')

const avatarRef = ref<SVGElement>()

// Configure jdenticon colors (warm paper-like theme)
jdenticon.configure({
  lightness: {
    color: [0.40, 0.80],
    grayscale: [0.30, 0.90]
  },
  saturation: {
    color: 0.50,
    grayscale: 0.00
  },
  backColor: '#FEF3C7' // Warm amber background
})

// Update avatar when mounted or seed changes
function updateAvatar() {
  if (avatarRef.value && !props.photoUrl) {
    jdenticon.update(avatarRef.value, seedValue.value)
  }
}

onMounted(() => {
  updateAvatar()
})

watch(() => seedValue.value, () => {
  updateAvatar()
})

watch(() => props.photoUrl, () => {
  if (!props.photoUrl) {
    nextTick(() => updateAvatar())
  }
})
</script>
