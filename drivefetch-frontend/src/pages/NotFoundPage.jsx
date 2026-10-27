import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import SEO from '../components/SEO';
import SplitText from '../components/motion/SplitText';

const EXITS = [
  { to: '/', name: 'Discover', d: 'Search 7 sites at once', rot: -90 },
  { to: '/recommend', name: 'Matchmaker', d: 'Tell us your needs, get 3 models', rot: -45 },
  { to: '/chat', name: 'Chat', d: 'Ask anything about buying', rot: 0 },
  { to: '/calculators', name: 'Calculators', d: 'Token tax, transfer, fuel', rot: 45 },
  { to: '/saved', name: 'Saved cars', d: 'Your garage', rot: 90 },
];

export default function NotFoundPage() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [q, setQ] = useState('');

  const onSearch = (e) => {
    e.preventDefault();
    const v = q.trim();
    navigate(v ? `/?q=${encodeURIComponent(v)}` : '/');
  };

  return (
    <div className="w-full flex flex-wrap min-h-[calc(100vh-72px)]">
      {/* noindex: a soft-404 that Google indexes competes with real pages. */}
      <SEO title="404 · Wrong turn" description="This DriveFetch page could not be found. Head back to the car search to continue." path="/404" noindex />

      <section className="flex-[1_1_560px] min-w-0 bg-df-red text-white px-5 sm:px-10 py-12 flex flex-col justify-between gap-10">
        <div className="flex flex-col gap-5">
          <span className="font-mono text-sm font-semibold break-all">ERROR 404 · {pathname}</span>
          <h1 className="df-display text-[length:clamp(72px,9.5vw,172px)] leading-[0.8]"><SplitText text="Wrong" className="block" /><SplitText text="turn." className="block text-black" start={1} /></h1>
          <p data-reveal style={{ '--rd': '250ms' }} className="max-w-[460px] text-[19px] leading-relaxed">This road doesn’t go anywhere. Search for a car instead, or take one of the exits.</p>
          <form onSubmit={onSearch} role="search" data-reveal style={{ '--rd': '400ms' }} className="flex bg-white max-w-[560px]">
            <label htmlFor="nf-q" className="sr-only">Search used cars</label>
            <input id="nf-q" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. Civic Lahore" className="flex-1 min-w-0 h-14 px-4 text-black text-lg outline-none placeholder:text-neutral-500" />
            <button type="submit" className="px-6 bg-black text-white text-sm font-extrabold tracking-[0.06em] hover:bg-white hover:text-black hover:outline hover:outline-2 hover:outline-black">SEARCH</button>
          </form>
        </div>
        <span className="text-sm">Followed a broken link? <Link to="/about#contact" className="font-extrabold underline underline-offset-2">Tell us</Link></span>
      </section>

      <nav aria-label="Exits" data-stagger className="flex-[1_1_480px] min-w-0 flex flex-col justify-center py-10">
        {EXITS.map((x, i) => (
          <Link
            key={x.to}
            to={x.to}
            className="group grid grid-cols-[72px_minmax(0,1fr)_auto] gap-4 sm:gap-5 items-center px-5 sm:px-10 py-5 border-t border-neutral-200 dark:border-zinc-800 last:border-b hover:bg-df-red hover:text-white transition-colors"
          >
            <span aria-hidden="true" className="w-14 h-14 border-[3px] border-current flex items-center justify-center">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" style={{ transform: `rotate(${x.rot}deg)` }}>
                <path d="M12 19V5M6 11l6-6 6 6" />
              </svg>
            </span>
            <span className="flex flex-col gap-0.5">
              <span className="df-display text-[36px] leading-[0.9]">{x.name}</span>
              <span className="text-sm opacity-80">{x.d}</span>
            </span>
            <span className="font-mono text-[13px] font-semibold">EXIT {i + 1}</span>
          </Link>
        ))}
      </nav>
    </div>
  );
}
