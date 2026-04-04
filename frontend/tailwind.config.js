/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      keyframes: {
        loadbar: {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(350%)' },
        },
      },
      animation: {
        loadbar: 'loadbar 1.4s ease-in-out infinite',
      },
      colors: {
        dark: {
          bg: '#0f0f23',
          bg2: '#1a1a2e',
          card: '#1e1e2e',
          border: '#2d2d44',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
