// Binds the locally stored wallet seed to the Parahub account that created it.
//
// The seed (parahub_seed) and the PGP keypair derived from it live in
// localStorage independently of the Django session, so an account switch in
// the same browser would otherwise open — and sync onto the new account's
// profile — a wallet belonging to someone else.
//
// Ownership anchor: Account ULID (stable across username changes), stamped
// when the seed is saved. Legacy seeds without a stamp are verified by
// comparing the stored PGP keypair's fingerprint against the fingerprints
// registered on the account's profiles (any profile — a seed may have been
// set up under a pseudonym); on match the stamp is written retroactively.

export type SeedOwnership = 'owned' | 'foreign' | 'unverified'

const OWNER_KEY = 'parahub_seed_owner'
const PGP_KEYS_KEY = 'parahub_pgp_keys'

interface WalletOwnerResponse {
  authenticated: boolean
  account_id?: string
  pgp_fingerprints?: string[]
}

export function getSeedOwner(): string | null {
  if (!process.client) return null
  return localStorage.getItem(OWNER_KEY)
}

export function stampSeedOwner(accountId: string): void {
  if (!process.client || !accountId) return
  localStorage.setItem(OWNER_KEY, accountId)
}

export function clearSeedOwnerStamp(): void {
  if (!process.client) return
  localStorage.removeItem(OWNER_KEY)
}

async function fetchWalletOwner(): Promise<WalletOwnerResponse | null> {
  const res = await $fetch<WalletOwnerResponse>('/api/v1/auth/wallet-owner/', {
    credentials: 'include',
    headers: { 'Accept': 'application/json' }
  })
  return res?.authenticated ? res : null
}

/** Stamp the current account as seed owner. Call right after saving a seed. */
export async function stampSeedOwnerFromSession(): Promise<void> {
  if (!process.client) return
  try {
    const owner = await fetchWalletOwner()
    if (owner?.account_id) stampSeedOwner(owner.account_id)
  } catch {
    // Stamp is an optimization on top of the fingerprint fallback — never
    // let it break the seed setup/restore flow
  }
}

function getStoredPgpFingerprint(): string | null {
  if (!process.client) return null
  try {
    const stored = localStorage.getItem(PGP_KEYS_KEY)
    if (!stored) return null
    return JSON.parse(stored)?.fingerprint || null
  } catch {
    return null
  }
}

/**
 * Decide whether the seed stored in this browser belongs to the current
 * account.
 *
 * 'unverified' means neither proof nor refutation was possible (no stamp and
 * no fingerprint pair to compare, or the ownership fetch failed). Callers may
 * still show the wallet then, but MUST NOT sync wallet identifiers
 * (spark_address / ln_address) onto the profile — blocking an owner whose
 * fingerprint registration failed is worse than a read-only session, while
 * profile contamination is irreversible without manual cleanup.
 */
export async function checkSeedOwnership(): Promise<SeedOwnership> {
  if (!process.client) return 'unverified'

  let owner: WalletOwnerResponse | null = null
  try {
    owner = await fetchWalletOwner()
  } catch {
    return 'unverified'
  }
  if (!owner?.account_id) return 'unverified'

  const stamped = getSeedOwner()
  if (stamped) return stamped === owner.account_id ? 'owned' : 'foreign'

  // Legacy seed (saved before owner stamping): the PGP keypair derived from
  // it travels alongside in localStorage — compare fingerprints
  const storedFp = getStoredPgpFingerprint()
  if (!storedFp || !owner.pgp_fingerprints?.length) return 'unverified'

  const match = owner.pgp_fingerprints.some(
    fp => fp.toLowerCase() === storedFp.toLowerCase()
  )
  if (match) {
    stampSeedOwner(owner.account_id)
    return 'owned'
  }
  return 'foreign'
}
