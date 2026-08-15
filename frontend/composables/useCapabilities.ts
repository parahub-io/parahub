/**
 * Platform capabilities of the signed-in login.
 *
 * The frontend half of `parahub/capabilities.py`: node-level surfaces (the
 * federation registry, the trust graph, the infrastructure consoles, the
 * urbanística dossiê) ask for a capability instead of `is_staff`, so one of them
 * can be handed to a person without handing over Django admin with it.
 *
 * `is_staff` still resolves to every capability server-side, so gating on a
 * capability never takes anything away from staff — it only widens who else can
 * be let in. Authority *inside an organization* is a different question and
 * comes from the org endpoints (`geo/permissions.py`), not from here.
 *
 *   const { can } = useCapabilities()
 *   const isFederationAdmin = computed(() => can('federation.admin'))
 */

export type PlatformCapability =
  | 'urban.validate'
  | 'moderation.review'
  | 'infra.operate'
  | 'federation.admin'

const ALL_CAPABILITIES: PlatformCapability[] = [
  'urban.validate', 'moderation.review', 'infra.operate', 'federation.admin',
]

export function useCapabilities() {
  const authStore = useAuthStore()

  const capabilities = computed<string[]>(() => {
    const user = authStore.user
    if (!user) return []
    if (Array.isArray(user.capabilities)) return user.capabilities
    // No `capabilities` key at all means the payload came from a backend that
    // predates them — SSR hydrates from the production node (`plugins/auth.ts`
    // hardcodes :8000), so a dev slot sees this until prod catches up. There
    // `is_staff` was the whole answer, so honour it rather than silently taking
    // away UI that used to be there. An empty array is authoritative.
    return user.is_staff ? [...ALL_CAPABILITIES] : []
  })

  /** Does this login hold `capability`? */
  function can(capability: PlatformCapability): boolean {
    return capabilities.value.includes(capability)
  }

  /** Any one of them — for a surface that several capabilities can open. */
  function canAny(...list: PlatformCapability[]): boolean {
    return list.some(can)
  }

  /**
   * The node owner — the only login that may hand a capability out
   * (`require_superuser` in `parahub/capabilities.py`). Holding capabilities
   * never includes granting them, and neither does `is_staff`.
   */
  const isOwner = computed(() => {
    const user = authStore.user
    if (!user) return false
    if (typeof user.is_superuser === 'boolean') return user.is_superuser
    // Same shape as above: an older payload has no such key, and there staff was
    // the closest thing to an owner. The screen itself asks the API anyway.
    return !!user.is_staff
  })

  return { capabilities, can, canAny, isOwner }
}
