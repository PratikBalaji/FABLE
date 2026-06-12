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
      backdropBlur: {
        xs: "2px",
        sm: "4px",
        md: "12px",
        lg: "20px",
        xl: "32px",
        "2xl": "48px",
      },
      boxShadow: {
        glass: "0 4px 32px 0 rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.06)",
        glow: "0 0 24px rgba(203,166,247,0.35)",
        "glow-blue": "0 0 24px rgba(137,180,250,0.35)",
        "glow-red": "0 0 24px rgba(243,139,168,0.35)",
        "glow-green": "0 0 24px rgba(166,227,161,0.35)",
      },
      keyframes: {
        "fade-in-up": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-glow": {
          "0%, 100%": { boxShadow: "0 0 8px rgba(203,166,247,0.2)" },
          "50%": { boxShadow: "0 0 28px rgba(203,166,247,0.6)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% center" },
          "100%": { backgroundPosition: "200% center" },
        },
        "thinking-dot": {
          "0%, 80%, 100%": { opacity: "0" },
          "40%": { opacity: "1" },
        },
      },
      animation: {
        "fade-in-up": "fade-in-up 0.35s ease-out forwards",
        "pulse-glow": "pulse-glow 2s ease-in-out infinite",
        shimmer: "shimmer 2s linear infinite",
        "thinking-1": "thinking-dot 1.4s ease-in-out 0s infinite",
        "thinking-2": "thinking-dot 1.4s ease-in-out 0.2s infinite",
        "thinking-3": "thinking-dot 1.4s ease-in-out 0.4s infinite",
      },
    },
  },
  plugins: [],
};
export default config;
