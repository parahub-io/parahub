import { ref, onMounted, onUnmounted } from 'vue'
import { useRealtimeStore } from '~/stores/realtime'

export interface OnlineUser {
  id: string
  hna: string
  local_name: string
  name: string
  avatar: string | null
}

/**
 * Live "who's online" presence for the staff dashboard widget.
 *
 * Joins the staff-only `presence` room over the shared realtime WebSocket and
 * receives a snapshot ({ total, anon, users }) on join and on every change
 * (someone connects / disconnects / ages out). No polling.
 */
export function useOnlinePresence() {
  const realtime = useRealtimeStore()
  const total = ref(0)
  const anon = ref(0)
  const users = ref<OnlineUser[]>([])

  function apply(d: any) {
    total.value = d?.total ?? 0
    anon.value = d?.anon ?? 0
    users.value = Array.isArray(d?.users) ? d.users : []
  }

  onMounted(() => {
    realtime.connect()
    realtime.on('presence.initial_state', apply)
    realtime.on('presence.snapshot', apply)
    // id is ignored server-side — the room is bound to the connection's deploy slot
    realtime.joinRoom('presence', 'self')
  })

  onUnmounted(() => {
    realtime.leaveRoom('presence', 'self')
    realtime.off('presence.initial_state', apply)
    realtime.off('presence.snapshot', apply)
  })

  return { total, anon, users }
}
