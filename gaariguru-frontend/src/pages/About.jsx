import React from 'react';

export default function About() {
  return (
    <div className="relative z-10 pt-32 px-6 pb-24 min-h-screen flex flex-col items-center">
      <div className="max-w-3xl w-full">
        
        <h1 className="text-5xl font-black tracking-tighter mb-8 text-black text-center">About GaariGuru</h1>
        
        <div className="bg-white/70 backdrop-blur-xl border border-white/50 rounded-3xl p-10 shadow-xl space-y-8">
          
          <section>
            <h2 className="text-2xl font-bold tracking-tight mb-3">The Problem</h2>
            <p className="text-neutral-600 leading-relaxed text-lg font-medium">
              The Pakistani used car market is fragmented. Buyers spend hours cross-referencing listings between platforms like PakWheels and OLX, only to encounter duplicate ads, fake pricing, and hidden mechanical faults. Making an informed decision requires deep market knowledge that most buyers simply do not have.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold tracking-tight mb-3">Our Solution</h2>
            <p className="text-neutral-600 leading-relaxed text-lg font-medium">
              GaariGuru is an AI-powered aggregator. Our autonomous web scrapers ingest data from the top platforms in real-time. We then pass this data through highly tuned Large Language Models to normalize prices, flag suspicious listing details (like "showered for fresh look"), and grade the vehicle's market liquidity.
            </p>
          </section>

          <hr className="border-neutral-200" />

          <section>
            <h2 className="text-2xl font-bold tracking-tight mb-6">Engineering Team</h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
              
              <div className="p-4 bg-neutral-50 rounded-xl border border-neutral-100 text-center">
                <p className="font-black text-lg">Muhammad Ismail</p>
                <p className="text-sm text-neutral-500 font-bold mt-1">Lead Architect</p>
              </div>

              <div className="p-4 bg-neutral-50 rounded-xl border border-neutral-100 text-center">
                <p className="font-black text-lg">Sufiyan Ahmed</p>
                <p className="text-sm text-neutral-500 font-bold mt-1">Systems Engineer</p>
              </div>

              <div className="p-4 bg-neutral-50 rounded-xl border border-neutral-100 text-center">
                <p className="font-black text-lg">Zaheen Masood</p>
                <p className="text-sm text-neutral-500 font-bold mt-1">Data Pipeline</p>
              </div>

            </div>
          </section>

        </div>
      </div>
    </div>
  );
}
