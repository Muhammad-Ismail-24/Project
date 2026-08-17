import React from 'react';
import { Link } from 'react-router-dom';
import SEO from '../components/SEO';

export default function NotFoundPage() {
  return (
    <>
      {/* noindex: a soft-404 that Google indexes competes with real pages and
          dilutes the branded "DriveFetch" result set. */}
      <SEO
        title="404 // Route Not Found"
        description="This DriveFetch page could not be found. Head back to the car search to continue."
        path="/404"
        noindex
      />

      {/* ── Background Grid Pattern ── */}
      <div className="fixed inset-0 pointer-events-none -z-10 bg-df-white">
        <div
          className="absolute inset-0"
          style={{
            backgroundImage: `
              repeating-linear-gradient(
                45deg,
                transparent,
                transparent 38px,
                #E5E5E5 38px,
                #E5E5E5 40px
              ),
              repeating-linear-gradient(
                -45deg,
                transparent,
                transparent 38px,
                #E5E5E5 38px,
                #E5E5E5 40px
              )
            `,
          }}
        />
      </div>

      <div className="min-h-[calc(100vh-140px)] flex flex-col items-center justify-center text-left px-4 md:px-8">
        <div className="bg-df-white dark:bg-black dark:border-white border-brutal shadow-brutal-lg p-8 sm:p-12 md:p-16 max-w-4xl w-full flex flex-col items-start">
          
          {/* Massive Structural Typography */}
          <h1 className="text-[6rem] sm:text-[8rem] md:text-[10rem] lg:text-[12rem] font-black tracking-tighter text-df-black dark:text-zinc-50 leading-none mb-2">
            404
          </h1>
          
          <h2 className="font-mono text-lg md:text-2xl font-bold tracking-[0.1em] text-df-black dark:text-zinc-50 uppercase mb-8">
            [ ROUTE NOT FOUND ]
          </h2>
          
          <p className="font-body text-base md:text-lg font-medium text-df-black/75 dark:text-zinc-50/75 mb-12 border-l-4 border-df-black pl-5 max-w-2xl leading-relaxed">
            The destination you are looking for doesn't exist in our current registry. The link might be broken, or the page has been moved. 
          </p>
          
          {/* Escape Hatch (Signal-Red Button) */}
          <div className="flex flex-col sm:flex-row gap-4">
            <Link 
              to="/" 
              className="px-8 py-4 bg-df-red text-df-white border-2 border-df-black font-mono text-xs md:text-sm font-bold tracking-[0.12em] uppercase shadow-[5px_5px_0px_0px_#000000] hover:translate-y-[2px] hover:translate-x-[2px] hover:shadow-[3px_3px_0px_0px_#000000] active:translate-y-[5px] active:translate-x-[5px] active:shadow-none transition-all"
            >
              [ RETURN TO HOME ]
            </Link>
          </div>
        </div>
      </div>
    </>
  );
}
