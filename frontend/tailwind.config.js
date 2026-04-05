/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./components/**/*.{js,vue,ts}",
    "./layouts/**/*.vue",
    "./pages/**/*.vue",
    "./plugins/**/*.{js,ts}",
    "./nuxt.config.{js,ts}",
    "./app.vue"
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Parahub Brand — split-complementary palette (Yellow ↔ Cyan base)
        primary: {
          DEFAULT: '#FFE216', // Parahub Yellow - CTA, active states, energy
          50: '#FFFEF0',
          100: '#FFFBD0',
          200: '#FFF7A1',
          300: '#FFF172',
          400: '#FFEA46',
          500: '#FFE216',
          600: '#E6CA00',
          700: '#BFA800',
          800: '#998700',
          900: '#736500',
        },
        secondary: {
          DEFAULT: '#4E4EC8', // Electric Indigo (AA-safe) - desaturated, refined, unique to Parahub
          50: '#ECECFA',
          100: '#DCDCF5',
          200: '#C6C6ED',
          300: '#ABABE0',
          400: '#8E8ED4',
          500: '#4E4EC8',
          600: '#4242B0',
          700: '#363698',
          800: '#2A2A7D',
          900: '#1A1A5E',
        },
        success: {
          DEFAULT: '#059669', // Emerald - deeper, better white-text contrast
          50: '#ECFDF5',
          100: '#D1FAE5',
          200: '#A7F3D0',
          300: '#6EE7B7',
          400: '#34D399',
          500: '#059669',
          600: '#047857',
          700: '#065F46',
          800: '#064E3B',
          900: '#022C22',
        },
        warning: {
          DEFAULT: '#D97706', // Amber - clear separation from primary yellow
          50: '#FFFBEB',
          100: '#FEF3C7',
          200: '#FDE68A',
          300: '#FCD34D',
          400: '#FBBF24',
          500: '#D97706',
          600: '#B45309',
          700: '#92400E',
          800: '#78350F',
          900: '#451A03',
        },
        error: {
          DEFAULT: '#DC2626', // Red 600 - less aggressive for P2P community
          50: '#FEF2F2',
          100: '#FEE2E2',
          200: '#FECACA',
          300: '#FCA5A5',
          400: '#F87171',
          500: '#DC2626',
          600: '#B91C1C',
          700: '#991B1B',
          800: '#7F1D1D',
          900: '#450A0A',
        },
        // Zinc-based neutrals — cool undertone, intentional feel
        neutral: {
          50: '#FAFAFA',
          100: '#F4F4F5',
          200: '#E4E4E7',
          300: '#D4D4D8',
          400: '#A1A1AA',
          500: '#71717A',
          600: '#52525B',
          700: '#3F3F46',
          800: '#27272A',
          900: '#18181B',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-in-out',
        'slide-up': 'slideUp 0.3s ease-out',
      },
      transitionDuration: {
        DEFAULT: '0ms',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { 
            opacity: '0',
            transform: 'translateY(1rem)'
          },
          '100%': { 
            opacity: '1',
            transform: 'translateY(0)'
          },
        }
      }
    },
  },
  plugins: [],
  safelist: [
    'text-primary',
    'bg-primary',
    'border-primary',
    'text-secondary',
    'bg-secondary',
    'border-secondary',
    // Wallet gradient
    'from-primary-500',
    'to-warning-600',
    'bg-gradient-to-br',
    // UiBadge dynamic classes
    { pattern: /^bg-(primary|secondary|success|warning|error)(\/10)?$/ },
    { pattern: /^text-(primary|secondary|success|warning|error)(-\d+)?$/ },
    { pattern: /^text-(primary|secondary|success|warning|error)(-\d+)?$/, variants: ['dark'] },
    { pattern: /^border-(primary|secondary|success|warning|error)$/ },
    { pattern: /^bg-(primary|secondary|success|warning|error|neutral)-\d+$/ },
    // UiAlert dynamic classes
    { pattern: /^bg-(secondary|success|warning|error)-50$/ },
    { pattern: /^bg-(secondary|success|warning|error)-900/, variants: ['dark'] },
    { pattern: /^border-(secondary|success|warning|error)-200$/ },
    { pattern: /^border-(secondary|success|warning|error)-800$/, variants: ['dark'] },
    { pattern: /^text-(secondary|success|warning|error)-700$/ },
    { pattern: /^text-(secondary|success|warning|error)-800$/ },
    { pattern: /^text-(secondary|success|warning|error)-200$/, variants: ['dark'] },
    { pattern: /^text-(secondary|success|warning|error)-300$/, variants: ['dark'] },
  ]
}