/**
 * Recurring-support (subscription) API client.
 *
 * Non-custodial: the actual Lightning payment is sent client-side straight to the
 * recipient (via UserLightningPayModal). These calls only record the relationship
 * and read its status — the backend never touches funds.
 */
export function useSubscriptions() {
  const authStore = useAuthStore()

  const authOpts = async () => {
    await authStore.ensureToken()
    return {
      credentials: 'include' as const,
      headers: { Authorization: `Bearer ${authStore.token}` },
    }
  }

  /** Public subscriber count for a profile + (if signed in) the viewer's own status. */
  const getStatus = async (recipientId: string) => {
    const opts: any = {}
    if (authStore.isAuthenticated) {
      await authStore.ensureToken()
      opts.credentials = 'include'
      opts.headers = { Authorization: `Bearer ${authStore.token}` }
    }
    return await $fetch(`/api/v1/subscriptions/status/${recipientId}/`, opts)
  }

  /** Record a paid cycle — starts a new subscription or renews an existing one. */
  const subscribe = async (recipientId: string, amountSats: number, paymentHash = '') => {
    await authStore.ensureToken()
    return await $fetch('/api/v1/subscriptions/', {
      method: 'POST',
      credentials: 'include',
      headers: {
        Authorization: `Bearer ${authStore.token}`,
        'Content-Type': 'application/json',
      },
      body: { recipient_id: recipientId, amount_sats: amountSats, ln_payment_hash: paymentHash },
    })
  }

  /** Stop renewals (access kept until the paid period ends). */
  const cancel = async (subscriptionId: string) => {
    const opts = await authOpts()
    return await $fetch(`/api/v1/subscriptions/${subscriptionId}/cancel/`, { method: 'POST', ...opts })
  }

  /** The caller's outbound subscriptions (who they support). */
  const listMine = async () => {
    const opts = await authOpts()
    return await $fetch('/api/v1/subscriptions/my/', opts)
  }

  return { getStatus, subscribe, cancel, listMine }
}
