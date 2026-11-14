// Shared building blocks. Every screen is assembled from these so spacing, type and motion stay consistent.
// Rules of use are in web/docs/design-system.md.
import { useState, type ReactNode } from "react";
import { AlertTriangle, ChevronDown, CircleAlert, Info, Loader2, type LucideIcon } from "lucide-react";

/** Screen with a docked control panel on the left and the map (or main content) filling the rest. */
export function Workspace({ panel, children, right }: { panel: ReactNode; children: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex h-full min-h-0">
      {panel}
      <div className="relative min-w-0 flex-1">{children}</div>
      {right}
    </div>
  );
}

/** Docked side panel: fixed header, scrolling body, optional fixed footer. */
export function Panel({
  title,
  subtitle,
  icon: Icon,
  actions,
  footer,
  side = "left",
  width = "w-[22rem]",
  children,
}: {
  title: string;
  subtitle?: ReactNode;
  icon?: LucideIcon;
  actions?: ReactNode;
  footer?: ReactNode;
  side?: "left" | "right";
  width?: string;
  children: ReactNode;
}) {
  return (
    <aside className={`panel ${width} ${side === "left" ? "border-r" : "animate-slide-in-right border-l"}`} aria-label={title}>
      <header className="flex items-start gap-2.5 border-b border-line px-4 py-3">
        {Icon && <Icon className="mt-0.5 h-5 w-5 shrink-0 text-link" aria-hidden="true" />}
        <div className="min-w-0 flex-1">
          <h1 className="text-base font-bold leading-tight">{title}</h1>
          {subtitle && <p className="hint mt-0.5">{subtitle}</p>}
        </div>
        {actions}
      </header>
      <div className="panel-body">{children}</div>
      {footer && <footer className="border-t border-line bg-sunken px-4 py-3">{footer}</footer>}
    </aside>
  );
}

/** Titled group inside a panel. `collapsible` folds secondary content away. */
export function Section({
  title,
  aside,
  collapsible = false,
  defaultOpen = true,
  children,
}: {
  title: string;
  aside?: ReactNode;
  collapsible?: boolean;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const shown = !collapsible || open;
  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        {collapsible ? (
          <button type="button" className="label flex items-center gap-1 hover:text-ink" aria-expanded={open} onClick={() => setOpen(!open)}>
            <ChevronDown className={`h-3.5 w-3.5 transition-transform duration-200 ${open ? "" : "-rotate-90"}`} aria-hidden="true" />
            {title}
          </button>
        ) : (
          <h2 className="label">{title}</h2>
        )}
        {aside}
      </div>
      {shown && <div className="animate-fade-in space-y-2">{children}</div>}
    </section>
  );
}

/** Label + control + optional help text. Wraps the control in a <label> so clicks and screen readers work. */
export function Field({ label, hint, children, className = "" }: { label: string; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={`block space-y-1 ${className}`}>
      <span className="block text-xs font-semibold text-ink">{label}</span>
      {children}
      {hint && <span className="hint block">{hint}</span>}
    </label>
  );
}

/** Two to four mutually exclusive choices, shown side by side. */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { id: T; label: string; icon?: LucideIcon }[];
  label: string;
}) {
  return (
    <div role="tablist" aria-label={label} className="grid auto-cols-fr grid-flow-col gap-0.5 rounded border border-line bg-sunken p-0.5">
      {options.map((o) => {
        const active = o.id === value;
        return (
          <button
            key={o.id}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(o.id)}
            className={`inline-flex min-h-8 items-center justify-center gap-1.5 rounded-sm px-2 text-sm font-semibold transition-all duration-150 ${
              active ? "bg-surface text-link shadow-panel" : "text-muted hover:text-ink"
            }`}
          >
            {o.icon && <o.icon className="h-4 w-4" aria-hidden="true" />}
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/** One headline figure. Numbers come from tool runs; pass them through unchanged. */
export function Stat({
  label,
  value,
  unit,
  note,
  tone = "ink",
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  note?: ReactNode;
  tone?: "ink" | "danger" | "real" | "estimated" | "simulated" | "whatif";
}) {
  const color = { ink: "text-ink", danger: "text-danger", real: "text-real", estimated: "text-estimated", simulated: "text-simulated", whatif: "text-whatif" }[tone];
  return (
    <div className="min-w-0 rounded border border-line bg-sunken px-3 py-2">
      <div className="label leading-tight">{label}</div>
      <div className={`num mt-0.5 text-xl font-medium leading-tight ${color}`}>
        {value}
        {unit && <span className="ml-1 text-xs font-normal text-muted">{unit}</span>}
      </div>
      {note && <div className="hint mt-0.5">{note}</div>}
    </div>
  );
}

const CALLOUT = {
  info: { icon: Info, cls: "border-link/40 bg-primary-soft text-ink", iconCls: "text-link" },
  warn: { icon: AlertTriangle, cls: "border-estimated/50 bg-estimated/10 text-ink", iconCls: "text-estimated" },
  error: { icon: CircleAlert, cls: "border-danger/50 bg-danger/10 text-ink", iconCls: "text-danger" },
} as const;

/** Inline message. `warn` for caveats, `error` for failures, `info` for guidance. */
export function Callout({ tone = "info", title, children }: { tone?: keyof typeof CALLOUT; title?: string; children?: ReactNode }) {
  const c = CALLOUT[tone];
  return (
    <div role={tone === "error" ? "alert" : "note"} className={`flex animate-fade-in gap-2 rounded border-l-4 px-3 py-2 text-sm ${c.cls}`}>
      <c.icon className={`mt-0.5 h-4 w-4 shrink-0 ${c.iconCls}`} aria-hidden="true" />
      <div className="min-w-0 space-y-0.5 break-words">
        {title && <div className="font-semibold">{title}</div>}
        {children && <div className="text-xs leading-snug">{children}</div>}
      </div>
    </div>
  );
}

/** Shown where results will appear, before the first run. */
export function EmptyState({ icon: Icon, title, children }: { icon: LucideIcon; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded border border-dashed border-line-strong px-4 py-8 text-center">
      <Icon className="h-7 w-7 text-muted" aria-hidden="true" />
      <div className="text-sm font-semibold">{title}</div>
      {children && <p className="hint max-w-xs">{children}</p>}
    </div>
  );
}

/** Grey bars while a tool run is in flight. */
export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-2" role="status" aria-label="Loading">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton h-3.5" style={{ width: `${92 - ((i * 17) % 40)}%` }} />
      ))}
    </div>
  );
}

export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return <Loader2 className={`animate-spin ${className}`} aria-hidden="true" />;
}

/** Colour scale under a map layer. */
export function LegendRamp({ gradient, low, high, mid }: { gradient: string; low: string; high: string; mid?: string }) {
  return (
    <div>
      <div className="h-2 rounded-sm border border-line" style={{ background: gradient }} />
      <div className="mt-1 flex justify-between gap-2 text-2xs text-muted">
        <span>{low}</span>
        {mid && <span className="truncate font-semibold text-ink">{mid}</span>}
        <span>{high}</span>
      </div>
    </div>
  );
}

/** Card that floats over the map (legend, status chip). */
export function MapFloat({ position, children, className = "" }: { position: "top-left" | "bottom-left" | "top-center"; children: ReactNode; className?: string }) {
  const pos = { "top-left": "left-3 top-3", "bottom-left": "bottom-8 left-3", "top-center": "left-1/2 top-3 -translate-x-1/2" }[position];
  return <div className={`map-float pointer-events-auto absolute z-10 max-w-sm animate-rise-in px-3 py-2 ${pos} ${className}`}>{children}</div>;
}

/** Centred page for screens without a map (tables, logs). */
export function Page({ title, lead, icon: Icon, actions, children }: { title: string; lead?: ReactNode; icon?: LucideIcon; actions?: ReactNode; children: ReactNode }) {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl animate-rise-in space-y-4 px-6 py-5">
        <header className="flex items-start gap-3">
          {Icon && <Icon className="mt-1 h-6 w-6 shrink-0 text-link" aria-hidden="true" />}
          <div className="min-w-0 flex-1">
            <h1 className="page-title">{title}</h1>
            {lead && <div className="mt-1 max-w-3xl text-sm text-muted">{lead}</div>}
          </div>
          {actions}
        </header>
        {children}
      </div>
    </div>
  );
}
