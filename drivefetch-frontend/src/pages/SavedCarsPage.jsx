import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import CarResultCard from '../components/CarResultCard';
import Background3DShell from '../components/Background3DShell';
import { Loader2, BookmarkX } from 'lucide-react';

export default function SavedCarsPage() {
  const [savedCars, setSavedCars] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [savedListingIds, setSavedListingIds] = useState(new Set());

  useEffect(() => {
    const fetchSavedCars = async () => {
      try {
        const response = await fetch('/user/saved-listings', {
          method: 'GET',
          credentials: 'include',
        });
        if (response.ok) {
          const data = await response.json();
          setSavedCars(data);
          setSavedListingIds(new Set(data.map(car => car.id || car.listing_id)));
        } else {
          setSavedCars([]);
          setSavedListingIds(new Set());
        }
      } catch (error) {
        console.error("Failed to fetch saved cars:", error);
      } finally {
        setIsLoading(false);
      }
    };
    fetchSavedCars();
  }, []);

  const handleUnsave = (listingId) => {
    setSavedCars(prev => prev.filter(car => (car.id || car.listing_id) !== listingId));
    setSavedListingIds(prev => {
      const newSet = new Set(prev);
      newSet.delete(listingId);
      return newSet;
    });
  };

  return (
    <div className="relative w-full min-h-[calc(100vh-80px)] overflow-x-hidden font-sans text-black">
      {/* ── Background ── */}
      <div className="fixed inset-0 z-[-1] pointer-events-none overflow-hidden bg-[#b0b0b0]">
        <div className="absolute inset-0" style={{ backgroundImage: 'linear-gradient(to right,rgba(0,0,0,0.06) 1px,transparent 1px),linear-gradient(to bottom,rgba(0,0,0,0.06) 1px,transparent 1px)', backgroundSize: '72px 72px' }} />
        <div className="absolute w-[75vw] h-[75vw] max-w-[1100px] max-h-[1100px] bg-white rounded-full blur-[160px] opacity-35 top-[-10%] right-[-12%]" />
        <div className="absolute w-[40vw] h-[40vw] max-w-[600px] max-h-[600px] bg-white rounded-full blur-[120px] opacity-15 bottom-[5%] left-[-5%]" />
        <div className="absolute inset-0" style={{ background: 'radial-gradient(ellipse at 60% 40%, transparent 40%, rgba(0,0,0,0.18) 100%)' }} />
      </div>

      <Background3DShell />
      
      <div className="relative z-10 w-full pt-24 md:pt-32 px-4 md:px-6 max-w-7xl mx-auto pb-16 md:pb-32">
        <div className="mb-10 md:mb-12 text-center md:text-left">
          <h1 className="text-4xl md:text-5xl font-black tracking-tight text-black mb-3 md:mb-4">
            Saved Cars
          </h1>
          <p className="text-base font-medium text-black/55">
            Review your bookmarked vehicles and top picks.
          </p>
        </div>

        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-16 md:py-20 space-y-4">
            <Loader2 className="w-7 h-7 text-black/40 animate-spin" />
            <p className="text-black font-medium text-black/50 text-sm animate-pulse">
              Loading your saved cars...
            </p>
          </div>
        ) : savedCars.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 md:py-32 px-4 bg-white/55 backdrop-blur-md border border-white/60 rounded-2xl shadow-lg">
            <BookmarkX className="w-10 h-10 text-black/40 mb-4 md:mb-6" />
            <h3 className="text-xl md:text-2xl font-black tracking-tight text-black mb-3 md:mb-4">
              No saved cars yet
            </h3>
            <p className="text-black font-bold text-sm md:text-lg mb-6 md:mb-8 text-center max-w-md">
              You haven't saved any cars yet! Go browse our listings and hit the heart icon to save your favorites here.
            </p>
            <Link to="/" className="px-6 py-2.5 bg-black text-white text-sm font-medium rounded-xl hover:bg-neutral-800 transition-colors">
              Explore Cars
            </Link>
          </div>
        ) : (
          <div className="space-y-6">
            {savedCars.map((car) => (
              <CarResultCard 
                key={car.id || car.listing_id} 
                car={car} 
                savedListingIds={savedListingIds}
                onUnsave={() => handleUnsave(car.id || car.listing_id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}