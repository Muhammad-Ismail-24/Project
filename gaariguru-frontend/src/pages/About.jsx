import React from 'react';

export default function About() {
  return (
    <div className="relative z-10 pt-24 md:pt-32 px-4 md:px-6 pb-16 md:pb-24 min-h-screen flex flex-col items-center font-sans text-black">
      
      {/* ── 1-Tone Solid Grey Background ── */}
      <div className="fixed inset-0 z-[-1] pointer-events-none overflow-hidden flex items-center justify-center bg-[#a3a3a3]">
        <div className="absolute inset-0 opacity-[0.05]" style={{ backgroundImage: 'radial-gradient(#000000 1px, transparent 1px)', backgroundSize: '32px 32px' }} />
        <div className="absolute w-[80vw] h-[80vw] max-w-[1000px] max-h-[1000px] bg-white rounded-full blur-[140px] top-[10%] left-[-10%] opacity-40" />
      </div>

      <div className="max-w-3xl w-full">
        <h1 className="text-4xl md:text-5xl font-black tracking-tighter mb-6 md:mb-8 text-black text-center">
          About GaariGuru
        </h1>
        
        {/* Frosted Glass Panel */}
        <div className="bg-white/60 backdrop-blur-md border border-black/15 rounded-2xl md:rounded-3xl p-6 sm:p-8 md:p-10 shadow-2xl space-y-6 md:space-y-8">
          
          <section>
            <h2 className="text-xl md:text-2xl font-black tracking-tight mb-2 md:mb-3">The Problem</h2>
            <p className="text-black leading-relaxed text-base md:text-lg font-bold">
              The Pakistani used car market is fragmented. Buyers spend hours cross-referencing listings between platforms like PakWheels and OLX, only to encounter duplicate ads, fake pricing, and hidden mechanical faults. Making an informed decision requires deep market knowledge that most buyers simply do not have.
            </p>
          </section>

          <section>
            <h2 className="text-xl md:text-2xl font-black tracking-tight mb-2 md:mb-3">Our Solution</h2>
            <p className="text-black leading-relaxed text-base md:text-lg font-bold">
              GaariGuru is an AI-powered aggregator. Our autonomous web scrapers ingest data from the top platforms in real-time. We then pass this data through highly tuned Large Language Models to normalize prices, flag suspicious listing details (like "showered for fresh look"), and grade the vehicle's market liquidity.
            </p>
          </section>

          <hr className="border-black/15" />

          <section>
            <h2 className="text-xl md:text-2xl font-black tracking-tight mb-4 md:mb-6">Founder</h2>
            <div className="max-w-sm">
              <div className="p-5 bg-white/40 rounded-xl border border-black/10 shadow-sm flex items-center gap-4">
                <div className="w-14 h-14 shrink-0 bg-black rounded-full flex items-center justify-center text-white text-xl font-black shadow-inner">
                  MI
                </div>
                <div>
                  <p className="font-black text-lg md:text-xl">Muhammad Ismail</p>
                  <p className="text-sm text-black font-bold mt-0.5">Founder & Lead Architect</p>
                </div>
              </div>
            </div>
          </section>

        </div>
      </div>
    </div>
  );
}