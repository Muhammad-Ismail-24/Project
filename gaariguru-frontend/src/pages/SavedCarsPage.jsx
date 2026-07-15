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
      <div className="fixed inset-0 z-[-1] pointer-events-none overflow-hidden flex items-center justify-center bg-[#a3a3a3]">
        <div className="absolute inset-0 opacity-[0.05]" style={{ backgroundImage: 'radial-gradient(#000000 1px, transparent 1px)', backgroundSize: '32px 32px' }} />
        <div className="absolute w-[80vw] h-[80vw] max-w-[1000px] max-h-[1000px] bg-white rounded-full blur-[140px] top-[0%] right-[-10%] opacity-40" />
      </div>

      <Background3DShell />
      
      <div className="relative z-10 w-full pt-24 md:pt-32 px-4 md:px-6 max-w-7xl mx-auto pb-16 md:pb-32">
        <div className="mb-10 md:mb-12 text-center md:text-left">
          <h1 className="text-4xl md:text-5xl font-black tracking-tight text-black mb-3 md:mb-4">
            Saved Cars
          </h1>
          <p className="text-lg md:text-xl font-bold text-black">
            Review your bookmarked vehicles and top picks.
          </p>
        </div>

        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-16 md:py-20 space-y-4">
            <Loader2 className="w-10 h-10 md:w-12 md:h-12 text-black animate-spin" />
            <p className="text-black font-bold text-base md:text-lg animate-pulse">
              Loading your saved cars...
            </p>
          </div>
        ) : savedCars.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 md:py-32 px-4 bg-white/60 backdrop-blur-md border border-black/15 rounded-2xl md:rounded-3xl shadow-2xl">
            <BookmarkX className="w-12 h-12 md:w-16 md:h-16 text-black mb-4 md:mb-6" />
            <h3 className="text-xl md:text-2xl font-black tracking-tight text-black mb-3 md:mb-4">
              No saved cars yet
            </h3>
            <p className="text-black font-bold text-sm md:text-lg mb-6 md:mb-8 text-center max-w-md">
              You haven't saved any cars yet! Go browse our listings and hit the heart icon to save your favorites here.
            </p>
            <Link to="/" className="px-6 py-3 md:px-8 md:py-4 bg-black text-white font-bold rounded-full hover:bg-neutral-800 transition-colors shadow-lg text-sm md:text-base">
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