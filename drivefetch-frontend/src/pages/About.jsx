import React from 'react';

export default function About() {
  return (
    <div className="relative z-10 pt-24 md:pt-32 px-4 md:px-6 pb-16 md:pb-24 min-h-screen flex flex-col items-center font-sans text-black">
      
      {/* ── 1-Tone Solid Grey Background ── */}
      <div className="fixed inset-0 z-[-1] pointer-events-none overflow-hidden bg-[#b0b0b0]">
        <div className="absolute inset-0" style={{ backgroundImage: 'linear-gradient(to right,rgba(0,0,0,0.06) 1px,transparent 1px),linear-gradient(to bottom,rgba(0,0,0,0.06) 1px,transparent 1px)', backgroundSize: '72px 72px' }} />
        <div className="absolute w-[75vw] h-[75vw] max-w-[1100px] max-h-[1100px] bg-white rounded-full blur-[160px] opacity-35 top-[-10%] right-[-12%]" />
        <div className="absolute w-[40vw] h-[40vw] max-w-[600px] max-h-[600px] bg-white rounded-full blur-[120px] opacity-15 bottom-[5%] left-[-5%]" />
        <div className="absolute inset-0" style={{ background: 'radial-gradient(ellipse at 60% 40%, transparent 40%, rgba(0,0,0,0.18) 100%)' }} />
      </div>

      <div className="max-w-3xl w-full">
        <h1 className="text-4xl md:text-5xl font-black tracking-tighter mb-6 md:mb-8 text-black text-center">
          About GaariGuru
        </h1>
        
        {/* Frosted Glass Panel */}
        <div className="bg-white/55 backdrop-blur-xl border border-white/60 rounded-2xl p-6 sm:p-8 md:p-10 shadow-lg space-y-6 md:space-y-8">
          
          <section>
            <h2 className="text-lg md:text-xl font-semibold tracking-tight mb-2 md:mb-3">The Problem</h2>
            <p className="text-black leading-relaxed text-base md:text-lg font-bold">
              The Pakistani used car market is fragmented. Buyers spend hours cross-referencing listings between platforms like PakWheels and OLX, only to encounter duplicate ads, fake pricing, and hidden mechanical faults. Making an informed decision requires deep market knowledge that most buyers simply do not have.
            </p>
          </section>

          <section>
            <h2 className="text-lg md:text-xl font-semibold tracking-tight mb-2 md:mb-3">Our Solution</h2>
            <p className="text-black leading-relaxed text-base md:text-lg font-bold">
              GaariGuru is an AI-powered aggregator. Our autonomous web scrapers ingest data from the top platforms in real-time. We then pass this data through highly tuned Large Language Models to normalize prices, flag suspicious listing details (like "showered for fresh look"), and grade the vehicle's market liquidity.
            </p>
          </section>

          <hr className="border-black/15" />

          <section>
            <h2 className="text-xl md:text-2xl font-black tracking-tight mb-4 md:mb-6">Founder</h2>
            <div className="max-w-sm">
              <div className="p-4 bg-white/50 rounded-xl border border-white/60 flex items-center gap-4">
                <div className="w-14 h-14 shrink-0 bg-black rounded-full flex items-center justify-center text-white text-xl font-black shadow-inner">
                  MI
                </div>
                <div>
                  <p className="font-semibold text-base md:text-lg">Muhammad Ismail</p>
                  <p className="text-xs text-black/50 font-medium mt-0.5">Founder & Lead Architect</p>
                </div>
              </div>
            </div>
          </section>

        </div>
      </div>
    </div>
  );
}