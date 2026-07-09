import { searchCars } from '../utils/api';
import React, { useState } from 'react';
import Background3DShell from '../components/Background3DShell';
import SearchBar from '../components/SearchBar';
import CarResultCard from '../components/CarResultCard';
import { ShieldCheck, Database, Sparkles, AlertCircle, Loader2 } from 'lucide-react';

export default function Home() {
  const [isLoading, setIsLoading] = useState(false);
  const [results, setResults] = useState([]);
  const [bestPick, setBestPick] = useState(null);
  const [error, setError] = useState(null);

  const handleSearch = async (query) => {
    if (!query.trim()) return;

    // 1. Clear previous data immediately
    setResults([]);
    setBestPick(null);
    setError(null);

    // 2. Initiate loading state ONLY AFTER data is cleared
    setIsLoading(true);

    try {
      // Calls the FastAPI backend (which hits the cache or runs the scrapers)
      const data = await searchCars(query);
      setResults(data);
      if (data && data.length > 0) {
        setBestPick(data[0]);
      }
    } catch (err) {
      console.error("Search failed:", err);
      setError("Search failed. Please verify the backend is running and try again.");
    } finally {
      setIsLoading(false);
    }
  };

  // Filter out bestPick from the remaining results list
  const otherResults = results.filter(car => !bestPick || car.id !== bestPick.id);

  return (
    <div className="relative w-full overflow-x-hidden font-sans">
      
      <Background3DShell />

      <div className="relative z-10 w-full">
        
        {/* SECTION 1: Hero */}
        <div className="min-h-screen flex flex-col justify-center px-6 max-w-7xl mx-auto pt-40">
          <div className="max-w-md">
            <div className="inline-flex items-center px-4 py-1.5 rounded-full bg-black/5 border border-black/10 text-black text-xs font-bold tracking-widest uppercase mb-8 shadow-sm">
              GaariGuru AI Engine
            </div>
            <h1 className="text-6xl md:text-7xl font-black tracking-tighter text-black mb-6 leading-[0.9]">
              Find the right car.<br />Skip the wrong ones.
            </h1>
            <p className="text-xl font-medium text-neutral-600">
              We scan thousands of listings across Pakistan, flag risk, and grade liquidity — so you only see cars worth buying.
            </p>
          </div>
        </div>

        {/* SECTION 2: Market Platforms */}
        <div className="min-h-screen flex flex-col justify-center px-6 max-w-7xl mx-auto">
          <div className="max-w-md">
            <Database className="w-10 h-10 text-neutral-400 mb-6" />
            <h2 className="text-4xl font-black tracking-tight mb-4 text-black">Total Market Coverage</h2>
            <p className="text-neutral-600 font-medium text-lg leading-relaxed mb-8">
              We deploy stealth data harvesters across the top automotive marketplaces simultaneously to ensure you never miss a deal.
            </p>
            
            <div className="flex flex-wrap gap-3">
              {['PakWheels', 'OLX Pakistan', 'Drive.pk', 'Gari.pk'].map(platform => (
                <span key={platform} className="px-5 py-2.5 bg-white/40 backdrop-blur-xl border border-white/60 rounded-full text-sm font-black tracking-wide shadow-sm text-black hover:bg-white/70 transition-colors cursor-default">
                  {platform}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* SECTION 3: AI Info Panel */}
        <div className="min-h-screen flex flex-col justify-center px-6 max-w-7xl mx-auto">
          <div className="max-w-xl ml-auto bg-white/50 backdrop-blur-xl p-10 rounded-[2rem] border border-white/50 shadow-2xl">
            <ShieldCheck className="w-12 h-12 text-black mb-6" />
            <h2 className="text-4xl font-black tracking-tight mb-4 text-black">Powered by AI</h2>
            <p className="text-neutral-600 font-medium text-lg leading-relaxed">
              Our system doesn't just show you prices. It reads descriptions, analyzes the market, and flags risky keywords like "showered for fresh look" or "duplicate file" before you make a costly mistake.
            </p>
          </div>
        </div>

        {/* SECTION 4: Search Area */}
        <div id="search-section" className="min-h-screen px-6 pt-32 pb-32 bg-neutral-50 relative z-20 shadow-[0_-20px_50px_rgba(0,0,0,0.05)] border-t border-neutral-200">
          <div className="max-w-4xl mx-auto">
            <div className="text-center mb-12">
              <h2 className="text-5xl font-black tracking-tight mb-4 text-black">Start Your Search</h2>
              <p className="text-neutral-500 font-medium text-xl">Let the engine analyze the market for you.</p>
            </div>
            
            <SearchBar onSearch={handleSearch} isLoading={isLoading} />

            <div className="mt-24 space-y-12">
              
              {/* 1. Loading Indicator */}
              {isLoading && (
                <div className="flex flex-col items-center justify-center py-20 space-y-4">
                  <Loader2 className="w-12 h-12 text-black animate-spin" />
                  <p className="text-neutral-500 font-bold text-lg animate-pulse">GaariGuru is fetching & appraising listings...</p>
                </div>
              )}

              {/* 2. Error Display */}
              {error && (
                <div className="flex items-center space-x-3 bg-red-50 border border-red-200 text-red-700 p-6 rounded-2xl shadow-sm">
                  <AlertCircle className="w-6 h-6 shrink-0" />
                  <p className="font-medium">{error}</p>
                </div>
              )}

              {/* 3. Results - Best Pick */}
              {bestPick && !isLoading && (
                <div className="space-y-6">
                  <div className="inline-flex items-center space-x-2 bg-gradient-to-r from-amber-500 to-yellow-500 text-white font-bold text-sm uppercase px-4 py-1.5 rounded-full shadow-md tracking-wider">
                    <Sparkles className="w-4 h-4" />
                    <span>Best AI Match</span>
                  </div>
                  <div className="ring-4 ring-amber-400/50 rounded-3xl overflow-hidden shadow-2xl">
                    <CarResultCard car={bestPick} isHighlighted={true} />
                  </div>
                </div>
              )}

              {/* 4. Other Results */}
              {otherResults.length > 0 && !isLoading && (
                <div className="space-y-6 pt-6 border-t border-neutral-200">
                  <h3 className="text-2xl font-black tracking-tight text-neutral-800">Alternative Matches</h3>
                  <div className="space-y-6">
                    {otherResults.map((car) => (
                      <CarResultCard key={car.id} car={car} />
                    ))}
                  </div>
                </div>
              )}

              {/* 5. Zero Results State */}
              {results.length === 0 && !isLoading && !error && (
                <div className="text-center py-20 bg-white/40 backdrop-blur-xl border border-neutral-200 rounded-3xl">
                  <p className="text-neutral-500 font-semibold text-lg">No search query executed yet. Try typing something above!</p>
                </div>
              )}

            </div>
          </div>
        </div>

      </div>
    </div>
  );
}