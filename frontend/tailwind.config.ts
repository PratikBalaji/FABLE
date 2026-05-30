import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Obsidian Catppuccin-inspired palette
        base:    "#1e1e2e",
        mantle:  "#181825",
        crust:   "#11111b",
        surface0:"#313244",
        surface1:"#45475a",
        surface2:"#585b70",
        text:    "#cdd6f4",
        subtext: "#a6adc8",
        overlay: "#6c7086",
        accent:  "#cba6f7",   // mauve
        blue:    "#89b4fa",
        green:   "#a6e3a1",
        red:     "#f38ba8",
        yellow:  "#f9e2af",
        teal:    "#94e2d5",
      },
      fontFamily: {
        mono: ["'JetBrains Mono'", "monospace"],
        sans: ["Inter", "sans-serif"],
      },
    },
  },
  plugins: [],
};
export default config;
