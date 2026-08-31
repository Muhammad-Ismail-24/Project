import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, BookmarkX } from 'lucide-react';
import CarResultCard from '../components/CarResultCard';
import SEO from '../components/SEO';

export default function SavedCarsPage() {
  const [savedCars, setSavedCars] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [savedListingIds, setSavedListingIds] = useState(new Set());

  useEffect(() => {
    const controller = new AbortController();
    
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
          signal: controller.signal,
        });
        if (response.ok) {
          const data = await response.json();
          if (!controller.signal.aborted) {
            setSavedCars(data);
            setSavedListingIds(new Set(data.map(car => car.id || car.listing_id)));
          }
        } else {
          if (response.status === 401) {
            document.cookie = "has_auth=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
          }
          if (!controller.signal.aborted) {
            setSavedCars([]);
            setSavedListingIds(new Set());
          }
        }
      } catch (error) {
        if (error.name === 'AbortError') return;
        if (import.meta.env.DEV) { console.error("Full error details:", error); }
        console.error("Failed to fetch saved cars:", error instanceof Error ? error.message : "Unknown error");
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false);
        }
      }
    };
    
    fetchSavedCars();
    
    return () => {
      controller.abort();
    };
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
    <>
      {/* noindex: per-user content behind auth. Indexing it would surface an
          empty shell to crawlers and is why it is absent from sitemap.xml. */}
      <SEO
        title="Saved Vehicles"
        description="Your saved vehicles on DriveFetch."
        path="/saved"
        noindex
      />

      {/* ── Background Pattern ── */}
      <div className="fixed inset-0 pointer-events-none -z-10 bg-df-white bg-[linear-gradient(to_right,#e5e7eb_1px,transparent_1px),linear-gradient(to_bottom,#e5e7eb_1px,transparent_1px)] bg-[size:40px_40px]" />

      <div className="relative z-10 w-full pt-12 md:pt-20 px-4 md:px-6 max-w-5xl mx-auto pb-16 md:pb-32 min-h-[calc(100vh-140px)]">
        <div className="mb-10 md:mb-12">
          <p className="font-mono text-[10px] md:text-xs font-bold tracking-[0.14em] text-df-black/35 dark:text-zinc-50/35 mb-2 uppercase">
            [ USER DATA // BOOKMARKS ]
          </p>
          <h1 className="text-display-lg text-df-black dark:text-zinc-50 mb-4">
            Saved Vehicles
          </h1>
        </div>

        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-20 border-2 border-df-black bg-df-white dark:bg-black dark:border-white shadow-brutal">
            <Loader2 className="w-8 h-8 text-df-black dark:text-zinc-50 animate-spin mb-4" />
            <p className="font-mono text-xs font-bold tracking-[0.1em] text-df-black dark:text-zinc-50 uppercase">
              [ LOADING DATA_STREAM ]
            </p>
          </div>
        ) : savedCars.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 md:py-32 px-6 bg-df-white dark:bg-black dark:border-white border-2 border-df-black shadow-brutal-lg">
            <div className="w-16 h-16 bg-df-black flex items-center justify-center border-brutal shadow-brutal-sm mb-8">
              <BookmarkX className="w-8 h-8 text-df-white" strokeWidth={2} />
            </div>
            <h3 className="font-display text-4xl md:text-5xl text-df-black dark:text-zinc-50 tracking-wide mb-6 uppercase text-center">
              [ NO SAVED VEHICLES ]
            </h3>
            <Link 
              to="/" 
              className="px-6 py-4 bg-[#E5202E] text-df-white border-2 border-df-black font-mono text-xs md:text-sm font-bold tracking-[0.1em] uppercase shadow-[4px_4px_0px_0px_#000000] hover:translate-y-[2px] hover:translate-x-[2px] hover:shadow-[2px_2px_0px_0px_#000000] transition-all"
            >
              RETURN TO HOME PAGE
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
    </>
  );
}