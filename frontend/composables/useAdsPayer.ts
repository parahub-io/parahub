/**
 * Background payer agent for browser-paid ad rewards (ads rail C).
 *
 * When an advertiser's payout wallet is their in-browser Parahub Spark wallet
 * (provider 'spark'), the server never touches the payment: viewers' claims
 * become queued instructions, and any open tab of the advertiser picks them
 * up — triggered live over WS (`ads.payout_requested` on the user channel)
 * and once shortly after login for anything queued while they were away.
 *
 * Safety model:
 * - Never pays from a seed that doesn't belong to the logged-in account
 *   (checkSeedOwnership must answer 'owned').
 * - Verifies every instruction against the campaign the advertiser created:
 *   amount must equal reward_sats and stay within budget_sats — including a
 *   local, monotonic ledger of what this browser already paid, so even a
 *   misbehaving server cannot squeeze out more than the declared budget.
 * - One device at a time per payout (server-side Redis lease); one tab at a
 *   time per browser (the SDK's own Web Lock — a tab that can't get it
 *   simply leaves the work to the tab that holds it).
 * - Spark-first: viewers with a platform wallet are paid to their Spark
 *   address (zero fee, no LNURL). Lightning addresses go through the
 *   server-resolved invoice, and the payment preimage is reported back as
 *   proof.
 */

import { ref } from 'vue'
import { useLightning } from './useLightning'
import { useSeed } from './useSeed'
import { checkSeedOwnership } from './useSeedOwner'
import { annotateTx } from './useTxAnnotations'

interface PayoutQueueItem {
  view_id: string
  amount_sats: number
  queued_at: string
  attempts: number
  viewer_spark_address: string | null
  viewer_ln_address: string | null
  campaign: {
    id: string
    name: string
    reward_sats: number
    budget_sats: number
    spent_sats: number
    status: string
  }
}

const queueCount = ref(0)
const paying = ref(false)

let initialized = false
let processing = false
let debounceTimer: ReturnType<typeof setTimeout> | null = null
let initialTimer: ReturnType<typeof setTimeout> | null = null

const LEDGER_KEY = 'parahub_ads_payer_ledger'
const SDK_READY_TIMEOUT_MS = 30000
const PREIMAGE_POLL_MS = 15000

function readLedger(): Record<string, number> {
  try {
    return JSON.parse(localStorage.getItem(LEDGER_KEY) || '{}')
  } catch {
    return {}
  }
}

function ledgerAdd(campaignId: string, sats: number) {
  const ledger = readLedger()
  ledger[campaignId] = (ledger[campaignId] || 0) + sats
  try { localStorage.setItem(LEDGER_KEY, JSON.stringify(ledger)) } catch {}
}

export const useAdsPayer = () => {
  const authStore = useAuthStore()

  async function api<T>(path: string, opts: any = {}): Promise<T> {
    await authStore.ensureToken()
    return $fetch<T>(`/api/v1/ads${path}`, {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      ...opts,
    })
  }

  const onPayoutRequested = () => scheduleProcess(1500)

  function scheduleProcess(delayMs: number) {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { processQueue() }, delayMs)
  }

  function init() {
    if (!process.client || initialized) return
    initialized = true
    const realtimeStore = useRealtimeStore()
    realtimeStore.on('ads.payout_requested', onPayoutRequested)
    // Anything queued while this account was offline: one check after the
    // page has settled (the queue endpoint is a single indexed query).
    initialTimer = setTimeout(() => { processQueue() }, 4000)
  }

  function cleanup() {
    if (!process.client || !initialized) return
    initialized = false
    const realtimeStore = useRealtimeStore()
    realtimeStore.off('ads.payout_requested', onPayoutRequested)
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null }
    if (initialTimer) { clearTimeout(initialTimer); initialTimer = null }
  }

  async function processQueue() {
    if (processing) return
    processing = true
    paying.value = true
    try {
      const queue = await api<{ items: PayoutQueueItem[]; count: number }>('/payouts/queue/')
      queueCount.value = queue.count
      if (!queue.items.length) return

      // This browser can only pay with the account's own wallet
      const { hasSeed } = useSeed()
      if (!hasSeed()) return // no wallet here — another device will pay
      const ownership = await checkSeedOwnership()
      if (ownership !== 'owned') return // never auto-pay from a foreign/unverified seed

      const lightning = useLightning()
      await lightning.initSdk()
      const ready = await waitForSdkReady(lightning)
      if (!ready) return // lock held by another tab (which also got the event) or init failed

      for (const item of queue.items) {
        await payOne(lightning, item)
        await new Promise(r => setTimeout(r, 300))
      }

      const after = await api<{ items: PayoutQueueItem[]; count: number }>('/payouts/queue/')
      queueCount.value = after.count
    } catch (e) {
      console.error('[ads-payer] queue processing failed:', e)
    } finally {
      paying.value = false
      processing = false
    }
  }

  async function waitForSdkReady(lightning: ReturnType<typeof useLightning>): Promise<boolean> {
    const start = Date.now()
    while (Date.now() - start < SDK_READY_TIMEOUT_MS) {
      if (lightning.sdkState.value === 'ready') return true
      if (lightning.sdkState.value === 'error') return false
      await new Promise(r => setTimeout(r, 500))
    }
    return false
  }

  /** Instruction sanity: only pay what the advertiser themselves declared. */
  function verifyAgainstCampaign(item: PayoutQueueItem): boolean {
    const c = item.campaign
    if (item.amount_sats !== c.reward_sats) return false
    if (c.spent_sats + item.amount_sats > c.budget_sats) return false
    const paidHere = readLedger()[c.id] || 0
    if (paidHere + item.amount_sats > c.budget_sats) return false
    return true
  }

  async function payOne(lightning: ReturnType<typeof useLightning>, item: PayoutQueueItem) {
    if (!verifyAgainstCampaign(item)) {
      // A mismatched instruction is suspicious, not merely failed — leave it
      // visible in the queue rather than burning it with a 'failed' report.
      console.warn('[ads-payer] payout does not match its campaign, skipping:', item.view_id)
      return
    }

    try {
      await api(`/payouts/${item.view_id}/lease/`, { method: 'POST' })
    } catch {
      return // another device is on it
    }

    try {
      if (item.viewer_spark_address) {
        await paySpark(lightning, item)
      } else if (item.viewer_ln_address) {
        await payLnurl(lightning, item)
      } else {
        await reportFailed(item, 'Viewer has no payment address', 'lnurl')
      }
    } catch (e: any) {
      console.error('[ads-payer] payout failed:', item.view_id, e)
      await reportFailed(item, e?.message || String(e), 'pay').catch(() => {})
    }
  }

  async function paySpark(lightning: ReturnType<typeof useLightning>, item: PayoutQueueItem) {
    let prepared
    try {
      prepared = await lightning.prepareSend(item.viewer_spark_address!, BigInt(item.amount_sats))
    } catch (e: any) {
      // prepare never moves money — safe to report as failed
      await reportFailed(item, `Prepare failed: ${e?.message || e}`, 'pay')
      return
    }
    try {
      const payment = await lightning.executeSend(prepared)
      annotateTx(payment.id, { kind: 'ad', name: item.campaign.name })
      await reportSent(item, 'spark', payment.id)
    } catch (e: any) {
      // sendPayment threw, but the transfer may still have gone through —
      // look for it before declaring failure, a false 'failed' re-queues the
      // ad and would pay the viewer twice.
      const recovered = await findRecentSparkSend(lightning, item)
      if (recovered) {
        annotateTx(recovered, { kind: 'ad', name: item.campaign.name })
        await reportSent(item, 'spark', recovered)
      } else {
        await reportFailed(item, e?.message || String(e), 'pay')
      }
    }
  }

  async function findRecentSparkSend(
    lightning: ReturnType<typeof useLightning>, item: PayoutQueueItem
  ): Promise<string | null> {
    try {
      const payments = await lightning.listPayments(20)
      const cutoff = Date.now() / 1000 - 120
      const match = payments.find(p => {
        const d = p.details
        return p.paymentType === 'send'
          && p.timestamp >= cutoff
          && Number(p.amount) === item.amount_sats
          && !!d && d.type === 'spark'
          && (p.status === 'completed' || p.status === 'pending')
      })
      return match?.id || null
    } catch {
      return null
    }
  }

  async function payLnurl(lightning: ReturnType<typeof useLightning>, item: PayoutQueueItem) {
    let invoice: string
    try {
      const resolved = await api<{ invoice: string }>(`/payouts/${item.view_id}/resolve/`, { method: 'POST' })
      invoice = resolved.invoice
    } catch (e: any) {
      await reportFailed(item, e?.data?.detail || 'Could not resolve viewer address', 'lnurl')
      return
    }

    // The viewer's LNURL server chose this invoice — never trust it blindly
    const parsed = await lightning.parseInput(invoice)
    if (parsed.type !== 'bolt11Invoice' || Number(parsed.amountMsat) !== item.amount_sats * 1000) {
      await reportFailed(item, 'Invoice amount does not match the reward', 'lnurl')
      return
    }

    // An earlier interrupted run may have already paid this exact invoice
    // (the server hands out the same one while it is fresh)
    const prior = await findPaymentByInvoice(lightning, invoice)
    if (prior) {
      const preimage = await extractPreimage(lightning, prior.id)
      if (preimage) {
        annotateTx(prior.id, { kind: 'ad', name: item.campaign.name })
        await reportSent(item, 'lnurl', preimage)
        return
      }
    }

    let prepared
    try {
      prepared = await lightning.prepareSend(invoice)
    } catch (e: any) {
      await reportFailed(item, `Prepare failed: ${e?.message || e}`, 'pay')
      return
    }
    const payment = await lightning.executeSend(prepared)
    annotateTx(payment.id, { kind: 'ad', name: item.campaign.name })
    const preimage = await extractPreimage(lightning, payment.id)
    if (!preimage) {
      // Paid (or possibly paid) but no proof yet. Do NOT report failure —
      // the lease will expire and the next round finds the paid invoice
      // above and completes with its preimage.
      console.warn('[ads-payer] no preimage yet for', item.view_id, '— will retry reporting later')
      return
    }
    await reportSent(item, 'lnurl', preimage)
  }

  async function findPaymentByInvoice(
    lightning: ReturnType<typeof useLightning>, invoice: string
  ) {
    try {
      const payments = await lightning.listPayments(100)
      return payments.find(p => {
        const d = p.details
        return !!d && d.type === 'lightning' && d.invoice === invoice
      }) || null
    } catch {
      return null
    }
  }

  async function extractPreimage(
    lightning: ReturnType<typeof useLightning>, paymentId: string
  ): Promise<string | null> {
    const start = Date.now()
    while (Date.now() - start < PREIMAGE_POLL_MS) {
      try {
        const payment = await lightning.getPayment(paymentId)
        const details = payment.details
        if (details && details.type === 'lightning' && details.htlcDetails?.preimage) {
          return details.htlcDetails.preimage
        }
        if (payment.status === 'failed') return null
      } catch {}
      await new Promise(r => setTimeout(r, 1000))
    }
    return null
  }

  async function reportSent(item: PayoutQueueItem, method: 'spark' | 'lnurl', proof: string) {
    await api(`/payouts/${item.view_id}/complete/`, {
      method: 'POST',
      body: { result: 'sent', method, proof },
    })
    ledgerAdd(item.campaign.id, item.amount_sats)
    notifyPaid(item)
  }

  function reportFailed(item: PayoutQueueItem, error: string, stage: 'lnurl' | 'pay') {
    return api(`/payouts/${item.view_id}/complete/`, {
      method: 'POST',
      body: { result: 'failed', method: 'spark', error: error.slice(0, 400), stage },
    })
  }

  function notifyPaid(item: PayoutQueueItem) {
    // Money left the advertiser's wallet without a click — that must never
    // be silent on their side.
    import('~/stores/toast').then(({ useToastStore }) => {
      try {
        const { $i18n } = useNuxtApp() as any
        const msg = $i18n?.t
          ? $i18n.t('ads.payer.paid_toast', { sats: item.amount_sats, name: item.campaign.name })
          : `-${item.amount_sats} sats · ad reward`
        useToastStore().success(msg)
      } catch {}
    }).catch(() => {})
  }

  return {
    queueCount,
    paying,
    init,
    cleanup,
    processQueue,
  }
}
