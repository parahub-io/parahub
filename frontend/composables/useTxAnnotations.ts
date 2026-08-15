/**
 * Client-side context for wallet payments, keyed by SDK payment id.
 *
 * A plain Spark transfer carries no counterparty in the payment record, so the
 * only place context exists is the moment a send is made — the pay-a-profile
 * modal knows the profile, the ticket modal knows the event, the ads payer
 * knows the campaign. Flows write a small annotation here and the wallet
 * history reads it to render a human line ("To @carlos", "Ticket · …") instead
 * of a bare amount. Receives stay anonymous by design (owner decision): the
 * server is never told who paid whom, so annotations live only in the browser
 * that made the payment, same as recent recipients and tip batches.
 *
 * Cross-device: users who opted into wallet sync (advanced preferences) carry
 * this store between devices as a seed-encrypted blob the server cannot read
 * (useWalletSync) — the who-paid-whom graph still never reaches the server in
 * plaintext, so the owner decision above survives sync.
 */
export type TxAnnotationKind = 'profile' | 'subscription' | 'donation' | 'ad' | 'ticket'

export interface TxAnnotation {
  kind: TxAnnotationKind
  /** Counterparty or subject display name (profile name, campaign, ticket type). */
  name?: string
  /** Profile local name for /@{slug} links, when the counterparty is a parahub profile. */
  slug?: string
  ts: number
}

const STORAGE_KEY = 'parahub_tx_annotations'
export const MAX_TX_ANNOTATION_ENTRIES = 1000

export const readTxAnnotations = (): Record<string, TxAnnotation> => {
  if (!import.meta.client) return {}
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
  } catch {
    return {}
  }
}

export const writeTxAnnotations = (all: Record<string, TxAnnotation>) => {
  if (!import.meta.client) return
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(all))
  } catch {
    // Quota or serialization failure loses a label, never a payment.
  }
}

/** Record context for a payment. Never throws — annotations are best-effort. */
export const annotateTx = (paymentId: string, ann: Omit<TxAnnotation, 'ts'>) => {
  if (!import.meta.client || !paymentId) return
  try {
    const all = readTxAnnotations()
    all[paymentId] = { ...ann, ts: Date.now() }
    const ids = Object.keys(all)
    if (ids.length > MAX_TX_ANNOTATION_ENTRIES) {
      ids.sort((a, b) => (all[a].ts || 0) - (all[b].ts || 0))
      for (const id of ids.slice(0, ids.length - MAX_TX_ANNOTATION_ENTRIES)) delete all[id]
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(all))
    useWalletSync().scheduleUpload()
  } catch {
    // Quota or serialization failure loses a label, never a payment.
  }
}
