import { searchCars } from '../utils/api';
import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import Background3DShell from '../components/Background3DShell';
import SearchBar from '../components/SearchBar';
import CarResultCard from '../components/CarResultCard';
import { ShieldCheck, Database, Sparkles, AlertCircle, Loader2 } from 'lucide-react';

// ─── Framer Motion variants ────────────────────────────────────────────────────
const heroContainerVariants = {
  hidden: {},
  visible: {
    transition: {
      staggerChildren: 0.12,
      delayChildren:   0.15,
    },
  },
};

const heroItemVariants = {
  hidden:  { opacity: 0, y: 28 },
  visible: {
    opacity: 1,
    y:       0,
    transition: {
      type:        'spring',
      stiffness:   80,
      damping:     18,
      mass:        1,
    },
  },
};

export default function Home() {
  const [isLoading, setIsLoading] = useState(false);
  const [results, setResults] = useState([]);
  const [bestPick, setBestPick] = useState(null);
  const [error, setError] = useState(null);
  const [savedListingIds, setSavedListingIds] = useState(new Set());

  // ── Fetch saved listings on mount ─────────────────────────────
  useEffect(() => {
    const fetchSavedListings = async () => {
      try {
        const response = await fetch(
          'https://carfinder-project-backend.onrender.com/user/saved-listings',
          { method: 'GET', credentials: 'include' }
        );
        if (response.ok) {
          const data = await response.json();
          setSavedListingIds(new Set(data.map(item => item.listing_id)));
        } else if (response.status === 401) {
          setSavedListingIds(new Set());
        }
      } catch (error) {
        console.error('Failed to fetch saved listings:', error);
        setSavedListingIds(new Set());
      }
    };
    fetchSavedListings();
  }, []);

  // ── Search handler ────────────────────────────────────────────
  const handleSearch = async (query) => {
    if (!query.trim()) return;
    setResults([]);
    setBestPick(null);
    setError(null);
    setIsLoading(true);
    try {
      const data = await searchCars(query);
      setResults(data);
      if (data && data.length > 0) setBestPick(data[0]);
    } catch (err) {
      console.error('Search failed:', err);
      setError('Search failed. Please verify the backend is running and try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const otherResults = results.filter(car => !bestPick || car.id !== bestPick.id);

  return (
    <div className="relative w-full overflow-x-hidden font-sans bg-zinc-950 text-white">

      {/* ── Fixed 3D canvas ── */}
      <Background3DShell />

      {/* ── Dark Automotive Studio Lighting ──────────────────────────────
          Transparent enough to let the z-0 car show through!
      ──────────────────────────────────────────────────────────────────────── */}
      <div className="fixed inset-0 z-[1] pointer-events-none overflow-hidden flex items-center justify-center">
        {/* Subtle Dark Isometric Grid */}
        <div 
          className="absolute inset-0 opacity-[0.1]" 
          style={{ 
            backgroundImage: 'radial-gradient(#ffffff 1px, transparent 1px)', 
            backgroundSize: '32px 32px' 
          }} 
        />
        {/* Stark Silver/White Spotlight BEHIND the car */}
        <div className="absolute w-[70vw] h-[70vw] max-w-[900px] max-h-[900px] bg-white/10 rounded-full blur-[140px] top-[5%] right-[-10%]" />
        
        {/* Smooth fade to deep zinc at the bottom for readability */}
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-zinc-950/40 to-zinc-950" />
      </div>

      <div className="relative z-10 w-full">

        {/* ════════════════════════════════════════════════════════════════════
            SECTION 1 — Hero (Dark Mode Text)
        ════════════════════════════════════════════════════════════════════ */}
        <div className="min-h-screen flex flex-col justify-center px-6 max-w-7xl mx-auto pt-40">
          <motion.div
            className="max-w-md"
            variants={heroContainerVariants}
            initial="hidden"
            animate="visible"
          >
            {/* Badge */}
            <motion.div variants={heroItemVariants}>
              <div className="inline-flex items-center px-4 py-1.5 rounded-full bg-white/10 border border-white/20 text-white text-xs font-bold tracking-widest uppercase mb-8 shadow-sm backdrop-blur-md">
                GaariGuru AI Engine
              </div>
            </motion.div>

            {/* Headline */}
            <motion.h1
              variants={heroItemVariants}
              className="text-6xl md:text-7xl font-black tracking-tighter text-white mb-6 leading-[0.9]"
            >
              Find the right car.<br />Skip the wrong ones.
            </motion.h1>

            {/* Subheading */}
            <motion.p
              variants={heroItemVariants}
              className="text-xl font-medium text-zinc-400"
            >
              We scan thousands of listings across Pakistan, flag risk, and grade
              liquidity — so you only see cars worth buying.
            </motion.p>
          </motion.div>
        </div>

        {/* ════════════════════════════════════════════════════════════════════
            SECTION 2 — Market Platforms
        ════════════════════════════════════════════════════════════════════ */}
        <div className="min-h-screen flex flex-col justify-center px-6 max-w-7xl mx-auto">
          <div className="max-w-md">
            <Database className="w-10 h-10 text-zinc-500 mb-6" />
            <h2 className="text-4xl font-black tracking-tight mb-4 text-white">
              Total Market Coverage
            </h2>
            <p className="text-zinc-400 font-medium text-lg leading-relaxed mb-8">
              We deploy stealth data harvesters across the top automotive marketplaces
              simultaneously to ensure you never miss a deal.
            </p>
            <div className="flex flex-wrap gap-3">
              {['PakWheels', 'OLX Pakistan', 'Drive.pk', 'Gari.pk'].map(platform => (
                <span
                  key={platform}
                  className="px-5 py-2.5 bg-zinc-900/80 backdrop-blur-xl border border-zinc-700/50 rounded-full text-sm font-bold tracking-wide shadow-sm text-zinc-300 hover:text-white hover:bg-zinc-800 transition-colors cursor-default"
                >
                  {platform}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* ════════════════════════════════════════════════════════════════════
            SECTION 3 — AI Info Panel
        ════════════════════════════════════════════════════════════════════ */}
        <div className="min-h-screen flex flex-col justify-center px-6 max-w-7xl mx-auto">
          <div className="max-w-xl ml-auto bg-zinc-900/60 backdrop-blur-xl p-10 rounded-[2rem] border border-zinc-800 shadow-2xl">
            <ShieldCheck className="w-12 h-12 text-white mb-6" />
            <h2 className="text-4xl font-black tracking-tight mb-4 text-white">
              Powered by AI
            </h2>
            <p className="text-zinc-400 font-medium text-lg leading-relaxed">
              Our system doesn't just show you prices. It reads descriptions, analyzes
              the market, and flags risky keywords like "showered for fresh look" or
              "duplicate file" before you make a costly mistake.
            </p>
          </div>
        </div>

        {/* ════════════════════════════════════════════════════════════════════
            SECTION 4 — Search
        ════════════════════════════════════════════════════════════════════ */}
        <div
          id="search-section"
          className="min-h-screen px-6 pt-32 pb-32 bg-zinc-950 relative z-20 border-t border-zinc-900"
        >
          <div className="max-w-4xl mx-auto">
            <div className="text-center mb-12">
              <h2 className="text-5xl font-black tracking-tight mb-4 text-white">
                Start Your Search
              </h2>
              <p className="text-zinc-400 font-medium text-xl">
                Let the engine analyze the market for you.
              </p>
            </div>

            <SearchBar onSearch={handleSearch} isLoading={isLoading} />

            <div className="mt-24 space-y-12">

              {/* Loading */}
              {isLoading && (
                <div className="flex flex-col items-center justify-center py-20 space-y-4">
                  <Loader2 className="w-12 h-12 text-white animate-spin" />
                  <p className="text-zinc-500 font-bold text-lg animate-pulse">
                    GaariGuru is fetching &amp; appraising listings...
                  </p>
                </div>
              )}

              {/* Error */}
              {error && (
                <div className="flex items-center space-x-3 bg-red-950 border border-red-900 text-red-400 p-6 rounded-2xl shadow-sm">
                  <AlertCircle className="w-6 h-6 shrink-0" />
                  <p className="font-medium">{error}</p>
                </div>
              )}

              {/* Best Pick */}
              {bestPick && !isLoading && (
                <div className="space-y-6">
                  <div className="inline-flex items-center space-x-2 bg-gradient-to-r from-zinc-700 to-zinc-600 text-white font-bold text-sm uppercase px-4 py-1.5 rounded-full shadow-md tracking-wider">
                    <Sparkles className="w-4 h-4 text-amber-400" />
                    <span>Best AI Match</span>
                  </div>
                  <div className="ring-1 ring-zinc-800 rounded-3xl overflow-hidden shadow-2xl">
                    <CarResultCard
                      car={bestPick}
                      isHighlighted={true}
                      savedListingIds={savedListingIds}
                    />
                  </div>
                </div>
              )}

              {/* Other Results */}
              {otherResults.length > 0 && !isLoading && (
                <div className="space-y-6 pt-6 border-t border-zinc-900">
                  <h3 className="text-2xl font-black tracking-tight text-white">
                    Alternative Matches
                  </h3>
                  <div className="space-y-6">
                    {otherResults.map(car => (
                      <CarResultCard key={car.id} car={car} savedListingIds={savedListingIds} />
                    ))}
                  </div>
                </div>
              )}

              {/* Zero Results */}
              {results.length === 0 && !isLoading && !error && (
                <div className="text-center py-20 bg-zinc-900/40 backdrop-blur-xl border border-zinc-800/50 rounded-3xl">
                  <p className="text-zinc-500 font-semibold text-lg">
                    No search query executed yet. Try typing something above!
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