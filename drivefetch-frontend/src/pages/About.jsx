import React from 'react';
import { Helmet } from 'react-helmet-async';
import useReveal from '../utils/useReveal';

export default function About() {
  const headingRef = useReveal();

  return (
    <main className="relative z-10 pt-32 md:pt-40 px-4 md:px-6 pb-16 md:pb-24 min-h-screen flex flex-col items-center font-sans">
      <Helmet>
        <title>About DriveFetch — How Our AI Car Search Works</title>
        <meta name="description" content="Learn how DriveFetch uses AI to aggregate listings from PakWheels, OLX, and more to give you the best used car options in Pakistan." />
        <link rel="canonical" href="https://carfinderproject.vercel.app/about" />
      </Helmet>

      <div className="max-w-3xl w-full">
        <h1 ref={headingRef} className="reveal font-display text-4xl md:text-5xl font-black tracking-tighter mb-6 md:mb-8 text-text text-center">
          About DriveFetch
        </h1>

        {/* Frosted Glass Panel */}
        <div className="glass p-6 sm:p-8 md:p-10 space-y-6 md:space-y-8">

          <section>
            <h2 className="text-lg md:text-xl font-semibold tracking-tight mb-2 md:mb-3 text-text">The Problem</h2>
            <p className="text-text-dim leading-relaxed text-base md:text-lg font-medium">
              The Pakistani used car market is fragmented. Buyers spend hours cross-referencing listings between platforms like PakWheels and OLX, only to encounter duplicate ads, fake pricing, and hidden mechanical faults. Making an informed decision requires deep market knowledge that most buyers simply do not have.
            </p>
          </section>

          <section>
            <h2 className="text-lg md:text-xl font-semibold tracking-tight mb-2 md:mb-3 text-text">Our Solution</h2>
            <p className="text-text-dim leading-relaxed text-base md:text-lg font-medium">
              DriveFetch is an AI-powered aggregator. Our autonomous web scrapers ingest data from the top platforms in real-time. We then pass this data through highly tuned Large Language Models to normalize prices, flag suspicious listing details (like "showered for fresh look"), and grade the vehicle's market liquidity.
            </p>
          </section>

          <hr style={{ borderColor: 'var(--df-glass-border)' }} />

          <section>
            <h2 className="font-display text-xl md:text-2xl font-black tracking-tight mb-4 md:mb-6 text-text">Founder</h2>
            <div className="max-w-sm">
              <div className="glass-thin p-4 flex items-center gap-4">
                <div className="w-14 h-14 shrink-0 bg-accent rounded-full flex items-center justify-center text-white text-xl font-black shadow-inner">
                  MI
                </div>
                <div>
                  <p className="font-semibold text-base md:text-lg text-text">Muhammad Ismail</p>
                  <p className="text-xs text-text-faint font-medium mt-0.5">Founder & Lead Architect</p>
                </div>
              </div>
            </div>
          </section>

        </div>
      </div>
    </main>
  );
}