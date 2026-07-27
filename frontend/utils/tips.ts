/**
 * Printed bitcoin tips — bearer-note derivation.
 *
 * A tip note carries exactly one thing: a 128-bit secret, printed as a QR and as
 * a typeable code. Everything else is derived from it in the browser:
 *
 *   secret ─HKDF─┬─► 16-byte seed ─BIP39─► mnemonic ─► Spark wallet (the note IS the wallet)
 *                └─► 32-byte preimage ──sha256──► payment hash (locks the HTLC)
 *
 * The sender funds each note with a Spark transfer locked to that payment hash and
 * an expiry. Only the holder of the paper can unlock it (preimage), and if nobody
 * does, the transfer returns to the sender when the expiry passes. No server ever
 * sees a secret — it lives in the URL fragment, which browsers never transmit.
 */
import { bech32m } from '@scure/base'
import { sha256 } from '@noble/hashes/sha2.js'
import { hkdf } from '@noble/hashes/hkdf.js'

export interface TipNote {
  /** Printed on the note; the only thing needed to claim it. */
  code: string
  mnemonic: string
  /** Spark address the sender pays. */
  address: string
  /** Unlocks the HTLC. Never leaves the client. */
  preimage: string
  paymentHash: string
}

const utf8 = (s: string) => new TextEncoder().encode(s)
const toHex = (b: Uint8Array) => Array.from(b, x => x.toString(16).padStart(2, '0')).join('')

/** URL- and paper-safe: no padding, no look-alike-prone punctuation. */
const encodeCode = (b: Uint8Array) =>
  btoa(String.fromCharCode(...b)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')

const decodeCode = (code: string): Uint8Array => {
  const b64 = code.replace(/-/g, '+').replace(/_/g, '/')
  const bin = atob(b64 + '='.repeat((4 - (b64.length % 4)) % 4))
  return Uint8Array.from(bin, c => c.charCodeAt(0))
}

/**
 * A Spark address is bech32m over a two-byte protobuf header plus the 33-byte
 * compressed identity pubkey. Deriving it here (rather than booting an SDK per
 * note) is what makes minting a whole batch cheap — no network, no Web Lock.
 */
const sparkAddressFor = (pubkey: Uint8Array) =>
  bech32m.encode('spark', bech32m.toWords(new Uint8Array([0x0a, 0x21, ...pubkey])), 1023)

const noteFromSecret = async (secret: Uint8Array): Promise<TipNote> => {
  const seed = hkdf(sha256, secret, undefined, utf8('parahub-tip-v1/seed'), 16)
  const preimage = hkdf(sha256, secret, undefined, utf8('parahub-tip-v1/preimage'), 32)

  const bip39 = await import('bip39')
  const mnemonic = bip39.entropyToMnemonic(toHex(seed))

  const breez = await import('@breeztech/breez-sdk-spark/web')
  await breez.default()
  const signers = breez.defaultExternalSigners(mnemonic, undefined, 'mainnet')
  const pubkey = new Uint8Array((await signers.sparkSigner.getIdentityPublicKey()).bytes)

  return {
    code: encodeCode(secret),
    mnemonic,
    address: sparkAddressFor(pubkey),
    preimage: toHex(preimage),
    paymentHash: toHex(sha256(preimage)),
  }
}

/** Mint a fresh note. The secret is the only thing that must reach paper. */
export const mintTipNote = (): Promise<TipNote> =>
  noteFromSecret(crypto.getRandomValues(new Uint8Array(16)))

/** Rebuild a note from its printed code — used by the claim page and reprints. */
export const tipNoteFromCode = (code: string): Promise<TipNote> => {
  const secret = decodeCode(code.trim().replace(/\s+/g, ''))
  if (secret.length !== 16) throw new Error('invalid tip code')
  return noteFromSecret(secret)
}

/** Printed form: groups of four, so it can be read aloud and typed. */
export const formatTipCode = (code: string) => code.replace(/(.{4})/g, '$1 ').trim()

/**
 * The note as a link. The secret rides in the fragment, which browsers never
 * send to a server — so a messenger's link-preview bot fetching this URL gets
 * the page without the money.
 */
export const tipClaimUrl = (code: string, origin: string) => `${origin}/t#${code}`
