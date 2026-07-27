// Nitro cache storage: Redis + gzip.
//
// The default production cache mount is the in-process memory driver, which
// never evicts: crawlers walking the ~90k transit stop URLs × 6 locales grew
// the V8 heap to its 4GB limit and OOM-crashed the SSR server every ~2h
// (2026-07-06 incident). Redis bounds it: per-entry EX TTL plus the
// instance's volatile-lru policy. Values are gzipped before write — SSR
// HTML/payload JSON compresses ~7x, keeping the shared Redis small.
//
// Degrades gracefully: if Redis is down every op fails fast (no offline
// queue) and pages simply render uncached.

import Redis from 'ioredis'
import { gzip, gunzip } from 'node:zlib'
import { promisify } from 'node:util'

const gzipAsync = promisify(gzip)
const gunzipAsync = promisify(gunzip)

// Above the largest route-rule maxAge (3600) so SWR can still serve a stale
// entry while revalidating; Redis then drops whatever crawlers never revisit.
const TTL_SECONDS = 7200

export default defineNitroPlugin(() => {
  // Key namespace MUST include the build id: prod and the dev slots share this
  // Redis (and cache keys vary only by host, which is parahub.io for all of
  // them), and entries outlive deploys. Without the build id one slot serves
  // HTML rendered by another build, whose /_nuxt chunk hashes 404 — an
  // unhydrated dead page for up to maxAge. Old-build keys age out via TTL.
  const buildId = useRuntimeConfig().app?.buildId || 'unknown'
  const PREFIX = `nitro-cache:${buildId}:`

  const redis = new Redis({
    host: '127.0.0.1',
    port: 6379,
    db: 2, // 0/1 belong to Django cache / Channels
    connectTimeout: 2000,
    maxRetriesPerRequest: 1,
    enableOfflineQueue: false,
  })

  // Without an error listener ioredis emits an unhandled 'error' event and
  // crashes the process the moment Redis goes away.
  let lastErrorLog = 0
  const logError = (op: string, err: unknown) => {
    const now = Date.now()
    if (now - lastErrorLog > 60_000) {
      lastErrorLog = now
      console.error(`[cache-redis] ${op} failed (further errors muted 60s):`, err)
    }
  }
  redis.on('error', (err) => logError('connection', err))

  const k = (key: string) => PREFIX + key

  useStorage().mount('cache', {
    name: 'redis-gzip',
    options: {},
    async hasItem(key: string) {
      try {
        return (await redis.exists(k(key))) > 0
      } catch (err) {
        logError('exists', err)
        return false
      }
    },
    async getItem(key: string) {
      try {
        const buf = await redis.getBuffer(k(key))
        return buf ? (await gunzipAsync(buf)).toString('utf8') : null
      } catch (err) {
        logError('get', err)
        return null
      }
    },
    async setItem(key: string, value: string) {
      try {
        const packed = await gzipAsync(Buffer.from(value))
        await redis.set(k(key), packed, 'EX', TTL_SECONDS)
      } catch (err) {
        logError('set', err)
      }
    },
    async removeItem(key: string) {
      try {
        await redis.del(k(key))
      } catch (err) {
        logError('del', err)
      }
    },
    async getKeys(base: string) {
      try {
        const keys: string[] = []
        const stream = redis.scanStream({ match: k(base || '') + '*', count: 1000 })
        for await (const chunk of stream) keys.push(...(chunk as string[]))
        return keys.map((key) => key.slice(PREFIX.length))
      } catch (err) {
        logError('scan', err)
        return []
      }
    },
    async clear(base: string) {
      try {
        const stream = redis.scanStream({ match: k(base || '') + '*', count: 1000 })
        for await (const chunk of stream) {
          if ((chunk as string[]).length) await redis.del(...(chunk as string[]))
        }
      } catch (err) {
        logError('clear', err)
      }
    },
    dispose() {
      redis.disconnect()
    },
  })
})
