<template>
  <div class="card p-6">
    <!-- Header (matches sibling infra cards) -->
    <div class="flex items-center gap-3 mb-3">
      <div class="w-10 h-10 rounded-full bg-secondary/10 flex items-center justify-center">
        <Wrench class="w-5 h-5 text-secondary" aria-hidden="true" />
      </div>
      <div>
        <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">Staff tools</h3>
        <span class="text-xs text-neutral-500">quick access</span>
      </div>
    </div>

    <!-- Sole entry point for these tools (the nav-menu staff row is retired);
         labels stay English, like the rest of the Infrastructure tab. Rows are
         filtered per viewer — see `tools` below. -->
    <div class="-mx-2">
      <NuxtLink
        v-for="tool in visibleTools"
        :key="tool.path"
        :to="localePath(tool.path)"
        class="flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors group"
      >
        <component :is="tool.icon" class="w-5 h-5 text-secondary flex-shrink-0" aria-hidden="true" />
        <div class="flex-1 min-w-0">
          <span class="block text-sm font-medium text-neutral-900 dark:text-neutral-100">{{ tool.label }}</span>
          <span class="block text-xs text-neutral-500 dark:text-neutral-400 truncate">{{ tool.desc }}</span>
        </div>
        <ChevronRight class="w-4 h-4 text-neutral-400 group-hover:text-secondary transition-colors flex-shrink-0" />
      </NuxtLink>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  Wrench, ChevronRight, LayoutDashboard, Sparkles, Share2, Network, Video,
  Flag, KeyRound,
} from 'lucide-vue-next'

const localePath = useLocalePath()
const authStore = useAuthStore()
const { can, isOwner } = useCapabilities()

// `when` decides who sees the row. A tool with a capability of its own shows for
// whoever holds it — this card is how an appointed moderator reaches their queue,
// not a staff-only shortcut list any more. Rows still on `is_staff` are the ones
// whose backend has no capability yet (mesh, zenith, calls, the dispatch override).
const isStaff = computed(() => !!authStore.user?.is_staff)
const tools = computed(() => [
  { path: '/moderation', icon: Flag, label: 'Moderation', desc: 'Abuse report queue', when: can('moderation.review') },
  { path: '/dispatch', icon: LayoutDashboard, label: 'Dispatch', desc: 'Vehicle-to-route assignments', when: isStaff.value },
  { path: '/zenith', icon: Sparkles, label: 'Zenith', desc: 'AI knowledge base', when: isStaff.value },
  { path: '/wot/graph', icon: Share2, label: 'WoT graph', desc: 'Verification network', when: can('moderation.review') },
  { path: '/mesh/graph', icon: Network, label: 'Mesh graph', desc: 'Fleet radio topology', when: isStaff.value },
  { path: '/call', icon: Video, label: 'Calls', desc: 'Video conference rooms', when: isStaff.value },
  { path: '/platform/capabilities', icon: KeyRound, label: 'Capabilities', desc: 'Who may do what on this node', when: isOwner.value },
])
const visibleTools = computed(() => tools.value.filter(t => t.when))
</script>
