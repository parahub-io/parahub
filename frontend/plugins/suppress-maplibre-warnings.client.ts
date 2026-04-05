/**
 * Suppress MapLibre GL missing sprite warnings in console
 * and log them to server instead
 */

const loggedImages = new Set<string>();

async function logMissingImageToServer(imageId: string) {
  if (loggedImages.has(imageId)) return;
  loggedImages.add(imageId);

  try {
    await fetch('/api/v1/geo/log-missing-image', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image_id: imageId,
        user_agent: navigator.userAgent
      })
    });
  } catch (error) {
    // Silently fail - don't spam console
  }
}

export default defineNuxtPlugin(() => {
  if (typeof window !== 'undefined' && !window._maplibreWarnSuppressed) {
    const originalWarn = console.warn.bind(console);

    console.warn = function(...args: any[]) {
      const message = args[0]?.toString() || '';

      // Suppress MapLibre missing image warnings and log to server
      if (message.includes('could not be loaded') && message.includes('map.addImage()')) {
        // Extract image name from warning message
        // Format: 'Image "gate" could not be loaded...'
        const match = message.match(/Image "([^"]+)"/);
        if (match && match[1]) {
          const imageId = match[1];
          // Log to server asynchronously (don't block)
          logMissingImageToServer(imageId);
        }
        // Suppress console output
        return;
      }

      // Pass through all other warnings
      originalWarn(...args);
    };

    window._maplibreWarnSuppressed = true;
  }
});
