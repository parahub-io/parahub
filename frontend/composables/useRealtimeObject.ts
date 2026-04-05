/**
 * Per-object reactive view into the realtime store.
 *
 * Returns `justUpdated` ref that flashes true for 500ms on each update,
 * and `changes` — the latest change payload.
 */
export function useRealtimeObject(ulid: string | Ref<string>) {
  const realtimeStore = useRealtimeStore()

  const justUpdated = ref(false)
  let flashTimer: ReturnType<typeof setTimeout> | null = null

  const resolvedId = computed(() => typeof ulid === 'string' ? ulid : ulid.value)

  const changes = computed(() => {
    return realtimeStore.latestUpdates.get(resolvedId.value)?.changes ?? null
  })

  // Watch for updates to this specific object
  watch(
    () => realtimeStore.latestUpdates.get(resolvedId.value)?.timestamp,
    (newTs, oldTs) => {
      if (newTs && newTs !== oldTs) {
        justUpdated.value = true
        if (flashTimer) clearTimeout(flashTimer)
        flashTimer = setTimeout(() => {
          justUpdated.value = false
        }, 500)
      }
    },
  )

  onUnmounted(() => {
    if (flashTimer) clearTimeout(flashTimer)
  })

  return { changes, justUpdated }
}
