import React, { useState } from 'react';
import { motion, useScroll, useTransform } from 'framer-motion';
import SEO from '../components/SEO';
import { buildAboutSchema } from '../config/seoSchemas';

/**
 * Single source for the FAQ. The accordion below renders from this array AND
 * the FAQPage JSON-LD is generated from it, so the rich snippet can never
 * describe a question that is not visibly on the page — which is exactly what
 * Google's FAQ structured-data policy requires.
 */
const FAQS = [
  {
    q: "How does DriveFetch calculate fair market value?",
    a: "Our engine cross-references thousands of live listings, adjusting for mileage, condition, and local market trends to pinpoint the exact true value, eliminating seller inflation."
  },
  {
    q: "Are the vehicle listings real-time?",
    a: "Yes. DriveFetch actively scrapes platforms like PakWheels, OLX, and Gari.pk the moment you execute a search to ensure zero stale data."
  },
  {
    q: "Does DriveFetch store my passwords?",
    a: "Never. We utilize Google OAuth 2.0 for secure, frictionless authentication. We only store basic profile data and your saved preferences."
  },
  {
    q: "Why do some cars get flagged by the AI?",
    a: 'Our NLP models read between the lines of seller descriptions. If a seller claims "B2B genuine" but mentions "sides sprayed," the system immediately flags the contradiction.'
  },
  {
    q: "Is DriveFetch free to use?",
    a: "Yes. Our core matchmaking, scraping, and AI appraisal tools are currently completely free for standard market queries."
  }
];

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
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [formName, setFormName] = useState('');
  const [formEmail, setFormEmail] = useState('');
  const [formMessage, setFormMessage] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setSubmitError('');

    const formData = new FormData(e.target);
    formData.append("access_key", "e5b8198a-38e6-4ea5-b5fa-ade6ca15ce58");

    try {
      const response = await fetch("https://api.web3forms.com/submit", {
        method: "POST",
        body: formData
      });

      const data = await response.json();

      if (data.success) {
        setIsSubmitted(true);
        e.target.reset();
      } else {
        console.error("Web3Forms error:", data.message);
        setSubmitError("Transmission failed. Please try again.");
      }
    } catch (error) {
      console.error("Network Error:", error);
      setSubmitError("Network error. Please check your connection.");
    } finally {
      setIsSubmitting(false);
    }
  };

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
      <SEO
        title="About DriveFetch | Intelligent Car Discovery in Pakistan"
        description="Learn how DriveFetch unifies the Pakistani used car market with multi-agent AI and real-time multi-platform scraping."
        path="/about"
        keywords={['how DriveFetch works', 'car search engine Pakistan', 'DriveFetch FAQ']}
        schema={buildAboutSchema(FAQS)}
      />

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

        {/* ═══ 4. FAQ SECTION ═══ */}
        <motion.div {...slideFromRight}>
          <div className="space-y-6">
            <h2 className="text-3xl md:text-5xl font-black uppercase tracking-tighter text-df-black dark:text-zinc-50 mb-8 mt-12 md:mt-20">
              [ FREQUENTLY ASKED QUESTIONS ]
            </h2>
            <div className="grid grid-cols-1 gap-6">
              {FAQS.map((faq, idx) => (
                <div key={idx} className="bg-white dark:bg-black border-2 border-black dark:border-white shadow-[6px_6px_0px_#000000] dark:shadow-[6px_6px_0px_#ffffff] p-6">
                  <h3 className="font-mono text-sm md:text-base font-bold text-df-black dark:text-zinc-50 mb-3 uppercase tracking-wide">
                    Q: {faq.q}
                  </h3>
                  <p className="font-body text-sm md:text-base text-df-black/80 dark:text-zinc-50/80 leading-relaxed">
                    A: {faq.a}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ═══ 5. CONTACT FORM ═══ */}
        <motion.div {...slideFromLeft}>
          <div className="bg-df-grey dark:bg-zinc-900 border-2 border-black dark:border-white shadow-[8px_8px_0px_#000000] dark:shadow-[8px_8px_0px_#ffffff] p-8 md:p-12 mt-12 md:mt-20">
            <h2 className="text-3xl md:text-5xl font-black uppercase tracking-tighter text-df-black dark:text-zinc-50 mb-8">
              [ TRANSMIT MESSAGE ]
            </h2>
            <form onSubmit={handleSubmit} className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block font-mono text-xs font-bold text-df-black dark:text-zinc-50 uppercase tracking-widest mb-2">NAME</label>
                  <input required name="name" type="text" maxLength={200} value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="YOUR NAME" className="w-full bg-white dark:bg-black border-2 border-black dark:border-white p-3 text-black dark:text-white font-mono text-sm focus:outline-none focus:ring-4 focus:ring-red-600/50 transition-all placeholder-gray-500" />
                </div>
                <div>
                  <label className="block font-mono text-xs font-bold text-df-black dark:text-zinc-50 uppercase tracking-widest mb-2">EMAIL</label>
                  <input required name="email" type="email" maxLength={200} value={formEmail} onChange={(e) => setFormEmail(e.target.value)} placeholder="YOUR EMAIL" className="w-full bg-white dark:bg-black border-2 border-black dark:border-white p-3 text-black dark:text-white font-mono text-sm focus:outline-none focus:ring-4 focus:ring-red-600/50 transition-all placeholder-gray-500" />
                </div>
              </div>
              <div>
                <label className="block font-mono text-xs font-bold text-df-black dark:text-zinc-50 uppercase tracking-widest mb-2">MESSAGE</label>
                <textarea required name="message" rows="4" maxLength={200} value={formMessage} onChange={(e) => setFormMessage(e.target.value)} placeholder="ENTER MESSAGE" className="w-full bg-white dark:bg-black border-2 border-black dark:border-white p-3 text-black dark:text-white font-mono text-sm focus:outline-none focus:ring-4 focus:ring-red-600/50 transition-all placeholder-gray-500" />
              </div>
              {submitError && (
                <div className="font-mono text-xs font-bold text-red-600 dark:text-red-500 bg-red-100 dark:bg-red-900/30 border-2 border-red-600 dark:border-red-500 p-3">
                  [ ERROR ]: {submitError}
                </div>
              )}
              <button disabled={isSubmitting || !formName.trim() || !formEmail.trim() || !formMessage.trim()} type="submit" className="w-full bg-red-600 text-white font-black uppercase py-4 border-2 border-black dark:border-white hover:-translate-y-1 hover:-translate-x-1 hover:shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:hover:shadow-[6px_6px_0px_0px_rgba(255,255,255,1)] transition-all disabled:opacity-50 disabled:hover:translate-x-0 disabled:hover:translate-y-0 disabled:hover:shadow-none">
                {isSubmitting ? '[ TRANSMITTING... ]' : 'SUBMIT'}
              </button>
            </form>
          </div>
        </motion.div>

      </div>
    </main>

    {/* ═══ THANK YOU MODAL ═══ */}
    {isSubmitted && (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
        <div className="bg-white dark:bg-zinc-900 border-4 border-black dark:border-white p-8 max-w-md w-full shadow-[12px_12px_0px_0px_rgba(0,0,0,1)] dark:shadow-[12px_12px_0px_0px_rgba(255,255,255,1)] text-black dark:text-white transition-all">
          <div className="text-xs font-mono text-red-600 dark:text-red-500 font-bold mb-2">
            // STATUS: 200 OK
          </div>
          <h3 className="font-black text-2xl uppercase tracking-tight mb-4">
            [ TRANSMISSION RECEIVED ]
          </h3>
          <p className="text-sm text-zinc-700 dark:text-zinc-300 font-medium mb-6">
            Your query has been logged and dispatched directly to DriveFetch operations. We will respond via email shortly.
          </p>
          <button
            onClick={() => setIsSubmitted(false)}
            className="w-full bg-red-600 text-white font-bold uppercase py-3 px-6 border-2 border-black dark:border-white hover:-translate-y-0.5 hover:-translate-x-0.5 hover:shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:hover:shadow-[4px_4px_0px_0px_rgba(255,255,255,1)] transition-all"
          >
            [ DISMISS ]
          </button>
        </div>
      </div>
    )}
    </>
  );
}