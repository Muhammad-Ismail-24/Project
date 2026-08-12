import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import CarResultCard from '../components/CarResultCard';
import { Loader2, BookmarkX } from 'lucide-react';
import useReveal from '../hooks/useReveal';

export default function SavedCarsPage() {
  const [savedCars, setSavedCars] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [savedListingIds, setSavedListingIds] = useState(new Set());
  const headingRef = useReveal();

  useEffect(() => {
    const fetchSavedCars = async () => {
      if (!document.cookie.includes('has_auth=1')) {
        setSavedCars([]);
        setSavedListingIds(new Set());
        setIsLoading(false);
        return;
      }
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
          if (response.status === 401) {
            document.cookie = "has_auth=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
          }
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
    <div className="relative w-full min-h-screen overflow-x-hidden font-sans">
      <div className="relative z-10 w-full pt-32 md:pt-40 px-4 md:px-6 max-w-7xl mx-auto pb-16 md:pb-32">
        <div ref={headingRef} className="reveal mb-10 md:mb-12 text-center md:text-left">
          <h1 className="font-display text-4xl md:text-5xl font-black tracking-tight text-text mb-3 md:mb-4">
            Saved Cars
          </h1>
          <p className="text-base font-medium text-text-dim">
            Review your bookmarked vehicles and top picks.
          </p>
        </div>

        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-16 md:py-20 space-y-4">
            <Loader2 className="w-7 h-7 text-text-faint animate-spin" />
            <p className="font-medium text-text-dim text-sm animate-pulse">
              Loading your saved cars...
            </p>
          </div>
        ) : savedCars.length === 0 ? (
          <div className="glass flex flex-col items-center justify-center py-16 md:py-32 px-4">
            <BookmarkX className="w-10 h-10 text-text-faint mb-4 md:mb-6" />
            <h3 className="font-display text-xl md:text-2xl font-black tracking-tight text-text mb-3 md:mb-4">
              No saved cars yet
            </h3>
            <p className="text-text-dim font-medium text-sm md:text-lg mb-6 md:mb-8 text-center max-w-md">
              You haven't saved any cars yet! Go browse our listings and hit the heart icon to save your favorites here.
            </p>
            <Link to="/" className="btn-primary text-sm">
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