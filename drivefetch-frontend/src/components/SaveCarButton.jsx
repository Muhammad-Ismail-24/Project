import React, { useState, useEffect } from 'react';
import { useUI } from '../contexts/UIContext';
import { Spinner } from './ui/Loaders';

export default function SaveCarButton({ listingId, platform, title, savedListingIds = new Set(), onUnsave, className = '' }) {
  const [isSaved, setIsSaved] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const { openSignIn } = useUI();

  useEffect(() => {
    if (savedListingIds.has(listingId)) {
      setIsSaved(true);
    }
  }, [listingId, savedListingIds]);

  const handleSaveToggle = async (e) => {
    e.preventDefault();
    e.stopPropagation();

    if (isLoading) return;
    setIsLoading(true);

    try {
      if (isSaved) {
        const encodedId = encodeURIComponent(listingId);
        const response = await fetch(`/user/saved-listings/${encodedId}`, {
          method: 'DELETE',
          credentials: 'include',
        });

        if (response.status === 401) {
          openSignIn('save');
          return;
        }

        if (response.ok) {
          setIsSaved(false);
          if (onUnsave) onUnsave();
        }
      } else {
        const response = await fetch('/user/saved-listings', {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ listing_id: listingId, platform, title }),
        });

        if (response.status === 401) {
          openSignIn('save');
          return;
        }

        if (response.ok || response.status === 201) {
          setIsSaved(true);
        }
      }
    } catch (error) {
      if (import.meta.env.DEV) { console.error("Full error details:", error); }
      console.error("Failed to toggle save state:", error instanceof Error ? error.message : "Unknown error");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <button
      type="button"
      onClick={handleSaveToggle}
      disabled={isLoading}
      aria-pressed={isSaved}
      aria-label={isSaved ? 'Remove from saved' : 'Save this car'}
      title={isSaved ? 'Saved' : 'Save'}
      className={`w-11 h-11 flex items-center justify-center transition-colors disabled:opacity-60 ${
        isSaved ? 'bg-df-red text-white hover:bg-black' : 'bg-white text-black hover:bg-black hover:text-white'
      } ${className}`}
    >
      {isLoading ? (
        <Spinner className="w-4 h-4" light={isSaved} />
      ) : (
        <svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18" fill={isSaved ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinejoin="round">
          <path d="M6 3h12v18l-6-4-6 4z" />
        </svg>
      )}
    </button>
  );
}
