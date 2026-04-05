/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './_template.html',
    './**/output/**/*.html',
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#FFE216',
          50: '#FFFEF0',
          100: '#FFFBD0',
          200: '#FFF7A1',
          400: '#FFEA46',
          500: '#FFE216',
          600: '#E6CA00',
        },
        secondary: {
          DEFAULT: '#0891B2',
          400: '#22D3EE',
          500: '#06B6D4',
          600: '#0891B2',
          700: '#0E7490',
        },
      },
    },
  },
  plugins: [],
}
