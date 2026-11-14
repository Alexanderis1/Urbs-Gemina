/** Two overlapping squares: the city and its twin. */
function Logo() {
  return (
    <svg viewBox="0 0 28 28" className="h-7 w-7" aria-hidden="true">
      <rect x="2" y="2" width="16" height="16" rx="1.5" fill="none" stroke="currentColor" strokeWidth="2" />
      <rect x="10" y="10" width="16" height="16" rx="1.5" fill="rgb(var(--c-brand-mark))" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

/** Name of the product and, under it, which of the two experiences this is. */
export function Brand({ tagline }: { tagline: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <Logo />
      <div className="leading-tight">
        <div className="text-lg font-bold tracking-tight">Urbs Gemina</div>
        <div className="text-2xs uppercase tracking-[0.1em] text-chrome-muted">{tagline}</div>
      </div>
    </div>
  );
}

export function SkipLink() {
  return (
    <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2">
      Skip to content
    </a>
  );
}
