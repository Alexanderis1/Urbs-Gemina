/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        real: "#15803d",
        estimated: "#b45309",
        simulated: "#7c3aed",
        roma: { DEFAULT: "#8b1e2d", light: "#f5e9d8" },
      },
    },
  },
  plugins: [],
};
