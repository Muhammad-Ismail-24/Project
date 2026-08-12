import React from 'react';
import { Helmet } from 'react-helmet-async';
import { motion, useScroll, useTransform } from 'framer-motion';

/* ═══════════════════════════════════════════════════════
   ANIMATION VARIANTS — Horizontal Snap
   ═══════════════════════════════════════════════════════ */

const slideFromLeft = {
  initial: { opacity: 0, x: -80 },
  whileInView: { opacity: 1, x: 0 },
  transition: { duration: 0.4, ease: 'easeOut' },
  viewport: { once: false, amount: 0.2 },
};

const slideFromRight = {
  initial: { opacity: 0, x: 80 },
  whileInView: { opacity: 1, x: 0 },
  transition: { duration: 0.4, ease: 'easeOut' },
  viewport: { once: false, amount: 0.2 },
};

/* ═══════════════════════════════════════════════════════
   ABOUT PAGE — The Manifesto
   ═══════════════════════════════════════════════════════ */

export default function About() {
  const { scrollYProgress } = useScroll();
  const scannerY = useTransform(scrollYProgress, [0, 1], ['0vh', '100vh']);

  return (
    <>
    {/* ── System Scanner — scroll-linked red laser ── */}
    <div className="fixed inset-0 pointer-events-none -z-10 overflow-hidden">
      <motion.div
        style={{ y: scannerY }}
        className="absolute top-0 left-0 w-full h-[2px] bg-[#E5202E] shadow-[0_0_15px_#E5202E] opacity-70"
      />
    </div>

    <main className="relative z-10 pt-28 md:pt-40 px-5 sm:px-8 lg:px-12 pb-20 md:pb-32 min-h-screen flex flex-col items-center">
      <Helmet>
        <title>About DriveFetch — How Our AI Car Search Works</title>
        <meta name="description" content="Learn how DriveFetch uses AI to aggregate listings from PakWheels, OLX, and more to give you the best used car options in Pakistan." />
        <link rel="canonical" href="https://carfinderproject.vercel.app/about" />
      </Helmet>

      <div className="w-full max-w-4xl space-y-12 md:space-y-20">

        {/* ═══ 1. PAGE HEADER — The Manifesto ═══ */}
        <motion.div {...slideFromLeft}>
          <h1 className="text-display-lg leading-[0.95] tracking-tight text-df-black">
            THE SYSTEM<br />ARCHITECTURE.
          </h1>
        </motion.div>

        {/* ═══ 2. PROBLEM & SOLUTION — Stacked Cards ═══ */}
        <div className="space-y-8 md:space-y-12">

          {/* Card 1: The Problem */}
          <motion.div {...slideFromLeft}>
            <div className="bg-white border-brutal shadow-[8px_8px_0px_#000000] p-6 sm:p-8 md:p-10">
              <span className="font-mono text-xs font-bold tracking-[0.1em] text-df-black/40 uppercase block mb-4">
                [ STATUS: FRAGMENTED ]
              </span>
              <h2 className="text-display-md text-df-black mb-4">
                THE MARKET IS BROKEN.
              </h2>
              <p className="font-body text-base md:text-lg leading-relaxed text-df-black/80 max-w-2xl">
                Buyers spend hours cross-referencing listings, only to encounter duplicate ads, fake pricing, and hidden faults. Making an informed decision requires deep market knowledge most simply do not have.
              </p>
            </div>
          </motion.div>

          {/* Card 2: The Engine */}
          <motion.div {...slideFromRight}>
            <div className="bg-white border-brutal shadow-[8px_8px_0px_#000000] p-6 sm:p-8 md:p-10">
              <span className="font-mono text-xs font-bold tracking-[0.1em] text-df-red uppercase block mb-4">
                [ STATUS: AUTOMATED ]
              </span>
              <h2 className="text-display-md text-df-black mb-4">
                AI-DRIVEN ORCHESTRATION.
              </h2>
              <p className="font-body text-base md:text-lg leading-relaxed text-df-black/80 max-w-2xl">
                DriveFetch is an autonomous aggregator. Our scrapers ingest real-time data, passing it through highly-tuned LLMs to normalize prices, flag suspicious details, and grade market liquidity instantly.
              </p>
            </div>
          </motion.div>

        </div>

        {/* ═══ 3. FOUNDER — The ID Badge ═══ */}
        <motion.div {...slideFromLeft}>
          <div className="bg-black border-2 border-black shadow-[8px_8px_0px_#E5202E] p-6 sm:p-8 md:p-10">
            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-6 sm:gap-8">

              {/* Avatar Box */}
              <div className="w-20 h-20 sm:w-24 sm:h-24 shrink-0 bg-white border-brutal flex items-center justify-center whitespace-nowrap">
                <span className="font-mono text-xl sm:text-2xl font-bold text-df-black tracking-tight select-none">
                  [ MI <span className="animate-pulse">_</span> ]
                </span>
              </div>

              {/* Info */}
              <div>
                <h3 className="text-white text-2xl sm:text-3xl font-bold tracking-tight leading-tight">
                  Muhammad Ismail
                </h3>
                <p className="text-df-red font-mono text-xs sm:text-sm font-bold uppercase tracking-widest mt-1">
                  LEAD ARCHITECT // AI ORCHESTRATOR
                </p>
                <p className="text-gray-300 font-mono text-xs sm:text-sm leading-relaxed mt-4 max-w-lg">
                  Engineering full-stack agentic systems and multi-agent architectures. Currently pushing the boundaries of data orchestration at FAST NUCES, Islamabad.
                </p>
              </div>

            </div>
          </div>
        </motion.div>

      </div>
    </main>
    </>
  );
}