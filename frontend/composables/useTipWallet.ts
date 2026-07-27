/**
 * A throwaway wallet driven by a printed tip note.
 *
 * Deliberately separate from `useLightning`: that composable is a per-browser
 * singleton guarding the user's own seed behind the `parahub-breez-sdk` Web
 * Lock, and a tip is a different wallet entirely. Claiming a note while your own
 * wallet is open in another tab must just work, so this one takes its own lock
 * and its own IndexedDB store, both keyed by the note.
 */
import type { Payment } from '@breeztech/breez-sdk-spark/web'

const buildSdk = async (mnemonic: string, storageName: string) => {
  const breez = await import('@breeztech/breez-sdk-spark/web')
  await breez.default()
  const config = breez.defaultConfig('mainnet')
  const apiKey = useRuntimeConfig().public.breezApiKey as string
  if (apiKey) config.apiKey = apiKey
  let builder = breez.SdkBuilder.new(config, { type: 'mnemonic', mnemonic })
  builder = await builder.withDefaultStorage(storageName)
  return builder.build()
}

export const useTipWallet = () => {
  const sdk = shallowRef<any>(null)
  const connecting = ref(false)
  const balanceSats = ref(0)
  /** Amount sitting in the HTLC before it is unlocked. */
  const pendingSats = ref(0)

  const connect = async (mnemonic: string, code: string) => {
    if (sdk.value) return
    connecting.value = true
    try {
      const storage = `parahub-tip-${code.slice(0, 12)}`
      const instance = 'locks' in navigator
        ? await navigator.locks.request(`${storage}-lock`, { ifAvailable: true },
            lock => (lock ? buildSdk(mnemonic, storage) : buildSdk(mnemonic, `${storage}-${Date.now()}`)))
        : await buildSdk(mnemonic, storage)
      sdk.value = instance
      await refresh()
    } finally {
      connecting.value = false
    }
  }

  const refresh = async () => {
    if (!sdk.value) return
    try { await sdk.value.syncWallet({}) } catch { /* balance below is still worth showing */ }
    balanceSats.value = (await sdk.value.getInfo({ ensureSynced: true })).balanceSats
    const { payments } = await sdk.value.listPayments({ limit: 20, offset: 0 })
    pendingSats.value = payments
      .filter((p: Payment) => p.status === 'pending' && p.paymentType === 'receive')
      .reduce((sum: number, p: Payment) => sum + Number(p.amount), 0)
  }

  /** Unlock the note with its preimage. */
  const claim = async (preimage: string) => {
    if (!sdk.value) throw new Error('tip wallet not connected')
    await sdk.value.claimHtlcPayment({ preimage })
    await refresh()
  }

  /** Pay a bolt11 invoice, a Spark address or an on-chain address. */
  const quote = async (destination: string, amountSats?: number) =>
    sdk.value.prepareSendPayment({
      paymentRequest: { type: 'input', input: destination.trim() },
      ...(amountSats ? { amount: BigInt(amountSats) } : {}),
    })

  const send = async (prepareResponse: any): Promise<Payment> => {
    const res = await sdk.value.sendPayment({ prepareResponse })
    await refresh()
    return res.payment
  }

  /**
   * Lightning addresses and LNURL take a different route entirely:
   * `prepareSendPayment` rejects them as an unsupported payment method.
   */
  const quoteLnurl = async (payRequest: any, amountSats: number) =>
    sdk.value.prepareLnurlPay({ amount: BigInt(amountSats), payRequest })

  const sendLnurl = async (prepareResponse: any): Promise<Payment> => {
    const res = await sdk.value.lnurlPay({ prepareResponse })
    await refresh()
    return res.payment
  }

  const disconnect = async () => {
    if (!sdk.value) return
    try { await sdk.value.disconnect() } catch { /* tab is going away anyway */ }
    sdk.value = null
  }

  return {
    sdk, connecting, balanceSats, pendingSats,
    connect, refresh, claim, quote, send, quoteLnurl, sendLnurl, disconnect,
  }
}
