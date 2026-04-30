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
        app: {
          bg: "var(--color-bg)",
          text: "var(--color-text)",
          muted: "var(--color-muted)",
          line: "var(--color-line)",
          surface: "var(--color-surface)",
          accent: "var(--color-accent)",
          "accent-soft": "var(--color-accent-soft)",
          success: "var(--color-success)",
          danger: "var(--color-danger)",
        },
      },
      fontFamily: {
        sans: ["var(--font-body)"],
        display: ["var(--font-body)"],
      },
      boxShadow: {
        panel: "0 10px 36px rgba(5, 26, 43, 0.08)",
      },
    },
  },
  plugins: [],
}
