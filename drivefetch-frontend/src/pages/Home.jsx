import { searchCars } from '../utils/api';
import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import Background3DShell from '../components/Background3DShell';
import SearchBar from '../components/SearchBar';
import CarResultCard from '../components/CarResultCard';
import { ShieldCheck, Database, Sparkles, AlertCircle, Loader2 } from 'lucide-react';

const heroContainerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.12, delayChildren: 0.15 } },
};

const heroItemVariants = {
  hidden: { opacity: 0, y: 24 },
  visible: { opacity: 1, y: 0, transition: { type: 'spring', stiffness: 70, damping: 20 } },
};

const HeroTypewriter = () => {
  const line1 = "Find the right car.";
  const line2 = "Skip the wrong ones.";
  const [displayed1, setDisplayed1] = useState('');
  const [displayed2, setDisplayed2] = useState('');
  const [phase, setPhase] = useState(0);

  useEffect(() => {
    if (phase === 0) { const t = setTimeout(() => setPhase(1), 400); return () => clearTimeout(t); }
    if (phase === 1) {
      if (displayed1.length < line1.length) {
        const t = setTimeout(() => setDisplayed1(line1.slice(0, displayed1.length + 1)), 50);
        return () => clearTimeout(t);
      } else { const t = setTimeout(() => setPhase(3), 400); return () => clearTimeout(t); }
    }
    if (phase === 3) {
      if (displayed2.length < line2.length) {
        const t = setTimeout(() => setDisplayed2(line2.slice(0, displayed2.length + 1)), 50);
        return () => clearTimeout(t);
      } else { setPhase(4); }
    }
  }, [phase, displayed1, displayed2, line1, line2]);

  return (
    <h1 className="text-5xl sm:text-6xl md:text-7xl font-black tracking-tighter text-black mb-6 leading-[0.95] md:leading-[0.9] min-h-[100px] sm:min-h-[120px] md:min-h-[145px]">
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

  useEffect(() => {
    const fetchSavedListings = async () => {
      try {
        const response = await fetch('/user/saved-listings', { method: 'GET', credentials: 'include' });
        if (response.ok) {
          const data = await response.json();
          setSavedListingIds(new Set(data.map(item => item.listing_id)));
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
    <div className="relative w-full overflow-x-hidden font-sans text-black">

      {/* ── Background: metallic grey studio, white key light, subtle grid ── */}
      <div className="fixed inset-0 z-[-1] pointer-events-none overflow-hidden bg-[#b0b0b0]">
        {/* Fine technical grid */}
        <div
          className="absolute inset-0"
          style={{
            backgroundImage:
              'linear-gradient(to right,rgba(0,0,0,0.06) 1px,transparent 1px),' +
              'linear-gradient(to bottom,rgba(0,0,0,0.06) 1px,transparent 1px)',
            backgroundSize: '72px 72px',
          }}
        />
        {/* Top-right key light — makes the car's black paint reflective */}
        <div className="absolute w-[75vw] h-[75vw] max-w-[1100px] max-h-[1100px] bg-white rounded-full blur-[160px] opacity-35 top-[-10%] right-[-12%]" />
        {/* Bottom-left subtle fill */}
        <div className="absolute w-[40vw] h-[40vw] max-w-[600px] max-h-[600px] bg-white rounded-full blur-[120px] opacity-15 bottom-[5%] left-[-5%]" />
        {/* Vignette */}
        <div
          className="absolute inset-0"
          style={{ background: 'radial-gradient(ellipse at 60% 40%, transparent 40%, rgba(0,0,0,0.18) 100%)' }}
        />
      </div>

      <Background3DShell />

      <div className="relative z-10 w-full">

        {/* ── SECTION 1: Hero ── */}
        <div className="min-h-[80vh] lg:min-h-screen flex flex-col justify-center px-6 max-w-7xl mx-auto pt-32 lg:pt-40 pb-16 lg:pb-0">
          <motion.div className="max-w-lg" variants={heroContainerVariants} initial="hidden" animate="visible">

            {/* Eyebrow — lighter weight, refined */}
            <motion.div variants={heroItemVariants}>
              <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-black/80 text-white text-[10px] font-semibold tracking-[0.15em] uppercase mb-8">
                <span className="w-1.5 h-1.5 rounded-full bg-white/70 inline-block" />
                GaariGuru AI Engine
              </div>
            </motion.div>

            {/* Headline — font-black reserved for display only */}
            <motion.div variants={heroItemVariants}>
              <HeroTypewriter />
            </motion.div>

            {/* Body copy — medium weight, not bold */}
            <motion.p variants={heroItemVariants} className="text-base md:text-lg font-medium text-black/70 leading-relaxed max-w-sm">
              We scan thousands of listings across Pakistan, flag risk, and grade
              liquidity — so you only see cars worth buying.
            </motion.p>
          </motion.div>
        </div>

        {/* ── SECTION 2: Market Coverage ── */}
        <div className="min-h-[70vh] lg:min-h-screen flex flex-col justify-center px-6 max-w-7xl mx-auto py-16 lg:py-0">
          <div className="max-w-md">
            {/* Icon — thinner, more refined */}
            <Database className="w-7 h-7 text-black/50 mb-5" strokeWidth={1.5} />
            <h2 className="text-3xl md:text-4xl font-black tracking-tight mb-3 text-black">
              Total Market Coverage
            </h2>
            <p className="text-base font-medium text-black/60 leading-relaxed mb-8">
              We deploy stealth data harvesters across the top automotive marketplaces
              simultaneously to ensure you never miss a deal.
            </p>
            {/* Platform tags — minimal, no heavy border, just a quiet surface */}
            <div className="flex flex-wrap gap-2">
              {['PakWheels', 'OLX Pakistan', 'Drive.pk', 'Gari.pk'].map(platform => (
                <span
                  key={platform}
                  className="px-4 py-1.5 bg-black/8 rounded-full text-xs font-medium tracking-wide text-black/80 border border-black/10"
                >
                  {platform}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* ── SECTION 3: AI Panel ── */}
        <div className="min-h-[70vh] lg:min-h-screen flex flex-col justify-center px-6 max-w-7xl mx-auto py-16 lg:py-0">
          {/* Glass card — white surface on grey background creates clean lift */}
          <div className="max-w-xl ml-auto bg-white/55 backdrop-blur-xl p-8 md:p-10 rounded-2xl border border-white/70 shadow-xl">
            <ShieldCheck className="w-7 h-7 text-black/40 mb-5" strokeWidth={1.5} />
            <h2 className="text-3xl md:text-4xl font-black tracking-tight mb-3 text-black">
              Powered by AI
            </h2>
            <p className="text-base font-medium text-black/60 leading-relaxed">
              Our system doesn't just show you prices. It reads descriptions, analyzes
              the market, and flags risky keywords like "showered for fresh look" or
              "duplicate file" before you make a costly mistake.
            </p>
          </div>
        </div>

        {/* ── SECTION 4: Search ── */}
        <div
          id="search-section"
          className="min-h-[80vh] lg:min-h-screen px-6 pt-24 lg:pt-32 pb-[30vh] lg:pb-[40vh] relative z-20"
        >
          <div className="max-w-4xl mx-auto">
            <div className="text-center mb-10 md:mb-12">
              <h2 className="text-4xl md:text-5xl font-black tracking-tight mb-2 text-black">
                Start Your Search
              </h2>
              <p className="text-base font-medium text-black/55">
                Let the engine analyze the market for you.
              </p>
            </div>

            <SearchBar onSearch={handleSearch} isLoading={isLoading} />

            <div className="mt-16 md:mt-24 space-y-8 md:space-y-12">

              {isLoading && (
                <div className="flex flex-col items-center justify-center py-16 space-y-3">
                  <Loader2 className="w-8 h-8 text-black/50 animate-spin" />
                  <p className="text-sm font-medium text-black/50 animate-pulse">
                    GaariGuru is fetching &amp; appraising listings…
                  </p>
                </div>
              )}

              {error && (
                <div className="flex items-center gap-3 bg-white/50 backdrop-blur-md border border-black/10 text-black/70 p-5 rounded-2xl">
                  <AlertCircle className="w-5 h-5 shrink-0 text-black/40" strokeWidth={1.5} />
                  <p className="text-sm font-medium">{error}</p>
                </div>
              )}

              {bestPick && !isLoading && (
                <div className="space-y-4">
                  {/* Best pick label — refined */}
                  <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-black text-white text-[10px] font-semibold tracking-[0.12em] uppercase">
                    <Sparkles className="w-3 h-3" strokeWidth={1.5} />
                    Best AI Match
                  </div>
                  {/* Card — clean white surface, no double-border */}
                  <div className="rounded-2xl overflow-hidden shadow-lg border border-black/10 bg-white/70 backdrop-blur-sm">
                    <CarResultCard car={bestPick} isHighlighted={true} savedListingIds={savedListingIds} userQuery={lastQuery} />
                  </div>
                </div>
              )}

              {otherResults.length > 0 && !isLoading && (
                <div className="space-y-5 pt-6 border-t border-black/10">
                  <h3 className="text-lg font-semibold tracking-tight text-black/70">
                    Alternative Matches
                  </h3>
                  <div className="space-y-4">
                    {otherResults.map(car => (
                      <div key={car.id} className="rounded-2xl overflow-hidden border border-black/10 shadow-md bg-white/60 backdrop-blur-sm">
                        <CarResultCard car={car} savedListingIds={savedListingIds} userQuery={lastQuery} />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {results.length === 0 && !isLoading && !error && hasSearched && (
                <div className="text-center py-14 bg-white/40 backdrop-blur-md rounded-2xl border border-black/8">
                  <p className="text-sm font-medium text-black/50 px-4">
                    No cars matched your criteria. Try broadening your search or budget.
                  </p>
                </div>
              )}

              {results.length === 0 && !isLoading && !error && !hasSearched && (
                <div className="text-center py-14 bg-white/40 backdrop-blur-md rounded-2xl border border-black/8">
                  <p className="text-sm font-medium text-black/50 px-4">
                    Type a query above to get started.
                  </p>
                </div>
              )}

            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
