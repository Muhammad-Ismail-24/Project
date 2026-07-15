import { searchCars } from '../utils/api';
import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import Background3DShell from '../components/Background3DShell';
import SearchBar from '../components/SearchBar';
import CarResultCard from '../components/CarResultCard';
import { ShieldCheck, Database, Sparkles, AlertCircle, Loader2 } from 'lucide-react';

const heroContainerVariants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.12, delayChildren: 0.15 },
  },
};

const heroItemVariants = {
  hidden: { opacity: 0, y: 28 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { type: 'spring', stiffness: 80, damping: 18, mass: 1 },
  },
};

export default function Home() {
  const [isLoading, setIsLoading] = useState(false);
  const [results, setResults] = useState([]);
  const [bestPick, setBestPick] = useState(null);
  const [error, setError] = useState(null);
  const [savedListingIds, setSavedListingIds] = useState(new Set());

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
    <div className="relative w-full overflow-x-hidden font-sans bg-gray-200 text-black">

      {/* ── Fixed 3D canvas ── */}
      <Background3DShell />

      {/* ── Metallic Titanium Background ────────────────────────────── */}
      <div className="fixed inset-0 z-[1] pointer-events-none overflow-hidden flex items-center justify-center">
        {/* Metallic Silver Base Gradient */}
        <div className="absolute inset-0 bg-gradient-to-br from-gray-100 via-gray-300 to-gray-400" />
        
        {/* Subtle Dark Grid for scale */}
        <div 
          className="absolute inset-0 opacity-[0.05]" 
          style={{ 
            backgroundImage: 'radial-gradient(#000000 1px, transparent 1px)', 
            backgroundSize: '32px 32px' 
          }} 
        />
        
        {/* Stark White Spotlight BEHIND the car to make the black model pop */}
        <div className="absolute w-[80vw] h-[80vw] max-w-[1000px] max-h-[1000px] bg-white rounded-full blur-[120px] top-[0%] right-[-10%]" />
        
        {/* Deep Shadow gradient at bottom to ground it into the search section */}
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-gray-300/80" />
      </div>

      <div className="relative z-10 w-full">

        {/* ════════════════════════════════════════════════════════════════════
            SECTION 1 — Hero
        ════════════════════════════════════════════════════════════════════ */}
        <div className="min-h-screen flex flex-col justify-center px-6 max-w-7xl mx-auto pt-40">
          <motion.div
            className="max-w-md"
            variants={heroContainerVariants}
            initial="hidden"
            animate="visible"
          >
            {/* The "Black Touch" Badge */}
            <motion.div variants={heroItemVariants}>
              <div className="inline-flex items-center px-5 py-2 rounded-full bg-black text-white text-xs font-bold tracking-widest uppercase mb-8 shadow-xl">
                GaariGuru AI Engine
              </div>
            </motion.div>

            <motion.h1
              variants={heroItemVariants}
              className="text-6xl md:text-7xl font-black tracking-tighter text-black mb-6 leading-[0.9]"
            >
              Find the right car.<br />Skip the wrong ones.
            </motion.h1>

            <motion.p
              variants={heroItemVariants}
              className="text-xl font-medium text-gray-700"
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
            <Database className="w-10 h-10 text-gray-600 mb-6" />
            <h2 className="text-4xl font-black tracking-tight mb-4 text-black">
              Total Market Coverage
            </h2>
            <p className="text-gray-700 font-medium text-lg leading-relaxed mb-8">
              We deploy stealth data harvesters across the top automotive marketplaces
              simultaneously to ensure you never miss a deal.
            </p>
            <div className="flex flex-wrap gap-3">
              {/* The "White Touch" Pills */}
              {['PakWheels', 'OLX Pakistan', 'Drive.pk', 'Gari.pk'].map(platform => (
                <span
                  key={platform}
                  className="px-5 py-2.5 bg-white/80 backdrop-blur-xl border border-white rounded-full text-sm font-bold tracking-wide shadow-sm text-black hover:shadow-md transition-all cursor-default"
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
          {/* The "White Touch" Glass Panel */}
          <div className="max-w-xl ml-auto bg-white/60 backdrop-blur-2xl p-10 rounded-[2rem] border border-white shadow-2xl">
            <ShieldCheck className="w-12 h-12 text-black mb-6" />
            <h2 className="text-4xl font-black tracking-tight mb-4 text-black">
              Powered by AI
            </h2>
            <p className="text-gray-700 font-medium text-lg leading-relaxed">
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
          className="min-h-screen px-6 pt-32 pb-32 bg-gray-100 relative z-20 border-t border-gray-300"
        >
          <div className="max-w-4xl mx-auto">
            <div className="text-center mb-12">
              <h2 className="text-5xl font-black tracking-tight mb-4 text-black">
                Start Your Search
              </h2>
              <p className="text-gray-500 font-medium text-xl">
                Let the engine analyze the market for you.
              </p>
            </div>

            <SearchBar onSearch={handleSearch} isLoading={isLoading} />

            <div className="mt-24 space-y-12">
              {isLoading && (
                <div className="flex flex-col items-center justify-center py-20 space-y-4">
                  <Loader2 className="w-12 h-12 text-black animate-spin" />
                  <p className="text-gray-500 font-bold text-lg animate-pulse">
                    GaariGuru is fetching &amp; appraising listings...
                  </p>
                </div>
              )}

              {error && (
                <div className="flex items-center space-x-3 bg-red-50 border border-red-200 text-red-700 p-6 rounded-2xl shadow-sm">
                  <AlertCircle className="w-6 h-6 shrink-0" />
                  <p className="font-medium">{error}</p>
                </div>
              )}

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

              {otherResults.length > 0 && !isLoading && (
                <div className="space-y-6 pt-6 border-t border-gray-300">
                  <h3 className="text-2xl font-black tracking-tight text-black">
                    Alternative Matches
                  </h3>
                  <div className="space-y-6">
                    {otherResults.map(car => (
                      <CarResultCard key={car.id} car={car} savedListingIds={savedListingIds} />
                    ))}
                  </div>
                </div>
              )}

              {results.length === 0 && !isLoading && !error && (
                <div className="text-center py-20 bg-white border border-gray-200 rounded-3xl shadow-sm">
                  <p className="text-gray-500 font-semibold text-lg">
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