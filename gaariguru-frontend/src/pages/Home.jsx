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

const HeroTypewriter = () => {
  const line1 = "Find the right car.";
  const line2 = "Skip the wrong ones.";
  
  const [displayed1, setDisplayed1] = useState('');
  const [displayed2, setDisplayed2] = useState('');
  const [phase, setPhase] = useState(0); 

  useEffect(() => {
    if (phase === 0) {
      const t = setTimeout(() => setPhase(1), 400);
      return () => clearTimeout(t);
    }
    if (phase === 1) {
      if (displayed1.length < line1.length) {
        const t = setTimeout(() => setDisplayed1(line1.slice(0, displayed1.length + 1)), 50);
        return () => clearTimeout(t);
      } else {
        const t = setTimeout(() => setPhase(3), 400); 
        return () => clearTimeout(t);
      }
    }
    if (phase === 3) {
      if (displayed2.length < line2.length) {
        const t = setTimeout(() => setDisplayed2(line2.slice(0, displayed2.length + 1)), 50);
        return () => clearTimeout(t);
      } else {
        setPhase(4);
      }
    }
  }, [phase, displayed1, displayed2, line1, line2]);

  return (
    <h1 className="text-6xl md:text-7xl font-black tracking-tighter text-black mb-6 leading-[0.9] min-h-[130px] md:min-h-[145px]">
      {displayed1}
      {phase === 1 && <span className="animate-pulse text-black ml-1">|</span>}
      <br />
      <span className="text-black">{displayed2}</span>
      {phase >= 3 && <span className="animate-pulse text-black ml-1">|</span>}
    </h1>
  );
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
        // PROXY FIX: Using relative path
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
    setResults([]); setBestPick(null); setError(null); setIsLoading(true);
    try {
      const data = await searchCars(query);
      setResults(data);
      if (data && data.length > 0) setBestPick(data[0]);
    } catch (err) { setError('Search failed.'); } finally { setIsLoading(false); }
  };

  const otherResults = results.filter(car => !bestPick || car.id !== bestPick.id);

  return (
    <div className="relative w-full overflow-x-hidden font-sans text-black">

      <div className="fixed inset-0 z-[-1] pointer-events-none overflow-hidden flex items-center justify-center bg-[#a3a3a3]">
        <div className="absolute inset-0 opacity-[0.05]" style={{ backgroundImage: 'radial-gradient(#000000 1px, transparent 1px)', backgroundSize: '32px 32px' }} />
        <div className="absolute w-[80vw] h-[80vw] max-w-[1000px] max-h-[1000px] bg-white rounded-full blur-[140px] top-[0%] right-[-10%] opacity-40" />
      </div>

      <Background3DShell />

      <div className="relative z-10 w-full">

        <div className="min-h-screen flex flex-col justify-center px-6 max-w-7xl mx-auto pt-40">
          <motion.div className="max-w-md" variants={heroContainerVariants} initial="hidden" animate="visible">
            <motion.div variants={heroItemVariants}>
              <div className="inline-flex items-center px-5 py-2 rounded-full bg-black text-white text-xs font-bold tracking-widest uppercase mb-8 shadow-md">
                GaariGuru AI Engine
              </div>
            </motion.div>

            <motion.div variants={heroItemVariants}>
              <HeroTypewriter />
            </motion.div>

            <motion.p variants={heroItemVariants} className="text-xl font-bold text-black">
              We scan thousands of listings across Pakistan, flag risk, and grade
              liquidity — so you only see cars worth buying.
            </motion.p>
          </motion.div>
        </div>

        <div className="min-h-screen flex flex-col justify-center px-6 max-w-7xl mx-auto">
          <div className="max-w-md">
            <Database className="w-10 h-10 text-black mb-6" />
            <h2 className="text-4xl font-black tracking-tight mb-4 text-black">
              Total Market Coverage
            </h2>
            <p className="text-lg font-bold text-black leading-relaxed mb-8">
              We deploy stealth data harvesters across the top automotive marketplaces
              simultaneously to ensure you never miss a deal.
            </p>
            <div className="flex flex-wrap gap-3">
              {['PakWheels', 'OLX Pakistan', 'Drive.pk', 'Gari.pk'].map(platform => (
                <span key={platform} className="px-5 py-2.5 bg-[#a3a3a3] border border-black/15 shadow-md rounded-full text-sm font-bold tracking-wide text-black cursor-default">
                  {platform}
                </span>
              ))}
            </div>
          </div>
        </div>

        <div className="min-h-screen flex flex-col justify-center px-6 max-w-7xl mx-auto">
          <div className="max-w-xl ml-auto bg-[#a3a3a3] p-10 rounded-[2rem] border border-black/15 shadow-2xl">
            <ShieldCheck className="w-12 h-12 text-black mb-6" />
            <h2 className="text-4xl font-black tracking-tight mb-4 text-black">
              Powered by AI
            </h2>
            <p className="text-lg font-bold text-black leading-relaxed">
              Our system doesn't just show you prices. It reads descriptions, analyzes
              the market, and flags risky keywords like "showered for fresh look" or
              "duplicate file" before you make a costly mistake.
            </p>
          </div>
        </div>

        <div id="search-section" className="min-h-screen px-6 pt-32 pb-[40vh] relative z-20">
          <div className="max-w-4xl mx-auto">
            <div className="text-center mb-12">
              <h2 className="text-5xl font-black tracking-tight mb-4 text-black">
                Start Your Search
              </h2>
              <p className="text-xl font-bold text-black">
                Let the engine analyze the market for you.
              </p>
            </div>

            <SearchBar onSearch={handleSearch} isLoading={isLoading} />

            <div className="mt-24 space-y-12">
              {isLoading && (
                <div className="flex flex-col items-center justify-center py-20 space-y-4">
                  <Loader2 className="w-12 h-12 text-black animate-spin" />
                  <p className="text-lg font-bold text-black animate-pulse">
                    GaariGuru is fetching &amp; appraising listings...
                  </p>
                </div>
              )}

              {error && (
                <div className="flex items-center space-x-3 bg-white/60 backdrop-blur-md border border-black/15 shadow-md text-black p-6 rounded-2xl">
                  <AlertCircle className="w-6 h-6 shrink-0" />
                  <p className="font-bold">{error}</p>
                </div>
              )}

              {bestPick && !isLoading && (
                <div className="space-y-6">
                  <div className="inline-flex items-center space-x-2 bg-black text-white font-bold text-sm uppercase px-4 py-1.5 rounded-full tracking-wider shadow-md">
                    <Sparkles className="w-4 h-4" />
                    <span>Best AI Match</span>
                  </div>
                  <div className="rounded-3xl overflow-hidden shadow-2xl border border-black/15 bg-[#a3a3a3]">
                    <CarResultCard
                      car={bestPick}
                      isHighlighted={true}
                      savedListingIds={savedListingIds}
                    />
                  </div>
                </div>
              )}

              {otherResults.length > 0 && !isLoading && (
                <div className="space-y-6 pt-6 border-t border-black/10">
                  <h3 className="text-2xl font-black tracking-tight text-black">
                    Alternative Matches
                  </h3>
                  <div className="space-y-6">
                    {otherResults.map(car => (
                      <div key={car.id} className="rounded-3xl overflow-hidden border border-black/15 shadow-xl bg-[#a3a3a3]">
                        <CarResultCard car={car} savedListingIds={savedListingIds} />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {results.length === 0 && !isLoading && !error && (
                <div className="text-center py-20 bg-white/60 backdrop-blur-md rounded-3xl border border-black/15 shadow-xl">
                  <p className="text-lg font-bold text-black">
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