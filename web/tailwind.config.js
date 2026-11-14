// Colours come from CSS variables in src/index.css so the light and dark themes share class names.
const v = (name) => `rgb(var(--c-${name}) / <alpha-value>)`;

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Titillium Web"', "system-ui", "-apple-system", '"Segoe UI"', "Roboto", "sans-serif"],
        mono: ['"Roboto Mono"', "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        // Titillium Web runs small: nudge the dense sizes up so panels stay readable.
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
        xs: ["0.8125rem", { lineHeight: "1.15rem" }],
        sm: ["0.9375rem", { lineHeight: "1.35rem" }],
      },
      colors: {
        canvas: v("canvas"),
        surface: v("surface"),
        sunken: v("sunken"),
        line: v("line"),
        "line-strong": v("line-strong"),
        ink: v("ink"),
        muted: v("muted"),
        primary: { DEFAULT: v("primary"), hover: v("primary-hover"), soft: v("primary-soft") },
        link: v("link"),
        chrome: { DEFAULT: v("chrome"), deep: v("chrome-deep"), ink: v("chrome-ink"), muted: v("chrome-muted"), line: v("chrome-line") },
        real: v("real"),
        estimated: v("estimated"),
        simulated: v("simulated"),
        whatif: v("whatif"),
        danger: v("danger"),
      },
      boxShadow: {
        panel: "0 1px 2px rgb(var(--c-shadow) / 0.08), 0 4px 16px rgb(var(--c-shadow) / 0.08)",
        float: "0 2px 6px rgb(var(--c-shadow) / 0.16), 0 12px 32px rgb(var(--c-shadow) / 0.18)",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "rise-in": { from: { opacity: "0", transform: "translateY(6px)" }, to: { opacity: "1", transform: "none" } },
        "slide-in-right": { from: { opacity: "0", transform: "translateX(16px)" }, to: { opacity: "1", transform: "none" } },
        shimmer: { from: { backgroundPosition: "200% 0" }, to: { backgroundPosition: "-200% 0" } },
        "pulse-ring": { "0%": { transform: "scale(0.9)", opacity: "0.7" }, "100%": { transform: "scale(1.9)", opacity: "0" } },
        level: { "0%, 100%": { transform: "scaleY(0.35)" }, "50%": { transform: "scaleY(1)" } },
      },
      animation: {
        "fade-in": "fade-in 180ms ease-out both",
        "rise-in": "rise-in 220ms cubic-bezier(0.2, 0.7, 0.2, 1) both",
        "slide-in-right": "slide-in-right 240ms cubic-bezier(0.2, 0.7, 0.2, 1) both",
        shimmer: "shimmer 1.6s linear infinite",
        "pulse-ring": "pulse-ring 1.6s ease-out infinite",
        level: "level 900ms ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
