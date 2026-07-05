import { computed, ref, watch } from 'vue'
import type { WatchSource } from 'vue'
import { useAuthStore } from '~/stores/auth'

/**
 * Cache-first list fetching for instant client-side navigation.
 *
 * Problem it solves: most pages used `onMounted` + `$fetch`, which renders the
 * page shell immediately and then pops the content in ~30-50ms later — the
 * "flicker" felt when switching navbar sections (top appears, brief gap, body
 * fills in). useListData removes that two-phase render structurally:
 *
 *   - server:true     → the fetch runs during SSR AND is awaited inside the
 *                       navigation's Suspense boundary, so on client-side
 *                       navigation the OLD page stays visible until the new
 *                       page's data is ready. The new page never appears
 *                       half-empty → no two-phase render. (Verified: with
 *                       `server:false` Nuxt mounts the page first and fetches
 *                       on mount, so the skeleton still flashes — server:true is
 *                       what actually blocks.) <NuxtLoadingIndicator> gives the
 *                       click instant top-bar feedback during the wait.
 *   - getCachedData   → on revisit (or KeepAlive eviction / deep link) the
 *                       result is served from the Nuxt payload synchronously →
 *                       instant, no skeleton. A page's WS subscription
 *                       (useObjectListSubscription) keeps that cache fresh.
 *   - reactive query  → filter changes refetch in the background while the
 *                       previous list stays visible (skeleton only on first load).
 *
 * `server: true` by default (required for the no-flicker blocking above) and
 * correct for PUBLIC endpoints, which SSR fine through the Nitro /api proxy.
 * For AUTHED endpoints that 401 during SSR (see the SSR-skip history in
 * pages/market/index.vue), pass `server: false` — client nav still benefits
 * from getCachedData (instant revisits) even though the first visit shows a
 * brief skeleton.
 */
export interface UseListDataOptions<T> {
  /** Reactive query object/computed — changing it refetches in the background. */
  query?: any
  params?: any
  /** Value shown before the first response resolves (shape of your payload). */
  default?: () => T
  /** SSR the fetch. Default true (needed to block nav). Set false for authed
   *  endpoints that 401 during SSR. */
  server?: boolean
  /** Inject the JWT Bearer token (via authStore.ensureToken) on each request.
   *  Implies server:false (token is client-only, would 401 during SSR). */
  auth?: boolean
  transform?: (input: any) => T
  /** Extra reactive sources to refetch on. useFetch already watches `query`. */
  watch?: WatchSource[] | false
  /** Explicit cache key (lets a prefetcher warm the exact same entry). */
  key?: string
  headers?: Record<string, string>
  immediate?: boolean
  credentials?: RequestCredentials
}

export function useListData<T = any>(
  url: string | (() => string),
  options: UseListDataOptions<T> = {},
) {
  // Authed endpoints: inject the Bearer token per request and skip SSR (the
  // token is client-only, so an SSR fetch would 401). The await barrier still
  // blocks client navigation regardless of server flag.
  const authStore = options.auth ? useAuthStore() : null

  const res = useFetch<T>(url as any, {
    query: options.query,
    params: options.params,
    server: options.server ?? (options.auth ? false : true),
    lazy: false,
    default: options.default,
    transform: options.transform,
    watch: options.watch,
    key: options.key,
    headers: options.headers,
    immediate: options.immediate,
    credentials: options.credentials ?? 'include',
    async onRequest({ options: reqOptions }) {
      if (!authStore) return
      try { await authStore.ensureToken() } catch { /* anon / refresh failed */ }
      const tok = authStore.token
      if (tok) {
        const h = new Headers(reqOptions.headers as HeadersInit | undefined)
        h.set('Authorization', `Bearer ${tok}`)
        reqOptions.headers = h
      }
    },
    // Cache-first: reuse the session payload so revisits render instantly
    // instead of refetching + flashing a skeleton.
    getCachedData(key, nuxtApp) {
      return nuxtApp.payload.data[key] ?? nuxtApp.static.data[key]
    },
  })

  const { status } = res

  // Distinguish the first load (show a skeleton) from background refetches
  // (filter change / revalidate — keep the previous list visible, no flash).
  // Tracked via a flag rather than `!data` because `default` is usually a
  // truthy empty shape like `{ items: [] }`. A getCachedData hit resolves
  // straight to 'success' (no pending), so hasResolved starts true → no flash.
  const hasResolved = ref(status.value === 'success' || status.value === 'error')
  watch(status, (s) => {
    if (s === 'success' || s === 'error') hasResolved.value = true
  })

  // Skeleton only on the very first load. The `status` check is what makes SSR
  // correct: with server:true the data resolves inside Suspense before render,
  // so status is already 'success' at render time even though the `watch` above
  // does not fire during SSR. `hasResolved` then keeps a background refetch
  // (filter change) from dropping back to a skeleton on the client.
  // server:false → status is 'idle' on SSR and 'pending' on client hydration,
  // both yielding isInitial=true, so the skeleton matches → no hydration drift.
  const isInitial = computed(
    () => status.value !== 'success' && status.value !== 'error' && !hasResolved.value,
  )
  // Background refetch (filter change / revalidate): list stays, show a cue.
  const refreshing = computed(() => hasResolved.value && status.value === 'pending')

  // Attach the derived flags onto the AsyncData object (rather than spreading
  // into a plain object) so it stays a thenable: the page can `await` the
  // return value to make its setup async, which is what actually makes Suspense
  // hold the previous page during client-side navigation (a non-awaited
  // useFetch returns synchronously → setup isn't async → no blocking → the
  // skeleton flashes). server:true alone does NOT block; the await does.
  return Object.assign(res, { isInitial, refreshing })
}
