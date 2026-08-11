import React, { createContext, useContext, useRef } from 'react';

// Shared mutable state bridging the DOM-side GSAP ScrollTrigger (set up by
// whichever page owns the scroll journey, e.g. Home.jsx) and the persistent
// R3F canvas (mounted once in MainLayout). Plain mutable fields on a stable
// object — never React state — so neither side re-renders the other's tree.
const ScrollDriveContext = createContext(null);

export function ScrollDriveProvider({ children }) {
  const state = useRef({
    progress: 0,      // 0..1 drive progress along the road curve
    orbitActive: true, // true while the car is in the free-orbit landing state
  }).current;

  return (
    <ScrollDriveContext.Provider value={state}>
      {children}
    </ScrollDriveContext.Provider>
  );
}

export function useScrollDrive() {
  const ctx = useContext(ScrollDriveContext);
  if (!ctx) {
    throw new Error('useScrollDrive must be used within a ScrollDriveProvider');
  }
  return ctx;
}
