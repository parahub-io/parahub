<template>
  <div class="relative w-full h-full flex items-center justify-center">
    <!-- SVG Pentagon with clean design -->
    <svg
      :width="size"
      :height="size"
      :viewBox="`0 0 ${size} ${size}`"
      class="transform"
    >
      <!-- Defs for gradients and filters -->
      <defs>
        <!-- Glow filter -->
        <filter id="glow">
          <feGaussianBlur stdDeviation="2" result="coloredBlur"/>
          <feMerge>
            <feMergeNode in="coloredBlur"/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>
      </defs>

      <!-- Grid circles (background) -->
      <circle
        v-for="level in [0.25, 0.5, 0.75, 1]"
        :key="level"
        :cx="center"
        :cy="center"
        :r="radius * level"
        fill="none"
        stroke="rgba(212, 212, 216, 0.4)"
        :stroke-width="level === 1 ? 2 : 1"
      />

      <!-- Grid lines from center to each point (straight lines) -->
      <line
        v-for="(point, index) in pentagonPoints"
        :key="`line-${index}`"
        :x1="center"
        :y1="center"
        :x2="point.x"
        :y2="point.y"
        stroke="rgba(212, 212, 216, 0.3)"
        stroke-width="1"
      />

      <!-- Achievement shape (filled area) - simple polygon -->
      <polygon
        :points="achievementPolygonPoints"
        :fill="achievementFillColor"
        :stroke="achievementStrokeColor"
        stroke-width="2.5"
        opacity="0.7"
        class="transition-all duration-500"
      />

      <!-- Pentagon points (achievement nodes) -->
      <g v-for="(achievement, index) in achievements" :key="achievement.category">
        <circle
          :cx="pentagonPoints[index].x"
          :cy="pentagonPoints[index].y"
          :r="getNodeRadius(achievement.level)"
          :fill="getNodeColor(achievement.level)"
          :stroke="getNodeStrokeColor(achievement.level)"
          stroke-width="2"
          filter="url(#glow)"
          class="transition-all duration-300 cursor-pointer"
          :class="{
            'animate-pulse': hoveredCategory === achievement.category
          }"
          @mouseenter="hoveredCategory = achievement.category"
          @mouseleave="hoveredCategory = null"
        />

        <!-- Level indicator (number inside node) -->
        <text
          :x="pentagonPoints[index].x"
          :y="pentagonPoints[index].y"
          text-anchor="middle"
          dominant-baseline="middle"
          class="text-xs font-bold fill-white pointer-events-none select-none"
        >
          {{ achievement.level }}
        </text>

        <!-- Label (category name) -->
        <text
          :x="labelPositions[index].x"
          :y="labelPositions[index].y"
          text-anchor="middle"
          class="text-sm font-medium fill-neutral-700 pointer-events-none select-none"
        >
          {{ getCategoryLabel(achievement.category) }}
        </text>

        <!-- Progress indicator (on hover) - positioned above node -->
        <g v-if="hoveredCategory === achievement.category">
          <!-- Tooltip background with subtle styling -->
          <rect
            :x="pentagonPoints[index].x - 35"
            :y="pentagonPoints[index].y - 50"
            width="70"
            height="24"
            rx="6"
            fill="rgba(255, 255, 255, 0.95)"
            stroke="rgba(8, 145, 178, 0.4)"
            stroke-width="1.5"
            filter="url(#glow)"
          />
          <!-- Progress text -->
          <text
            :x="pentagonPoints[index].x"
            :y="pentagonPoints[index].y - 33"
            text-anchor="middle"
            class="text-xs fill-secondary-700 font-semibold"
          >
            {{ achievement.progress }}{{ achievement.next_threshold ? ` / ${achievement.next_threshold}` : '' }}
          </text>
        </g>
      </g>
    </svg>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface Achievement {
  category: string
  level: number
  progress: number
  next_threshold: number | null
}

const props = withDefaults(defineProps<{
  achievements: Achievement[]
  size?: number
}>(), {
  size: 400
})

const hoveredCategory = ref<string | null>(null)

const center = computed(() => props.size / 2)
const radius = computed(() => props.size * 0.32)

// Calculate pentagon points (5 points in a circle)
const pentagonPoints = computed(() => {
  const points = []
  const angleOffset = -Math.PI / 2 // Start from top

  for (let i = 0; i < 5; i++) {
    const angle = angleOffset + (i * 2 * Math.PI / 5)
    points.push({
      x: center.value + radius.value * Math.cos(angle),
      y: center.value + radius.value * Math.sin(angle)
    })
  }

  return points
})

// Calculate label positions (further out from points)
const labelPositions = computed(() => {
  const labelRadius = radius.value * 1.30
  const angleOffset = -Math.PI / 2
  const points = []

  for (let i = 0; i < 5; i++) {
    const angle = angleOffset + (i * 2 * Math.PI / 5)
    points.push({
      x: center.value + labelRadius * Math.cos(angle),
      y: center.value + labelRadius * Math.sin(angle)
    })
  }

  return points
})

// Create achievement polygon points (simple, no curves)
const achievementPolygonPoints = computed(() => {
  if (props.achievements.length === 0) return ''

  const points = props.achievements.map((achievement, index) => {
    const point = pentagonPoints.value[index]
    const levelRatio = achievement.level / 2 // Max level is 2
    const x = center.value + (point.x - center.value) * levelRatio
    const y = center.value + (point.y - center.value) * levelRatio
    return `${x},${y}`
  })

  return points.join(' ')
})

const achievementFillColor = computed(() => {
  const totalLevel = props.achievements.reduce((sum, a) => sum + a.level, 0)
  const maxLevel = props.achievements.length * 2
  const ratio = totalLevel / maxLevel

  if (ratio >= 0.8) return 'rgba(5, 150, 105, 0.3)' // success
  if (ratio >= 0.5) return 'rgba(8, 145, 178, 0.3)' // secondary
  return 'rgba(161, 161, 170, 0.3)' // neutral-400
})

const achievementStrokeColor = computed(() => {
  const totalLevel = props.achievements.reduce((sum, a) => sum + a.level, 0)
  const maxLevel = props.achievements.length * 2
  const ratio = totalLevel / maxLevel

  if (ratio >= 0.8) return 'rgba(5, 150, 105, 0.8)' // success
  if (ratio >= 0.5) return 'rgba(8, 145, 178, 0.8)' // secondary
  return 'rgba(161, 161, 170, 0.8)' // neutral-400
})

function getNodeRadius(level: number): number {
  if (level === 0) return 12
  if (level === 1) return 18
  return 24
}

function getNodeColor(level: number): string {
  if (level === 0) return 'rgba(113, 113, 122, 0.8)' // neutral-500
  if (level === 1) return 'rgba(8, 145, 178, 0.8)' // secondary
  return 'rgba(5, 150, 105, 0.8)' // success
}

function getNodeStrokeColor(level: number): string {
  if (level === 0) return 'rgba(161, 161, 170, 1)' // neutral-400
  if (level === 1) return 'rgba(34, 211, 238, 1)' // secondary-400
  return 'rgba(52, 211, 153, 1)' // success-400
}

function getCategoryLabel(category: string): string {
  const labels: Record<string, string> = {
    cryptography: 'Crypto',
    goods_services: 'Goods',
    profile: 'Profile',
    ads: 'Ads',
    verifications: 'Trust'
  }
  return labels[category] || category
}
</script>
