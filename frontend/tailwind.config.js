/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        navy: '#0F1B3D',
        gold: '#B8892B',
        paper: '#F5F1EA',
      },
      fontFamily: {
        display: ['"Source Serif 4"', 'serif'],
        body: ['Inter', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
