import { searchCars } from '../utils/api';
import React, { useState, useEffect, useRef } from 'react';
import { Helmet } from 'react-helmet-async';
import SearchBar from '../components/SearchBar';
import CarResultCard from '../components/CarResultCard';
import { ShieldCheck, Database, Sparkles, AlertCircle, Loader2, Car } from 'lucide-react';
import { useScrollProgress } from '../three/useScrollProgress';
import useReveal from '../hooks/useReveal';

// Defined at module scope so they are stable references and never appear in
// useEffect dependency arrays (avoids the infinite-re-render trap where
// in-component string literals look like new values on every render).
const HERO_LINE_1 = "Find the right car.";
const HERO_LINE_2 = "Skip the wrong ones.";

const HeroTypewriter = () => {
  const [displayed1, setDisplayed1] = useState('');
  const [displayed2, setDisplayed2] = useState('');
  const [phase, setPhase] = useState(0);

  useEffect(() => {
    if (phase === 0) { const t = setTimeout(() => setPhase(1), 400); return () => clearTimeout(t); }
    if (phase === 1) {
      if (displayed1.length < HERO_LINE_1.length) {
        const t = setTimeout(() => setDisplayed1(HERO_LINE_1.slice(0, displayed1.length + 1)), 50);
        return () => clearTimeout(t);
      } else { const t = setTimeout(() => setPhase(3), 400); return () => clearTimeout(t); }
    }
    if (phase === 3) {
      if (displayed2.length < HERO_LINE_2.length) {
        const t = setTimeout(() => setDisplayed2(HERO_LINE_2.slice(0, displayed2.length + 1)), 50);
        return () => clearTimeout(t);
      } else { setPhase(4); }
    }
  }, [phase, displayed1, displayed2]); // stable: module-scope constants excluded

  return (
    <h1 className="font-display text-5xl sm:text-6xl md:text-7xl font-black tracking-tighter text-text mb-6 leading-[0.95] md:leading-[0.9] min-h-[100px] sm:min-h-[120px] md:min-h-[145px]">
      {displayed1}
      {phase === 1 && <span className="animate-pulse ml-0.5">|</span>}
      <br />
      <span>{displayed2}</span>
      {phase >= 3 && <span className="animate-pulse ml-0.5">|</span>}
    </h1>
  );
};

export default function Home() {
  const [isLoading, setIsLoading] = useState(false);
  const [results, setResults] = useState([]);
  const [bestPick, setBestPick] = useState(null);
  const [error, setError] = useState(null);
  const [savedListingIds, setSavedListingIds] = useState(new Set());
  const [hasSearched, setHasSearched] = useState(false);
  const [lastQuery, setLastQuery] = useState('');

  const journeyRef = useRef(null);

  const heroRevealRef = useReveal();
  const coverageRevealRef = useReveal();
  const aiPanelRevealRef = useReveal();
  const searchRevealRef = useReveal();

  // Scroll → progressRef bridge (Blueprint §6). No React state: the hook writes
  // scroll progress into a module ref that the canvas reads in useFrame.
  // Disabled under reduced motion, which pins progress at 0 (landing pose held).
  const prefersReducedMotion =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  useScrollProgress(journeyRef, { enabled: !prefersReducedMotion });

  useEffect(() => {
    const fetchSavedListings = async () => {
      if (!document.cookie.includes('has_auth=1')) return;
      try {
        const response = await fetch('/user/saved-listings', { method: 'GET', credentials: 'include' });
        if (response.ok) {
          const data = await response.json();
          setSavedListingIds(new Set(data.map(item => item.listing_id)));
        } else if (response.status === 401) {
          document.cookie = "has_auth=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
        }
      } catch (error) { console.error('Failed to fetch saved listings:', error); }
    };
    fetchSavedListings();
  }, []);

  const handleSearch = async (query) => {
    if (!query.trim()) return;
    setResults([]); setBestPick(null); setError(null);
    setIsLoading(true); setHasSearched(true); setLastQuery(query);
    try {
      const data = await searchCars(query);
      setResults(data);
      if (data && data.length > 0) setBestPick(data[0]);
    } catch (err) {
      setError('Search failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const otherResults = results.filter(car => !bestPick || car.id !== bestPick.id);

  return (
    <main className="relative w-full overflow-x-hidden font-sans">
      <Helmet>
        <title>DriveFetch — Find the Right Used Car in Pakistan, Powered by AI</title>
        <meta name="description" content="Find the perfect used car in Pakistan with DriveFetch. Our AI-powered search scours multiple sources to find your ideal match." />
        <link rel="canonical" href="https://carfinderproject.vercel.app/" />
      </Helmet>

      <div className="relative z-10 w-full">

        {/* ── Scroll-drive journey: hero → coverage → AI panel. GSAP ScrollTrigger
             tracks scroll progress across this wrapper's height and drives the
             persistent 3D car (Sec 6.4); it exits the frame by the end of it.
             pointer-events-none so drags pass through to the canvas behind it,
             letting OrbitControls receive them during the free-orbit landing
             state — this section has no clickable content of its own. ── */}
        <div ref={journeyRef} className="pointer-events-none">

        {/* ── SECTION 1: Hero (scroll 0) — car is orbit-controllable here ── */}
        <div className="min-h-[80vh] lg:min-h-screen flex flex-col justify-center px-6 max-w-7xl mx-auto pt-32 lg:pt-40 pb-16 lg:pb-0">
          <div ref={heroRevealRef} className="reveal max-w-lg">

            <div className="glass-thin inline-flex items-center gap-2 px-3.5 py-1.5 text-text text-[10px] font-semibold tracking-[0.15em] uppercase mb-8">
              <span className="w-1.5 h-1.5 rounded-full bg-accent inline-block" />
              Drive Fetch AI Engine
            </div>

            <HeroTypewriter />

            <p className="text-base md:text-lg font-medium text-text-dim leading-relaxed max-w-sm">
              We scan thousands of listings across Pakistan, flag risk, and grade
              liquidity — so you only see cars worth buying.
            </p>
          </div>
        </div>

        {/* ── SECTION 2: Total Market Coverage ── */}
        <div className="min-h-[70vh] lg:min-h-screen flex flex-col justify-center px-6 max-w-7xl mx-auto py-16 lg:py-0">
          <div ref={coverageRevealRef} className="reveal max-w-md">
            <Database className="w-7 h-7 text-text-dim mb-5" strokeWidth={1.5} />
            <h2 className="font-display text-3xl md:text-4xl font-black tracking-tight mb-3 text-text">
              Total Market Coverage
            </h2>
            <p className="text-base font-medium text-text-dim leading-relaxed mb-8">
              We deploy stealth data harvesters across the top automotive marketplaces
              simultaneously to ensure you never miss a deal.
            </p>
            <div className="flex flex-wrap gap-2">
              {['PakWheels', 'OLX Pakistan', 'Drive.pk', 'Gari.pk'].map((platform) => (
                <span
                  key={platform}
                  className="glass-thin px-4 py-1.5 text-xs font-medium tracking-wide text-text-dim"
                >
                  {platform}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* ── SECTION 3: Powered by AI — offset so the driving car stays visible ── */}
        <div className="min-h-[70vh] lg:min-h-screen flex flex-col justify-center px-6 max-w-7xl mx-auto py-16 lg:py-0">
          <div ref={aiPanelRevealRef} className="reveal glass max-w-xl ml-auto p-8 md:p-10">
            <ShieldCheck className="w-7 h-7 text-text-dim mb-5" strokeWidth={1.5} />
            <h2 className="font-display text-3xl md:text-4xl font-black tracking-tight mb-3 text-text">
              Powered by AI
            </h2>
            <p className="text-base font-medium text-text-dim leading-relaxed">
              Our system doesn't just show you prices. It reads descriptions, analyzes
              the market, and flags risky keywords like "showered for fresh look" or
              "duplicate file" before you make a costly mistake.
            </p>
          </div>
        </div>

        </div>

        {/* ── SECTION 4: Start Your Search ── */}
        <div
          id="search-section"
          className="min-h-[80vh] lg:min-h-screen px-6 pt-24 lg:pt-32 pb-[30vh] lg:pb-[40vh] relative z-20"
        >
          <div ref={searchRevealRef} className="reveal max-w-4xl mx-auto">
            <div className="text-center mb-10 md:mb-12">
              <h2 className="font-display text-4xl md:text-5xl font-black tracking-tight mb-2 text-text">
                Start Your Search
              </h2>
              <p className="text-base font-medium text-text-dim">
                Let the engine analyze the market for you.
              </p>
            </div>

            <SearchBar onSearch={handleSearch} isLoading={isLoading} />

            {/* ── Category Badges ── */}
            <div className="mt-6 flex flex-wrap justify-center gap-3">
              <button
                onClick={() => handleSearch("7 Seater MPV under 60 lacs")}
                disabled={isLoading}
                className="glass-thin glass-hover flex items-center gap-2 px-4 py-2 text-sm font-semibold text-text-dim transition-all disabled:opacity-50"
              >
                <Car className="w-4 h-4" />
                MPVs (7-Seater)
              </button>
              <button
                onClick={() => handleSearch("Mini SUV Crossover under 70 lacs")}
                disabled={isLoading}
                className="glass-thin glass-hover flex items-center gap-2 px-4 py-2 text-sm font-semibold text-text-dim transition-all disabled:opacity-50"
              >
                <Car className="w-4 h-4" />
                Mini SUVs
              </button>
            </div>

            <div className="mt-16 md:mt-24 space-y-8 md:space-y-12">

              {isLoading && (
                <div className="flex flex-col items-center justify-center py-16 space-y-3">
                  <Loader2 className="w-8 h-8 text-text-dim animate-spin" />
                  <p className="text-sm font-medium text-text-dim animate-pulse">
                    Drive Fetch is fetching &amp; appraising listings…
                  </p>
                </div>
              )}

              {error && (
                <div className="glass-thin flex items-center gap-3 text-text-dim p-5">
                  <AlertCircle className="w-5 h-5 shrink-0 text-danger" strokeWidth={1.5} />
                  <p className="text-sm font-medium">{error}</p>
                </div>
              )}

              {bestPick && !isLoading && (
                <div className="space-y-4">
                  <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-accent text-white text-[10px] font-semibold tracking-[0.12em] uppercase">
                    <Sparkles className="w-3 h-3" strokeWidth={1.5} />
                    Best AI Match
                  </div>
                  <CarResultCard car={bestPick} isHighlighted={true} savedListingIds={savedListingIds} userQuery={lastQuery} />
                </div>
              )}

              {otherResults.length > 0 && !isLoading && (
                <div className="space-y-5 pt-6" style={{ borderTop: '1px solid var(--df-glass-border)' }}>
                  <h3 className="text-lg font-semibold tracking-tight text-text-dim">
                    Alternative Matches
                  </h3>
                  <div className="space-y-4">
                    {otherResults.map(car => (
                      <CarResultCard key={car.id} car={car} savedListingIds={savedListingIds} userQuery={lastQuery} />
                    ))}
                  </div>
                </div>
              )}

              {results.length === 0 && !isLoading && !error && hasSearched && (
                <div className="glass-thin text-center py-14">
                  <p className="text-sm font-medium text-text-dim px-4">
                    No cars matched your criteria. Try broadening your search or budget.
                  </p>
                </div>
              )}

              {results.length === 0 && !isLoading && !error && !hasSearched && (
                <div className="glass-thin text-center py-14">
                  <p className="text-sm font-medium text-text-dim px-4">
                    Type a query above to get started.
                  </p>
                </div>
              )}

            </div>
          </div>
        </div>

      </div>
    </main>
  );
}
