/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#ecfdf5",
          100: "#d1fae5",
          200: "#a7f3d0",
          300: "#6ee7b7",
          400: "#34d399",
          500: "#10b981",
          600: "#059669",
          700: "#047857",
          800: "#065f46",
          900: "#064e3b",
        },
        profit: {
          DEFAULT: "#16a34a",
          soft: "#dcfce7",
        },
        loss: {
          DEFAULT: "#dc2626",
          soft: "#fee2e2",
        },
      },
      boxShadow: {
        card: "0 1px 2px rgba(15,23,42,.04), 0 1px 3px rgba(15,23,42,.06)",
        pop: "0 4px 16px rgba(15,23,42,.10)",
      },
      borderRadius: {
        xl: "12px",
      },
    },
  },
  plugins: [],
};
