/**
 * Reverse geocode a coordinate to an area name via the local Pelias geocoder.
 *
 * Used by OpenSky mission cards to label each survey with its place
 * (freguesia / município / region) instead of raw coordinates.
 *
 * Layers are restricted to area-level units (locality/localadmin/county/region)
 * so a survey over open countryside resolves to its parish/municipality rather
 * than the nearest street address.
 *
 * GET /api/geocode/reverse?lat=41.987&lon=-8.477
 */
export default defineEventHandler(async (event) => {
  const q = getQuery(event)
  const lat = q.lat
  const lon = q.lon
  if (lat == null || lon == null) return { feature: null }

  try {
    const params = new URLSearchParams({
      'point.lat': String(lat),
      'point.lon': String(lon),
      size: '1',
      layers: 'locality,localadmin,county,region',
    })
    const r = await $fetch(`http://127.0.0.1:4000/v1/reverse?${params}`)
    const p = r?.features?.[0]?.properties
    if (!p) return { feature: null }
    return {
      feature: {
        name: p.name ?? null,
        locality: p.locality ?? null,
        localadmin: p.localadmin ?? null,
        county: p.county ?? null,
        region: p.region ?? null,
        country: p.country ?? null,
        label: p.label ?? null,
      },
    }
  } catch (e) {
    return { feature: null }
  }
})
