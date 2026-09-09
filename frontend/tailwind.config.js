/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['Clash Display', 'Cabinet Grotesk', 'Syne', 'sans-serif'],
        sans: ['Satoshi', 'Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        brutal: {
          base: '#E4E2DD',
          dark: '#1E1E1E',
          red: '#DB4A2B',
          orange: '#F8A348',
          pink: '#FF89A9',
        },
      },
    },
  },
  plugins: [],
}
