export function Spinner({ className = 'w-4 h-4', light = false }) {
  return (
    <span
      aria-hidden="true"
      className={`inline-block rounded-full border-[3px] animate-spin ${light ? 'border-white/40 border-t-white' : 'border-neutral-300 border-t-df-red dark:border-zinc-700 dark:border-t-df-red'} ${className}`}
    />
  );
}

export function RoadLoader({ className = 'w-56' }) {
  return <div aria-hidden="true" className={`h-2 bg-neutral-200 dark:bg-zinc-800 df-road-loader ${className}`} />;
}

export function PageLoader({ label = 'Loading…' }) {
  return (
    <div role="status" className="flex min-h-[60vh] flex-col items-center justify-center gap-6 px-6">
      <RoadLoader />
      <span className="text-sm font-bold animate-df-pulse">{label}</span>
    </div>
  );
}

export function TypingDots({ label = 'Typing' }) {
  return (
    <span className="inline-flex items-center gap-1.5" aria-label={label} role="status">
      <span className="df-dot" />
      <span className="df-dot [animation-delay:.2s]" />
      <span className="df-dot [animation-delay:.4s]" />
    </span>
  );
}
