import { forwardRef, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import Plate from '../ui/Plate';

const reducedMotion = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

/** Resolves once the intro has finished (html.df-ready), so demos don't play hidden. */
function whenReady(cb) {
  const root = document.documentElement;
  if (root.classList.contains('df-ready')) { cb(); return () => {}; }
  const mo = new MutationObserver(() => {
    if (root.classList.contains('df-ready')) { mo.disconnect(); cb(); }
  });
  mo.observe(root, { attributes: true, attributeFilter: ['class'] });
  return () => mo.disconnect();
}

/* ─────────────────────────────────────────────────────────
   Hero search input with a typewriter placeholder that cycles
   through example searches while the box is empty.
   ───────────────────────────────────────────────────────── */
const EXAMPLES = [
  'Civic 2018 or newer in Lahore under 50 lac',
  'Corolla in Karachi under 40 lac',
  'Aqua 2016+ Islamabad',
  'Automatic hatchback under 30 lac',
];

export const HeroSearchInput = forwardRef(function HeroSearchInput({ value, onChange }, ref) {
  const [text, setText] = useState(EXAMPLES[0]);
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (reducedMotion() || focused || value) return undefined;
    let ex = 0;
    let i = EXAMPLES[0].length;
    let deleting = true;
    let timer = 0;
    const tick = () => {
      const word = EXAMPLES[ex];
      if (deleting) {
        i -= 1;
        if (i <= 0) { deleting = false; ex = (ex + 1) % EXAMPLES.length; i = 0; }
      } else {
        i += 1;
        if (i >= EXAMPLES[ex].length) { deleting = true; setText(EXAMPLES[ex]); timer = setTimeout(tick, 2200); return; }
      }
      setText((deleting ? word : EXAMPLES[ex]).slice(0, Math.max(0, i)));
      timer = setTimeout(tick, deleting ? 22 : 48);
    };
    timer = setTimeout(tick, 2600);
    return () => clearTimeout(timer);
  }, [focused, value]);

  return (
    <input
      id="home-q"
      ref={ref}
      type="search"
      maxLength={200}
      value={value}
      onChange={onChange}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      placeholder={focused ? 'Make, model, city, budget' : text}
      autoComplete="off"
      className="flex-1 min-w-0 h-16 sm:h-[72px] px-5 sm:px-6 bg-transparent text-black text-lg sm:text-[22px] font-medium outline-none placeholder:text-neutral-500"
    />
  );
});

/* ─────────────────────────────────────────────────────────
   The two entry points, as big cards that fill red on hover.
   ───────────────────────────────────────────────────────── */
export function CtaCard({ n, kicker, title, desc, action, to, onClick, plate }) {
  const body = (
    <>
      <div className="flex items-start justify-between gap-4">
        <span className="font-mono text-[13px] font-semibold tracking-[0.08em] df-fill-muted df-muted">{n} · {kicker}</span>
        {plate}
      </div>
      <div className="flex flex-col gap-3 mt-auto">
        <span className="df-display text-[length:clamp(36px,4.4vw,76px)]">{title}</span>
        <span className="max-w-[440px] text-[17px] leading-relaxed df-fill-muted df-muted">{desc}</span>
      </div>
      <span className="flex items-center justify-between gap-4 pt-6 mt-2 border-t border-neutral-300 dark:border-zinc-700 group-hover:border-white/40 transition-colors duration-500 text-[15px] font-extrabold tracking-wide">
        {action}
        <span aria-hidden="true" className="df-fill-arrow w-12 h-12 flex items-center justify-center bg-black text-white dark:bg-zinc-50 dark:text-black">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="square"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
        </span>
      </span>
    </>
  );
  const cls = 'df-fill-card group flex flex-col gap-6 min-h-[380px] sm:min-h-[440px] p-6 sm:p-9 text-left bg-df-grey dark:bg-black border border-neutral-200 dark:border-zinc-800';
  return to ? <Link to={to} className={cls}>{body}</Link> : <button type="button" onClick={onClick} className={cls}>{body}</button>;
}

/* ─────────────────────────────────────────────────────────
   Direct search demo: an example ad gets scanned, the risky
   phrases light up one by one, then the verdict appears.
   ───────────────────────────────────────────────────────── */
export function AdScanDemo() {
  return (
    <div data-reveal="fade" className="relative bg-white dark:bg-df-night border border-black dark:border-zinc-700 shadow-[12px_12px_0_0_#000] dark:shadow-[12px_12px_0_0_#E5202E]">
      <div className="flex items-center justify-between gap-3 px-5 py-3 border-b border-black dark:border-zinc-700">
        <span className="font-mono text-xs font-semibold tracking-[0.08em]">EXAMPLE AD · OLX</span>
        <span className="font-mono text-xs font-semibold text-df-red-dark dark:text-df-red flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-df-red animate-df-pulse" /> SCANNING
        </span>
      </div>
      <div className="relative p-5 sm:p-6 flex flex-col gap-4 overflow-hidden">
        <span className="df-scanbar" aria-hidden="true" />
        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-1">
            <strong className="text-xl leading-snug">Honda Civic Oriel 1.8 2019</strong>
            <span className="font-mono text-xs df-muted">54,000 km · Lahore · Automatic</span>
          </div>
          <Plate top="PUNJAB" main="LHR 2019" size="sm" />
        </div>
        <p className="text-[17px] leading-[1.8]">
          Total <mark className="df-hl" style={{ '--d': '1.2s' }}>genuine</mark> car, just a{' '}
          <mark className="df-hl" style={{ '--d': '1.5s' }}>minor shower</mark> on one door. First owner,{' '}
          <mark className="df-hl" style={{ '--d': '1.8s' }}>duplicate file</mark> available.{' '}
          <mark className="df-hl" style={{ '--d': '2.1s' }}>Urgent sale</mark>, serious buyers only.
        </p>
        <div className="flex flex-wrap gap-2">
          <span data-late style={{ '--d': '2.5s' }} className="df-flag-risk">“Genuine” but repainted</span>
          <span data-late style={{ '--d': '2.65s' }} className="df-flag-risk">Duplicate file</span>
          <span data-late style={{ '--d': '2.8s' }} className="df-flag-warn">Pressure to buy fast</span>
        </div>
        <div data-late style={{ '--d': '3.05s' }} className="flex items-center gap-3 pt-4 border-t border-neutral-200 dark:border-zinc-800">
          <span className="w-9 h-9 shrink-0 bg-black text-white dark:bg-zinc-50 dark:text-black flex items-center justify-center font-black">!</span>
          <span className="text-[15px] font-semibold leading-snug">Verdict: ask for the paint report and the original file before you visit.</span>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   Types text once it scrolls into view (after the intro).
   ───────────────────────────────────────────────────────── */
export function TypeOnView({ text, speed = 30, startDelay = 400, className = '' }) {
  const ref = useRef(null);
  const [shown, setShown] = useState('');
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (reducedMotion() || !('IntersectionObserver' in window)) { setShown(text); setDone(true); return undefined; }
    let timer = 0;
    let stopReady = () => {};
    const io = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      io.disconnect();
      stopReady = whenReady(() => {
        let i = 0;
        const step = () => {
          i += 1;
          setShown(text.slice(0, i));
          if (i < text.length) timer = setTimeout(step, speed);
          else setDone(true);
        };
        timer = setTimeout(step, startDelay);
      });
    }, { threshold: 0.5 });
    if (ref.current) io.observe(ref.current);
    return () => { io.disconnect(); stopReady(); clearTimeout(timer); };
  }, [text, speed, startDelay]);

  return (
    <span ref={ref} className={className} aria-label={text}>
      <span aria-hidden="true">{shown}</span>
      <span aria-hidden="true" className={`inline-block w-[2px] h-[1.1em] align-[-0.15em] ml-0.5 bg-current ${done ? 'df-caret' : ''}`} />
    </span>
  );
}

/* ─────────────────────────────────────────────────────────
   Matchmaker demo: a brief types itself, three models follow.
   ───────────────────────────────────────────────────────── */
const DEMO_BRIEF = 'Family of 5 in Lahore, 40 km a day, automatic, under 45 lac.';
const DEMO_MODELS = [
  ['Honda City Aspire', 'Roomy, reliable, cheap to run in traffic.'],
  ['Toyota Yaris ATIV X', 'Strong resale and low maintenance.'],
  ['Suzuki Cultus AGS', 'Lowest running cost in the budget.'],
];

export function MatchDemo() {
  const typingMs = 400 + DEMO_BRIEF.length * 30;
  return (
    <div data-reveal="fade" className="flex flex-col gap-4">
      <div className="bg-white text-black p-5 sm:p-6 flex flex-col gap-2">
        <span className="text-[13px] font-bold text-neutral-600">Your brief</span>
        <TypeOnView text={DEMO_BRIEF} className="text-xl sm:text-2xl leading-snug font-medium min-h-[2.6em]" />
      </div>
      <ol className="flex flex-col">
        {DEMO_MODELS.map(([name, why], i) => (
          <li
            key={name}
            data-late
            style={{ '--d': `${(typingMs + 350 + i * 220) / 1000}s` }}
            className="grid grid-cols-[48px_minmax(0,1fr)] gap-4 items-baseline py-4 border-b border-white/20"
          >
            <span className="font-mono text-sm font-semibold text-df-red">0{i + 1}</span>
            <span className="flex flex-col gap-0.5">
              <strong className="text-xl">{name}</strong>
              <span className="text-[15px] text-zinc-400">{why}</span>
            </span>
          </li>
        ))}
      </ol>
      <span data-late style={{ '--d': `${(typingMs + 1100) / 1000}s` }} className="font-mono text-xs text-zinc-500">Example result. Real picks come with live ads for each model.</span>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   Chat demo: a question, a typing indicator, then an answer.
   ───────────────────────────────────────────────────────── */
export function ChatDemo() {
  return (
    <div data-reveal="fade" className="flex flex-col gap-4 p-5 sm:p-7 bg-white dark:bg-df-night border border-neutral-200 dark:border-zinc-800">
      <div className="flex items-center gap-3 pb-4 border-b border-neutral-200 dark:border-zinc-800">
        <span className="w-9 h-9 bg-df-red text-white flex items-center justify-center font-black">D</span>
        <strong className="text-[15px] uppercase tracking-wide">DriveFetch AI</strong>
        <span className="ml-auto font-mono text-xs df-muted">EXAMPLE</span>
      </div>
      <div data-late style={{ '--d': '.3s' }} className="self-end max-w-[85%] bg-black text-white dark:bg-zinc-50 dark:text-black px-4 py-3 text-[15px] leading-relaxed">
        Is a 2016 Aqua a good buy at 38 lac?
      </div>
      <div className="grid justify-items-start">
        <div data-blip style={{ '--d': '.8s' }} className="[grid-area:1/1] self-start flex items-center gap-1.5 px-4 py-3 bg-df-grey dark:bg-zinc-900 text-df-red">
          <span className="df-dot" /><span className="df-dot [animation-delay:.15s]" /><span className="df-dot [animation-delay:.3s]" />
        </div>
        <div data-late style={{ '--d': '1.9s' }} className="[grid-area:1/1] max-w-[92%] bg-df-grey dark:bg-zinc-900 px-4 py-3 text-[15px] leading-relaxed">
          It can be. Ask for the auction sheet and a hybrid battery health check first, then compare the price with similar live ads before you agree on a number.
        </div>
      </div>
    </div>
  );
}
