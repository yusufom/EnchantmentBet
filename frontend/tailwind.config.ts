import type { Config } from "tailwindcss";

// Dark-committed theme. Data colors are the validated dark-mode palette from
// the dataviz reference: blue/orange series pair, gray diverging midpoint,
// reserved status steps.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        page: "#0d0d0d",
        surface: "#1a1a19",
        raised: "#232322",
        ink: "#ffffff",
        ink2: "#c3c2b7",
        muted: "#898781",
        line: "#2c2c2a",
        home: "#3987e5",
        away: "#d95926",
        draw: "#6b6a66",
        good: "#0ca30c",
        warn: "#fab219",
        serious: "#ec835a",
      },
      fontFamily: {
        sans: ["system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
