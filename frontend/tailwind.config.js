/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "media",
  theme: {
    extend: {
      colors: {
        surface: { light: "#fcfcfb", dark: "#1a1a19" },
        plane: { light: "#f9f9f7", dark: "#0d0d0d" },
      },
    },
  },
  plugins: [],
};
