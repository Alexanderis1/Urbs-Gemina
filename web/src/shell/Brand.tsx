import { LANGS, LANG_LABEL, setLang, texts, tr, useLang } from "@/lib/i18n";

const T = texts({
  en: { skip: "Skip to content", language: "Language" },
  it: { skip: "Vai al contenuto", language: "Lingua" },
});

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
      {tr(T).skip}
    </a>
  );
}

/** IT | EN in the header. Italian comes first and is the default. */
export function LangSwitch() {
  const lang = useLang();
  return (
    <div role="group" aria-label={tr(T).language} className="flex overflow-hidden rounded border border-chrome-line text-2xs font-bold">
      {LANGS.map((l) => (
        <button
          key={l}
          type="button"
          lang={l}
          title={LANG_LABEL[l]}
          aria-pressed={l === lang}
          onClick={() => setLang(l)}
          className={`min-h-9 px-2 uppercase tracking-wide transition-colors duration-150 ${
            l === lang ? "bg-chrome-ink text-chrome" : "text-chrome-muted hover:bg-chrome-line hover:text-chrome-ink"
          }`}
        >
          {l}
        </button>
      ))}
    </div>
  );
}
