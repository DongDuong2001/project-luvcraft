module.exports = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
    "./hooks/**/*.{js,ts,jsx,tsx}",
    "./state/**/*.{js,ts,jsx,tsx}",
    "./services/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--color-bg)",
        foreground: "var(--color-text)",
        border: "var(--color-line)",
        input: "var(--color-line)",
        ring: "var(--color-accent)",
        primary: {
          DEFAULT: "var(--color-accent)",
          foreground: "#ffffff",
        },
        secondary: {
          DEFAULT: "var(--color-surface-strong)",
          foreground: "var(--color-text)",
        },
        muted: {
          DEFAULT: "var(--color-surface-strong)",
          foreground: "var(--color-muted)",
        },
        accent: {
          DEFAULT: "var(--color-accent-soft)",
          foreground: "#ffffff",
        },
        card: {
          DEFAULT: "var(--color-surface)",
          foreground: "var(--color-text)",
        },
        app: {
          bg: "var(--color-bg)",
          "bg-soft": "var(--color-bg-soft)",
          text: "var(--color-text)",
          muted: "var(--color-muted)",
          line: "var(--color-line)",
          surface: "var(--color-surface)",
          "surface-strong": "var(--color-surface-strong)",
          accent: "var(--color-accent)",
          "accent-soft": "var(--color-accent-soft)",
          "accent-faint": "var(--color-accent-faint)",
          "accent-hover": "var(--color-accent-hover)",
          success: "var(--color-success)",
          danger: "var(--color-danger)",
          sidebar: "var(--color-sidebar)",
          "card-glow": "var(--color-card-glow)",
        },
      },
      fontFamily: {
        sans: ["var(--font-body)"],
        display: ["var(--font-body)"],
      },
      boxShadow: {
        panel: "0 0 0 1px rgba(255,255,255,0.03)",
      },
      animation: {
        "fade-rise": "fade-rise 400ms ease-out both",
        "fade-rise-delay": "fade-rise 400ms ease-out 60ms both",
        "fade-rise-delay-2": "fade-rise 400ms ease-out 120ms both",
        "fade-rise-delay-3": "fade-rise 400ms ease-out 180ms both",
      },
      keyframes: {
        "fade-rise": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
}
