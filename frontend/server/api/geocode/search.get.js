export default defineEventHandler(async (event) => {
  const query = getQuery(event)

  if (!query.q) {
    return {
      type: 'FeatureCollection',
      features: []
    }
  }

  try {
    // Use local Pelias geocoder
    const params = new URLSearchParams({
      text: query.q, // Pelias uses 'text' instead of 'q'
      size: query.limit || '10',
      // Layer prioritization: cities/regions first, then streets, then venues
      layers: 'locality,localadmin,region,country,county,neighbourhood,borough,street,venue'
    })

    // Add language if provided (no default language for global search)
    if (query.lang) {
      params.append('lang', query.lang)
    }

    // Add bounding box if provided (for local filtering)
    if (query.bbox) {
      const bbox = query.bbox.split(',')
      if (bbox.length === 4) {
        params.append('boundary.rect.min_lon', bbox[0])
        params.append('boundary.rect.min_lat', bbox[1])
        params.append('boundary.rect.max_lon', bbox[2])
        params.append('boundary.rect.max_lat', bbox[3])
      }
    }

    const response = await $fetch(`http://127.0.0.1:4000/v1/search?${params}`)

    // Sort results: 1) by layer priority, 2) by confidence (Pelias relevance score)
    const layerPriority = {
      'locality': 10,      // Cities, towns
      'localadmin': 9,     // Local admin areas
      'region': 8,         // States, provinces
      'county': 7,         // Counties
      'neighbourhood': 6,  // Neighbourhoods
      'country': 5,        // Countries
      'borough': 4,        // Boroughs
      'street': 3,         // Streets
      'venue': 2,          // POIs
      'address': 1         // Addresses
    }

    if (response.features) {
      response.features.sort((a, b) => {
        // First: sort by layer priority
        const priorityA = layerPriority[a.properties?.layer] || 0
        const priorityB = layerPriority[b.properties?.layer] || 0
        if (priorityB !== priorityA) {
          return priorityB - priorityA
        }
        // Second: within same layer, sort by confidence (higher = better)
        const confA = a.properties?.confidence || 0
        const confB = b.properties?.confidence || 0
        return confB - confA
      })
    }

    // Pelias returns GeoJSON format
    return response
  } catch (error) {
    console.error('Geocoding error:', error)
    return {
      type: 'FeatureCollection',
      features: [],
      error: 'Geocoding service temporarily unavailable'
    }
  }
})