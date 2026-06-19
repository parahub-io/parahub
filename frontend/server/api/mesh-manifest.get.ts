import { readFile } from 'node:fs/promises'

const MANIFEST_PATH = '/opt/parahub-mesh/output/manifest.json'

export default defineEventHandler(async () => {
  try {
    const raw = await readFile(MANIFEST_PATH, 'utf-8')
    return JSON.parse(raw)
  } catch (err) {
    console.error('mesh-manifest read failed:', err)
    return { version: null, devices: {} }
  }
})
