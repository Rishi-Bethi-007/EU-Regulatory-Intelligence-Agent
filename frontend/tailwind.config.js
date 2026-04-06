/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        eu: {
          blue:   '#003399',
          yellow: '#FFCC00',
        },
      },
    },
  },
  plugins: [],
}
