/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef2ff",
          100: "#e0e7ff",
          200: "#c7d2fe",
          300: "#a5b4fc",
          400: "#818cf8",
          500: "#6366f1",
          600: "#4f46e5",
          700: "#4338ca",
          800: "#3730a3",
          900: "#312e81",
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
    },
  },
  plugins: [],
};
