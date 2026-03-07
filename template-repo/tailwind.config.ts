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
        // Brand kit can override these via CSS variables
        primary: {
          DEFAULT: "var(--color-primary, #3b82f6)",
          50: "var(--color-primary-50, #eff6ff)",
          100: "var(--color-primary-100, #dbeafe)",
          200: "var(--color-primary-200, #bfdbfe)",
          300: "var(--color-primary-300, #93c5fd)",
          400: "var(--color-primary-400, #60a5fa)",
          500: "var(--color-primary-500, #3b82f6)",
          600: "var(--color-primary-600, #2563eb)",
          700: "var(--color-primary-700, #1d4ed8)",
          800: "var(--color-primary-800, #1e40af)",
          900: "var(--color-primary-900, #1e3a8a)",
          950: "var(--color-primary-950, #172554)",
        },
        accent: {
          DEFAULT: "var(--color-accent, #8b5cf6)",
          50: "var(--color-accent-50, #f5f3ff)",
          100: "var(--color-accent-100, #ede9fe)",
          500: "var(--color-accent-500, #8b5cf6)",
          600: "var(--color-accent-600, #7c3aed)",
        },
        background: {
          DEFAULT: "var(--color-background, #ffffff)",
          muted: "var(--color-background-muted, #f8fafc)",
        },
        foreground: {
          DEFAULT: "var(--color-foreground, #0f172a)",
          muted: "var(--color-foreground-muted, #64748b)",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        heading: ["var(--font-heading)", "var(--font-sans)", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};

export default config;
