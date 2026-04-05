import { scryptAsync } from '@noble/hashes/scrypt.js'
import { bytesToHex } from '@noble/hashes/utils.js'

export interface PoWProof {
  challenge: string
  hash: string
}

export interface PoWParams {
  N: number
  r: number
  p: number
  dkLen: number
}

const SALT = new TextEncoder().encode('parahub-pow-v1')

/**
 * Scrypt PoW: single memory-hard computation.
 * GPU resistance: ~10-20x (vs 1000-10000x for SHA-256).
 * N=65536: ~1-2s on phone, ~50-100ms on GPU — enough to deter bot farms.
 * No nonce loop — difficulty IS the scrypt params.
 */
export async function solvePoW(challenge: string, params: PoWParams): Promise<PoWProof> {
  const input = new TextEncoder().encode(challenge)
  const hashBytes = await scryptAsync(input, SALT, {
    N: params.N,
    r: params.r,
    p: params.p,
    dkLen: params.dkLen,
  })
  return { challenge, hash: bytesToHex(hashBytes) }
}
