import React from 'react';

export default function About() {
  return (
    <div className="relative z-10 pt-32 px-6 pb-24 min-h-screen flex flex-col items-center font-sans text-black">
      
      {/* ── 1-Tone Solid Grey Background ── */}
      <div className="fixed inset-0 z-[-1] pointer-events-none overflow-hidden flex items-center justify-center bg-[#a3a3a3]">
        <div className="absolute inset-0 opacity-[0.05]" style={{ backgroundImage: 'radial-gradient(#000000 1px, transparent 1px)', backgroundSize: '32px 32px' }} />
        <div className="absolute w-[80vw] h-[80vw] max-w-[1000px] max-h-[1000px] bg-white rounded-full blur-[140px] top-[10%] left-[-10%] opacity-40" />
      </div>

      <div className="max-w-3xl w-full">
        <h1 className="text-5xl font-black tracking-tighter mb-8 text-black text-center">About GaariGuru</h1>
        
        {/* Frosted Glass Panel */}
        <div className="bg-white/60 backdrop-blur-md border border-black/15 rounded-3xl p-10 shadow-2xl space-y-8">
          
          <section>
            <h2 className="text-2xl font-black tracking-tight mb-3">The Problem</h2>
            <p className="text-black/80 leading-relaxed text-lg font-bold">
              The Pakistani used car market is fragmented. Buyers spend hours cross-referencing listings between platforms like PakWheels and OLX, only to encounter duplicate ads, fake pricing, and hidden mechanical faults. Making an informed decision requires deep market knowledge that most buyers simply do not have.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-black tracking-tight mb-3">Our Solution</h2>
            <p className="text-black/80 leading-relaxed text-lg font-bold">
              GaariGuru is an AI-powered aggregator. Our autonomous web scrapers ingest data from the top platforms in real-time. We then pass this data through highly tuned Large Language Models to normalize prices, flag suspicious listing details (like "showered for fresh look"), and grade the vehicle's market liquidity.
            </p>
          </section>

          <hr className="border-black/15" />

          <section>
            <h2 className="text-2xl font-black tracking-tight mb-6">Engineering Team</h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
              
              <div className="p-4 bg-white/40 rounded-xl border border-black/10 text-center shadow-sm">
                <p className="font-black text-lg">Muhammad Ismail</p>
                <p className="text-sm text-black/60 font-bold mt-1">Lead Architect</p>
              </div>

              <div className="p-4 bg-white/40 rounded-xl border border-black/10 text-center shadow-sm">
                <p className="font-black text-lg">Sufiyan Ahmed</p>
                <p className="text-sm text-black/60 font-bold mt-1">Systems Engineer</p>
              </div>

              <div className="p-4 bg-white/40 rounded-xl border border-black/10 text-center shadow-sm">
                <p className="font-black text-lg">Zaheen Masood</p>
                <p className="text-sm text-black/60 font-bold mt-1">Data Pipeline</p>
              </div>

            </div>
          </section>

        </div>
      </div>
    </div>
  );
}