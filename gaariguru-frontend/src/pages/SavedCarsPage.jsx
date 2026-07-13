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
        const response = await fetch('https://carfinder-project-backend.onrender.com/user/saved-listings', {
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
    // Smoothly remove the unsaved car from the UI
    setSavedCars(prev => prev.filter(car => (car.id || car.listing_id) !== listingId));
    setSavedListingIds(prev => {
      const newSet = new Set(prev);
      newSet.delete(listingId);
      return newSet;
    });
  };

  return (
    <div className="relative w-full min-h-[calc(100vh-80px)] overflow-x-hidden font-sans">
      <Background3DShell />
      
      <div className="relative z-10 w-full pt-16 px-6 max-w-7xl mx-auto pb-32">
        <div className="mb-12 text-center md:text-left">
          <h1 className="text-4xl md:text-5xl font-black tracking-tight text-black mb-4">Saved Cars</h1>
          <p className="text-xl font-medium text-neutral-600">Review your bookmarked vehicles and top picks.</p>
        </div>

        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-20 space-y-4">
            <Loader2 className="w-12 h-12 text-black animate-spin" />
            <p className="text-neutral-500 font-bold text-lg animate-pulse">Loading your saved cars...</p>
          </div>
        ) : savedCars.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-32 bg-white/50 backdrop-blur-xl border border-white/60 rounded-3xl shadow-xl">
            <BookmarkX className="w-16 h-16 text-neutral-300 mb-6" />
            <h3 className="text-2xl font-black tracking-tight text-black mb-4">No saved cars yet</h3>
            <p className="text-neutral-500 font-medium text-lg mb-8 text-center max-w-md">
              You haven't saved any cars yet! Go browse our listings and hit the heart icon to save your favorites here.
            </p>
            <Link to="/" className="px-8 py-4 bg-black text-white font-bold rounded-full hover:scale-105 transition-transform shadow-lg">
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
