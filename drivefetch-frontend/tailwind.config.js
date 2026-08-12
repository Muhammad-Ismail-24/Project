/** @type {import('tailwindcss').Config} */
export default {
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
        'df-pattern': '#E5E5E5',
      },
      fontFamily: {
        'display': ['"Bebas Neue"', 'sans-serif'],
        'mono': ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
        'body': ['"Inter"', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        'brutal-sm': '3px 3px 0px 0px #000000',
        'brutal': '5px 5px 0px 0px #000000',
        'brutal-lg': '8px 8px 0px 0px #000000',
      },
      borderRadius: {
        'none': '0px',
      },
    },
  },
  plugins: [],
}
