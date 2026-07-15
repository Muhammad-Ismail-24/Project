import { searchCars } from '../utils/api';
import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import Background3DShell from '../components/Background3DShell';
import SearchBar from '../components/SearchBar';
import CarResultCard from '../components/CarResultCard';
import { ShieldCheck, Database, Sparkles, AlertCircle, Loader2 } from 'lucide-react';

// ─── Framer Motion variants ────────────────────────────────────────────────────
// Used in the Hero section only. All other sections are untouched.

// Container: staggers children with a short delay after mount
const heroContainerVariants = {
  hidden: {},
  visible: {
    transition: {
      staggerChildren: 0.12,
      delayChildren:   0.15,
    },
  },
};

// Each child rises up and fades in with a spring
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

  // ── Fetch saved listings on mount (unchanged) ─────────────────────────────
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

  // ── Search handler (unchanged) ────────────────────────────────────────────
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
    <div className="relative w-full overflow-x-hidden font-sans">

      {/* ── Fixed 3D canvas ── */}
      <Background3DShell />

      {/* ── Radial spotlight behind the 3D car ──────────────────────────────
          Sits above the Canvas (z-1) but below page content (z-10).
          pointer-events-none so it never blocks clicks.
          Two layered blobs: one warm-white glow centered right where the car
          sits on load, one cooler accent below-left for depth.
      ──────────────────────────────────────────────────────────────────────── */}
      <div className="fixed inset-0 z-[1] pointer-events-none overflow-hidden">
        {/* Primary glow — soft white spotlight behind the car */}
        <div
          className="absolute rounded-full blur-[140px]"
          style={{
            width:      '70vw',
            height:     '70vw',
            maxWidth:   '900px',
            maxHeight:  '900px',
            top:        '5%',
            right:      '-10%',
            background: 'radial-gradient(circle, rgba(255,255,255,0.55) 0%, rgba(245,245,245,0.18) 55%, transparent 80%)',
          }}
        />
        {/* Accent glow — very subtle cool undertone for dimension */}
        <div
          className="absolute rounded-full blur-[180px]"
          style={{
            width:      '50vw',
            height:     '50vw',
            maxWidth:   '700px',
            maxHeight:  '700px',
            bottom:     '10%',
            right:      '5%',
            background: 'radial-gradient(circle, rgba(220,225,235,0.30) 0%, transparent 70%)',
          }}
        />
      </div>

      <div className="relative z-10 w-full">

        {/* ════════════════════════════════════════════════════════════════════
            SECTION 1 — Hero
            Text block animates in with staggered spring on mount.
            The 3D car reveal is handled inside Background3DShell.jsx.
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
              <div className="inline-flex items-center px-4 py-1.5 rounded-full bg-black/5 border border-black/10 text-black text-xs font-bold tracking-widest uppercase mb-8 shadow-sm">
                GaariGuru AI Engine
              </div>
            </motion.div>

            {/* Headline */}
            <motion.h1
              variants={heroItemVariants}
              className="text-6xl md:text-7xl font-black tracking-tighter text-black mb-6 leading-[0.9]"
            >
              Find the right car.<br />Skip the wrong ones.
            </motion.h1>

            {/* Subheading */}
            <motion.p
              variants={heroItemVariants}
              className="text-xl font-medium text-neutral-600"
            >
              We scan thousands of listings across Pakistan, flag risk, and grade
              liquidity — so you only see cars worth buying.
            </motion.p>
          </motion.div>
        </div>

        {/* ════════════════════════════════════════════════════════════════════
            SECTION 2 — Market Platforms (unchanged)
        ════════════════════════════════════════════════════════════════════ */}
        <div className="min-h-screen flex flex-col justify-center px-6 max-w-7xl mx-auto">
          <div className="max-w-md">
            <Database className="w-10 h-10 text-neutral-400 mb-6" />
            <h2 className="text-4xl font-black tracking-tight mb-4 text-black">
              Total Market Coverage
            </h2>
            <p className="text-neutral-600 font-medium text-lg leading-relaxed mb-8">
              We deploy stealth data harvesters across the top automotive marketplaces
              simultaneously to ensure you never miss a deal.
            </p>
            <div className="flex flex-wrap gap-3">
              {['PakWheels', 'OLX Pakistan', 'Drive.pk', 'Gari.pk'].map(platform => (
                <span
                  key={platform}
                  className="px-5 py-2.5 bg-white/40 backdrop-blur-xl border border-white/60 rounded-full text-sm font-black tracking-wide shadow-sm text-black hover:bg-white/70 transition-colors cursor-default"
                >
                  {platform}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* ════════════════════════════════════════════════════════════════════
            SECTION 3 — AI Info Panel (unchanged)
        ════════════════════════════════════════════════════════════════════ */}
        <div className="min-h-screen flex flex-col justify-center px-6 max-w-7xl mx-auto">
          <div className="max-w-xl ml-auto bg-white/50 backdrop-blur-xl p-10 rounded-[2rem] border border-white/50 shadow-2xl">
            <ShieldCheck className="w-12 h-12 text-black mb-6" />
            <h2 className="text-4xl font-black tracking-tight mb-4 text-black">
              Powered by AI
            </h2>
            <p className="text-neutral-600 font-medium text-lg leading-relaxed">
              Our system doesn't just show you prices. It reads descriptions, analyzes
              the market, and flags risky keywords like "showered for fresh look" or
              "duplicate file" before you make a costly mistake.
            </p>
          </div>
        </div>

        {/* ════════════════════════════════════════════════════════════════════
            SECTION 4 — Search (unchanged)
        ════════════════════════════════════════════════════════════════════ */}
        <div
          id="search-section"
          className="min-h-screen px-6 pt-32 pb-32 bg-neutral-50 relative z-20 shadow-[0_-20px_50px_rgba(0,0,0,0.05)] border-t border-neutral-200"
        >
          <div className="max-w-4xl mx-auto">
            <div className="text-center mb-12">
              <h2 className="text-5xl font-black tracking-tight mb-4 text-black">
                Start Your Search
              </h2>
              <p className="text-neutral-500 font-medium text-xl">
                Let the engine analyze the market for you.
              </p>
            </div>

            <SearchBar onSearch={handleSearch} isLoading={isLoading} />

            <div className="mt-24 space-y-12">

              {/* Loading */}
              {isLoading && (
                <div className="flex flex-col items-center justify-center py-20 space-y-4">
                  <Loader2 className="w-12 h-12 text-black animate-spin" />
                  <p className="text-neutral-500 font-bold text-lg animate-pulse">
                    GaariGuru is fetching &amp; appraising listings...
                  </p>
                </div>
              )}

              {/* Error */}
              {error && (
                <div className="flex items-center space-x-3 bg-red-50 border border-red-200 text-red-700 p-6 rounded-2xl shadow-sm">
                  <AlertCircle className="w-6 h-6 shrink-0" />
                  <p className="font-medium">{error}</p>
                </div>
              )}

              {/* Best Pick */}
              {bestPick && !isLoading && (
                <div className="space-y-6">
                  <div className="inline-flex items-center space-x-2 bg-gradient-to-r from-amber-500 to-yellow-500 text-white font-bold text-sm uppercase px-4 py-1.5 rounded-full shadow-md tracking-wider">
                    <Sparkles className="w-4 h-4" />
                    <span>Best AI Match</span>
                  </div>
                  <div className="ring-4 ring-amber-400/50 rounded-3xl overflow-hidden shadow-2xl">
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
                <div className="space-y-6 pt-6 border-t border-neutral-200">
                  <h3 className="text-2xl font-black tracking-tight text-neutral-800">
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
                <div className="text-center py-20 bg-white/40 backdrop-blur-xl border border-neutral-200 rounded-3xl">
                  <p className="text-neutral-500 font-semibold text-lg">
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
