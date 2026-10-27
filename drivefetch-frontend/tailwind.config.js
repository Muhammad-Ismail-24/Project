/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'df-white': '#FFFFFF',
        'df-grey': '#F5F5F5',
        'df-black': '#000000',
        'df-red': '#E5202E',
        'df-red-dark': '#B3121D',
        'df-pattern': '#E5E5E5',
        'df-night': '#09090B',
      },
      fontFamily: {
        'display': ['"Archivo"', '"Helvetica Neue"', 'Arial', 'sans-serif'],
        'body': ['"Archivo"', '"Helvetica Neue"', 'Arial', 'sans-serif'],
        'sans': ['"Archivo"', '"Helvetica Neue"', 'Arial', 'sans-serif'],
        'mono': ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      keyframes: {
        'df-fade-up': { from: { opacity: '0', transform: 'translateY(8px)' }, to: { opacity: '1', transform: 'none' } },
        'df-slide-in-right': { from: { transform: 'translateX(100%)' }, to: { transform: 'none' } },
        'df-slide-in-left': { from: { transform: 'translateX(-100%)' }, to: { transform: 'none' } },
        'df-wipe-down': { from: { clipPath: 'inset(0 0 100% 0)' }, to: { clipPath: 'inset(0 0 0 0)' } },
        'df-road': { from: { backgroundPosition: '0 0' }, to: { backgroundPosition: '-80px 0' } },
        'df-dot': { '0%, 80%, 100%': { opacity: '.25' }, '40%': { opacity: '1' } },
        'df-pulse': { '0%, 100%': { opacity: '.4' }, '50%': { opacity: '1' } },
        'df-spin-in': { from: { opacity: '0', transform: 'rotate(-90deg) scale(.6)' }, to: { opacity: '1', transform: 'none' } },
      },
      animation: {
        'df-fade-up': 'df-fade-up .3s ease-out both',
        'df-slide-in-right': 'df-slide-in-right .28s cubic-bezier(.2,.8,.2,1) both',
        'df-slide-in-left': 'df-slide-in-left .24s cubic-bezier(.2,.8,.2,1) both',
        'df-wipe-down': 'df-wipe-down .32s cubic-bezier(.76,0,.24,1) both',
        'df-road': 'df-road .6s linear infinite',
        'df-dot': 'df-dot 1.2s infinite',
        'df-pulse': 'df-pulse 1.6s infinite',
        'df-spin-in': 'df-spin-in .5s cubic-bezier(.19,1,.22,1) both',
      },
    },
  },
  plugins: [],
}
