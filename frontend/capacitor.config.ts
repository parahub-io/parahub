import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'io.parahub.app',
  appName: 'Parahub',
  webDir: 'dist',

  server: {
    // Production: load from parahub.io (no local static files needed)
    url: 'https://parahub.io',
    // Allow navigation to these origins
    allowNavigation: [
      'parahub.io',
      '*.parahub.io',
    ],
  },

  plugins: {
    SplashScreen: {
      launchAutoHide: true,
      launchShowDuration: 1500,
      backgroundColor: '#eab308', // Parahub yellow
      showSpinner: false,
    },
    SystemBars: {
      style: 'LIGHT',
      insetsHandling: 'css', // Injects --safe-area-inset-* CSS vars; layout uses them to shrink container
    },
    Keyboard: {
      resize: 'body',
      resizeOnFullScreen: false, // Must be false for Android 15+ edge-to-edge
    },
    PushNotifications: {
      presentationOptions: ['badge', 'sound', 'alert'],
    },
  },

  // Android-specific
  android: {
    allowMixedContent: false,
    captureInput: true,
    webContentsDebuggingEnabled: true,
  },

  // iOS-specific
  ios: {
    contentInset: 'automatic',
    scrollEnabled: true,
  },
}

export default config
