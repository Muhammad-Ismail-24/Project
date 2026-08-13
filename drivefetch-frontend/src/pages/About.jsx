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

  /* ── The Data Blueprint: 3-layer scroll crossfade over white ── */
  const chaosOpacity    = useTransform(scrollYProgress, [0, 0.3, 0.5], [1, 1, 0]);
  const orderOpacity    = useTransform(scrollYProgress, [0.3, 0.5, 0.7, 0.9], [0, 1, 1, 0]);
  const architectOpacity = useTransform(scrollYProgress, [0.6, 0.8, 1], [0, 1, 1]);

  return (
    <>
    {/* ── The Data Blueprint — scroll-linked background ── */}
    <div className="fixed inset-0 pointer-events-none -z-10 overflow-hidden bg-white dark:bg-zinc-950 bg-[linear-gradient(to_right,#e5e7eb_1px,transparent_1px),linear-gradient(to_bottom,#e5e7eb_1px,transparent_1px)] dark:bg-[linear-gradient(to_right,#27272a_1px,transparent_1px),linear-gradient(to_bottom,#27272a_1px,transparent_1px)] bg-[size:20px_20px]" aria-hidden="true">

      {/* Stage 1: The Chaos — widely spaced diagonal sketch lines */}
      <motion.div
        style={{ opacity: chaosOpacity }}
        className="absolute inset-0"
      >
        <div
          className="absolute inset-0"
          style={{
            backgroundImage: `
              repeating-linear-gradient(
                45deg,
                transparent,
                transparent 58px,
                #B3B3B3 58px,
                #B3B3B3 59px
              ),
              repeating-linear-gradient(
                -45deg,
                transparent,
                transparent 78px,
                #C4C4C4 78px,
                #C4C4C4 79px
              ),
              repeating-linear-gradient(
                30deg,
                transparent,
                transparent 68px,
                #BEBEBE 68px,
                #BEBEBE 69px
              )
            `,
          }}
        />
      </motion.div>

      {/* Stage 2: The Order — deliberate dot-matrix targeting grid */}
      <motion.div
        style={{ opacity: orderOpacity }}
        className="absolute inset-0"
      >
        <div
          className="absolute inset-0"
          style={{
            backgroundImage: `radial-gradient(circle, #A3A3A3 1.5px, transparent 1.5px)`,
            backgroundSize: '40px 40px',
          }}
        />
      </motion.div>

      {/* Stage 3: The Architect — precision crosshair (+) grid */}
      <motion.div
        style={{ opacity: architectOpacity }}
        className="absolute inset-0"
      >
        <div
          className="absolute inset-0"
          style={{
            backgroundImage: `
              linear-gradient(to right,  transparent 39px, #C0C0C0 39px, #C0C0C0 41px, transparent 41px),
              linear-gradient(to bottom, transparent 39px, #C0C0C0 39px, #C0C0C0 41px, transparent 41px)
            `,
            backgroundSize: '80px 80px',
          }}
        />
      </motion.div>

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
          <h1 className="text-6xl md:text-8xl font-black uppercase tracking-tighter leading-[0.9] text-df-black dark:text-zinc-50">
            THE <span className="text-[#E5202E]">SYSTEM</span><br />ARCHITECTURE.
          </h1>
        </motion.div>

        {/* ═══ 2. PROBLEM & SOLUTION — Stacked Cards ═══ */}
        <div className="space-y-8 md:space-y-12">

          {/* Card 1: The Problem */}
          <motion.div {...slideFromLeft}>
            <div className="bg-white dark:bg-black border-brutal dark:border-white shadow-[8px_8px_0px_#000000] dark:shadow-[8px_8px_0px_#ffffff] p-6 sm:p-8 md:p-10">
              <span className="font-mono text-xs font-bold tracking-[0.1em] text-df-black/40 dark:text-white/40 uppercase block mb-4">
                [ STATUS: FRAGMENTED ]
              </span>
              <h2 className="text-display-md text-df-black dark:text-zinc-50 mb-4">
                THE MARKET IS BROKEN.
              </h2>
              <p className="font-body text-base md:text-lg leading-relaxed text-df-black/80 dark:text-white/80 max-w-2xl">
                Buyers spend hours cross-referencing listings, only to encounter duplicate ads, fake pricing, and hidden faults. Making an informed decision requires deep market knowledge most simply do not have.
              </p>
            </div>
          </motion.div>

          {/* Card 2: The Engine */}
          <motion.div {...slideFromRight}>
            <div className="bg-white dark:bg-black border-brutal dark:border-white shadow-[8px_8px_0px_#000000] dark:shadow-[8px_8px_0px_#ffffff] p-6 sm:p-8 md:p-10">
              <span className="font-mono text-xs font-bold tracking-[0.1em] text-df-red uppercase block mb-4">
                [ STATUS: AUTOMATED ]
              </span>
              <h2 className="text-display-md text-df-black dark:text-zinc-50 mb-4">
                AI-DRIVEN ORCHESTRATION.
              </h2>
              <p className="font-body text-base md:text-lg leading-relaxed text-df-black/80 dark:text-white/80 max-w-2xl">
                DriveFetch is an autonomous aggregator. Our scrapers ingest real-time data, passing it through highly-tuned LLMs to normalize prices, flag suspicious details, and grade market liquidity instantly.
              </p>
            </div>
          </motion.div>

        </div>

        {/* ═══ 3. FOUNDER — The ID Badge ═══ */}
        <motion.div {...slideFromLeft}>
          <div className="bg-black border-2 border-black dark:border-white shadow-[8px_8px_0px_#E5202E] p-6 sm:p-8 md:p-10">
            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-6 sm:gap-8">

              {/* Photo Placeholder */}
              <div className="w-24 h-24 md:w-32 md:h-32 shrink-0 bg-gray-300 border-brutal flex items-center justify-center grayscale contrast-125 overflow-hidden">
                <span className="font-mono text-[9px] md:text-[10px] font-bold text-df-black/40 dark:text-white/40 tracking-[0.06em] text-center select-none leading-tight px-1">
                  [ INSERT<br />B&amp;W PHOTO ]
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