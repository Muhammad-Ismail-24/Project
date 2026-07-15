import React, { useState, useEffect } from 'react';

export default function SaveCarButton({ listingId, platform, title, savedListingIds = new Set(), onUnsave }) {
  const [isSaved, setIsSaved] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

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
        // PROXY FIX: Unsave using relative path
        const encodedId = encodeURIComponent(listingId);
        const response = await fetch(`/user/saved-listings/${encodedId}`, {
          method: 'DELETE',
          credentials: 'include',
        });

        if (response.status === 401) {
          alert("Sign in to save cars");
          setIsLoading(false);
          return;
        }

        if (response.ok) {
          setIsSaved(false);
          if (onUnsave) {
            onUnsave();
          }
        }
      } else {
        // PROXY FIX: Save using relative path
        const response = await fetch('/user/saved-listings', {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            listing_id: listingId,
            platform,
            title,
          }),
        });

        if (response.status === 401) {
          alert("Sign in to save cars");
          setIsLoading(false);
          return;
        }

        if (response.ok || response.status === 201) {
          setIsSaved(true);
        }
      }
    } catch (error) {
      console.error("Failed to toggle save state:", error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <button
      onClick={handleSaveToggle}
      disabled={isLoading}
      aria-label={isSaved ? "Remove from saved" : "Save this car"}
      className="p-2.5 rounded-full bg-white/60 backdrop-blur-md border border-black/15 shadow-md hover:bg-white hover:scale-105 transition-all disabled:opacity-50"
    >
      {isLoading ? (
        <svg className="animate-spin h-5 w-5 text-black" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
      ) : (
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          width="20"
          height="20"
          className="transition-colors duration-200"
        >
          <path
            d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"
            fill={isSaved ? "black" : "none"}
            stroke="black"
            strokeWidth="2"
          />
        </svg>
      )}
    </button>
  );
}