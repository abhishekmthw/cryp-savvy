import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
    "./hooks/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        surface:  "#0f172a",   // page background
        card:     "#1e293b",   // card background
        border:   "#334155",   // subtle border
        muted:    "#64748b",   // secondary text
        accent:   "#3b82f6",   // primary blue
        success:  "#10b981",
        danger:   "#ef4444",
        warning:  "#f59e0b",
      },
    },
  },
  plugins: [],
};

export default config;
