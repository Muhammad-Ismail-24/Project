/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        void:    "var(--df-void)",
        bg:      "var(--df-bg)",
        surface: "var(--df-surface)",
        "surface-2": "var(--df-surface-2)",
        accent:  "var(--df-accent)",
        good:    "var(--df-good)",
        warn:    "var(--df-warn)",
        danger:  "var(--df-danger)",
        "text-dim":   "var(--df-text-dim)",
        "text-faint": "var(--df-text-faint)",
      },
      borderRadius: {
        df: "var(--df-radius)",
        "df-sm": "var(--df-radius-sm)",
      },
      boxShadow: {
        df: "var(--df-shadow)",
      },
      fontFamily: {
        // No display face was configured in the existing hero (plain font-sans + font-black).
        // Loaded Satoshi (display) + Inter (body) via Fontshare/Google Fonts in index.html.
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["Satoshi", "ui-sans-serif", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
}
