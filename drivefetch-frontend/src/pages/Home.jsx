import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, useScroll, useTransform } from 'framer-motion';
import { lazy, Suspense } from 'react';
const DynamicBackground = lazy(() => import('../components/DynamicBackground'));
import SEO from '../components/SEO';
import { homeSchema } from '../config/seoSchemas';
import { searchCars } from '../utils/api';
import CarResultCard from '../components/CarResultCard';
import FeatureErrorBoundary from '../components/FeatureErrorBoundary';

/**
 * Floating monospace system tags scattered in the background.
 * Matches the reference mockup's "[SYS_INIT]", "[DRIVE_DATA]", "[FETCH_STATUS]" style.
 */
const SYSTEM_TAGS = [
  { label: '[DRIVE_DATA]', top: '8%',  left: '30%'  },
  { label: '[SYS_INIT]',   top: '22%', left: '8%'   },
  { label: '[SYS_INIT]',   top: '14%', right: '12%' },
  { label: '[DRIVE_DATA]', top: '16%', right: '4%'  },
  { label: '[SYS_INIT]',   top: '78%', left: '2%'   },
  { label: '[SYS_INIT]',   top: '82%', left: '8%'   },
  { label: '[DRIVE_DATA]', top: '80%', left: '50%'  },
  { label: '[FETCH_STATUS]', top: '82%', right: '8%' },
  { label: '[DRIVE_DATA]', top: '76%', left: '2%'   },
];

/**
 * ScrollHoverCard — Handles Neo-Brutalist hover physics on mobile scroll.
 */
function ScrollHoverCard({ as = 'div', className, hoverClass, children, ...props }) {
  const [inView, setInView] = useState(false);
  const isMobile = typeof window !== 'undefined' && window.innerWidth < 768;
  
  // Combine base classes and active mobile-hover classes (stripping 'hover:' prefix for mobile)
  const activeHover = hoverClass.split(' ').map(c => c.replace(/^hover:/, '')).join(' ');
  const finalClass = `${className} ${isMobile && inView ? activeHover : hoverClass}`;

  const MotionTag = motion[as];

  return (
    <MotionTag
      onViewportEnter={() => isMobile && setInView(true)}
      onViewportLeave={() => isMobile && setInView(false)}
      viewport={{ amount: 0.5, margin: "0px 0px -15% 0px" }}
      className={finalClass}
      {...props}
    >
      {children}
    </MotionTag>
  );
}


function SystemTags() {
  return (
    <>
      {SYSTEM_TAGS.map((tag, i) => (
        <span
          key={i}
          className="sys-tag absolute"
          style={{
            top: tag.top,
            left: tag.left,
            right: tag.right,
          }}
        >
          {tag.label}
        </span>
      ))}
    </>
  );
}

/**
 * Gateway card data — each card maps to a tool/route.
 * Card 1 scrolls to Section 4. Cards 2 & 3 navigate via router.
 */
const GATEWAY_CARDS = [
  {
    index: '01',
    tag: 'MANUAL',
    headline: '[ DIRECT SEARCH ]',
    body: 'Query the full market yourself. Filter by make, model, price, year — raw access to every listing we track.',
    action: 'scroll',
    target: '#console',
  },
  {
    index: '02',
    tag: 'MATCH',
    headline: '[ AI MATCHMAKER ]',
    body: 'Tell our engine what you need. It cross-references specs, flags risk, and ranks the best options for you.',
    action: 'route',
    target: '/recommend',
  },
  {
    index: '03',
    tag: 'CHAT',
    headline: '[ ASSISTANT CHAT ]',
    body: 'Talk to DriveFetch like a human. Ask questions, compare trims, get instant verdicts in natural language.',
    action: 'route',
    target: '/chat',
  },
];

/**
 * Financial tools teaser cards — route to /calculators.
 */
const FINANCIAL_TOOLS = [
  { label: 'FUEL COST ESTIMATOR', desc: 'Monthly fuel spend based on your commute and engine.' },
  { label: 'TOKEN TAX BRACKETS', desc: 'Punjab & Sindh token tax by engine capacity.' },
  { label: 'TRANSFER FEES CALCULATOR', desc: 'Excise, withholding tax, filer vs non-filer.' },
];

/**
 * GatewayCard — Neo-Brutalist CTA card.
 */
function GatewayCard({ card }) {
  const navigate = useNavigate();

  const handleClick = () => {
    if (card.action === 'scroll') {
      const el = document.querySelector(card.target);
      if (el) el.scrollIntoView({ behavior: 'smooth' });
    } else {
      navigate(card.target);
    }
  };

  return (
    <ScrollHoverCard 
      className="group bg-df-grey dark:bg-black border-brutal flex flex-col shadow-[4px_4px_0px_#000000] dark:shadow-[4px_4px_0px_#ffffff] transition-all duration-200"
      hoverClass="hover:-translate-y-2 hover:shadow-[8px_8px_0px_#000000] dark:hover:shadow-[8px_8px_0px_#ffffff]"
    >
      <div className="px-5 sm:px-6 pt-5 sm:pt-6 pb-3">
        <span className="font-mono text-xs sm:text-sm font-bold tracking-[0.1em] text-df-red">
          {card.index} / {card.tag}
        </span>
      </div>
      <div className="px-5 sm:px-6 flex-1 flex flex-col">
        <h3 className="text-xl md:text-2xl font-bold text-df-black dark:text-zinc-100 mb-3 sm:mb-4">
          {card.headline}
        </h3>
        <p className="font-body text-sm sm:text-base text-df-black/60 dark:text-white/60 leading-relaxed mb-6 sm:mb-8">
          {card.body}
        </p>
      </div>
      <div className="px-5 sm:px-6 pb-5 sm:pb-6 mt-auto">
        <button
          onClick={handleClick}
          className="w-full px-4 py-3 sm:py-3.5 border-brutal-thin bg-df-white dark:bg-zinc-900 text-df-black dark:text-zinc-100 font-mono text-xs sm:text-sm font-bold tracking-[0.06em] transition-all duration-100 hover:bg-df-black hover:text-df-white dark:hover:bg-white dark:hover:text-black hover:shadow-none active:translate-x-[2px] active:translate-y-[2px]"
        >
          [ LAUNCH TOOL → ]
        </button>
      </div>
    </ScrollHoverCard>
  );
}

export default function Home() {
  return (
    <main className="relative w-full overflow-x-hidden" style={{ perspective: '1000px' }}>
      <SEO
        path="/"
        description="Find the perfect used car in Pakistan with DriveFetch. Real-time multi-platform search aggregating PakWheels, OLX & Gari.pk with AI-powered inspection and pricing insights."
        schema={homeSchema}
      />

      {/* Scroll-Linked SVG Background (Framer Motion) */}
      <Suspense fallback={null}>
        <DynamicBackground />
      </Suspense>

      {/* ═══════════════════════════════════════════════
          SECTION 1 — HERO
          ═══════════════════════════════════════════════ */}
      <section
        id="hero"
        className="relative z-10 flex items-center justify-center py-16 md:py-24 px-5 sm:px-8 lg:px-12"
      >
        <SystemTags />

        <motion.div
          initial={{ opacity: 0, scale: 0.9, rotateX: 15, y: 80 }}
          whileInView={{ opacity: 1, scale: 1, rotateX: 0, y: 0 }}
          viewport={{ once: false, margin: "-10%" }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          className="w-full max-w-[1400px] mx-auto origin-center"
        >
          <h1 className="text-4xl sm:text-6xl md:text-7xl lg:text-[5.5rem] leading-[0.95] tracking-tight font-black text-df-black dark:text-zinc-100">
            <span className="block">FIND THE RIGHT CAR.</span>
            <span className="block">
              <span className="text-[#E5202E] font-bold">SKIP</span>
              {' '}THE WRONG ONES.
            </span>
          </h1>
          <a
            href="#tools-section"
            onClick={(e) => {
              e.preventDefault();
              document.getElementById('tools-section')?.scrollIntoView({ behavior: 'smooth' });
            }}
            className="bg-red-600 text-white font-bold uppercase py-3 px-6 border-2 border-black dark:border-white hover:-translate-y-1 hover:-translate-x-1 hover:shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:hover:shadow-[4px_4px_0px_0px_rgba(255,255,255,1)] transition-all inline-block mt-8 font-mono text-sm tracking-[0.06em]"
          >
            [ EXPLORE TOOLS ↓ ]
          </a>
        </motion.div>
      </section>

      {/* ═══════════════════════════════════════════════
          SECTION 2 — GATEWAY CTAs
          ═══════════════════════════════════════════════ */}
      <section id="tools-section" className="relative z-10 py-16 md:py-24 px-5 sm:px-8 lg:px-12">
        <motion.div
          initial={{ opacity: 0, scale: 0.9, rotateX: 15, y: 80 }}
          whileInView={{ opacity: 1, scale: 1, rotateX: 0, y: 0 }}
          viewport={{ once: false, margin: "-10%" }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          className="w-full max-w-[1400px] mx-auto"
        >
          <div className="border-t-2 border-df-black dark:border-white pt-6 mb-16 sm:mb-20">
            <span className="font-mono text-xs sm:text-sm font-bold tracking-[0.08em] text-df-black/50 dark:text-white/50">
              // SECTION 02: CHOOSE YOUR MISSION
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 lg:gap-8">
            {GATEWAY_CARDS.map((card) => (
              <GatewayCard key={card.index} card={card} />
            ))}
          </div>
        </motion.div>
      </section>

      {/* ═══════════════════════════════════════════════
          SECTION 3 — INTELLIGENCE ENGINE & MARKET COVERAGE
          ═══════════════════════════════════════════════ */}
      <section id="engine" className="relative z-10 py-16 md:py-24 px-5 sm:px-8 lg:px-12">
        <motion.div
          initial={{ opacity: 0, scale: 0.9, rotateX: 15, y: 80 }}
          whileInView={{ opacity: 1, scale: 1, rotateX: 0, y: 0 }}
          viewport={{ once: false, margin: "-10%" }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          className="w-full max-w-[1400px] mx-auto"
        >
          <div className="border-t-2 border-df-black dark:border-white pt-6 mb-16 sm:mb-20">
            <span className="font-mono text-xs sm:text-sm font-bold tracking-[0.08em] text-df-black/50 dark:text-white/50">
              // SECTION 03: INTELLIGENCE ENGINE & COVERAGE
            </span>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12 items-start">

            {/* ── LEFT COLUMN: Intelligence Engine Punch Cards ── */}
            <div className="lg:col-span-7 flex flex-col gap-6">
              {[
                {
                  id: '01',
                  title: 'AI CONDITION SCANNER',
                  text: 'We read between the lines. If a seller says "genuine" but mentions a "shower", we flag it immediately.',
                },
                {
                  id: '02',
                  title: 'TRUE FAIR MARKET VALUE',
                  text: 'No more guessing. We cross-reference thousands of live listings to calculate the exact price a car should sell for.',
                },
                {
                  id: '03',
                  title: 'HIDDEN RISK DETECTION',
                  text: 'Duplicate files, suspicious mileage, and sketchy descriptions are instantly caught and graded before you buy.',
                },
              ].map((card) => (
                <ScrollHoverCard key={card.id} 
                  className="bg-df-white dark:bg-zinc-900 border-2 border-df-black dark:border-white p-6 shadow-[4px_4px_0px_#000000] dark:shadow-[4px_4px_0px_#ffffff] rounded-none transition-transform duration-200"
                  hoverClass="hover:-translate-y-1"
                >
                  <div className="font-mono text-[10px] sm:text-xs font-bold tracking-[0.08em] text-df-red mb-3">
                    [ ENGINE // {card.id} ]
                  </div>
                  <h3 className="text-xl sm:text-2xl font-black text-df-black dark:text-zinc-100 mb-2 leading-tight">
                    {card.title}
                  </h3>
                  <p className="font-body text-sm sm:text-base text-df-black/70 dark:text-white/70 leading-relaxed">
                    {card.text}
                  </p>
                </ScrollHoverCard>
              ))}
            </div>

            {/* ── RIGHT COLUMN: Market Coverage & Trust ── */}
            <div className="lg:col-span-5 flex flex-col gap-8 sm:gap-10">
              <h2 className="text-display-lg text-df-black dark:text-zinc-100 leading-[0.95]">
                SCANNING EVERY MAJOR PLATFORM IN PAKISTAN.
              </h2>

              {/* Platform Coverage Pills */}
              <div className="flex flex-wrap gap-3">
                {['PAKWHEELS', 'OLX PAKISTAN', 'GARI.PK', 'DRIVE.PK'].map((platform) => (
                  <span
                    key={platform}
                    className="px-4 sm:px-5 py-2.5 sm:py-3 border-brutal-thin bg-df-white dark:bg-zinc-900 text-df-black dark:text-zinc-100 font-mono text-xs sm:text-sm font-bold tracking-[0.06em] cursor-default select-none transition-all duration-[50ms] hover:bg-df-black hover:text-df-white dark:hover:bg-white dark:hover:text-black"
                  >
                    [ {platform} ]
                  </span>
                ))}
              </div>

              {/* LIVE MARKET PULSE */}
              <div className="border-t border-df-black/15 pt-6">
                <div className="bg-[#F5F5F5] dark:bg-zinc-800 border border-df-black dark:border-white p-4 sm:p-5 w-full">
                  <div className="font-mono text-xs sm:text-sm text-df-black/80 dark:text-white/80 tracking-[0.05em] space-y-2">
                    <div className="flex items-center gap-2">
                      <span>STATUS: MULTI-AGENT SCRAPER [ONLINE]</span>
                      <span className="bg-green-500 animate-pulse rounded-full w-2 h-2 inline-block"></span>
                    </div>
                    <div>LAST SWEEP: 14 SECONDS AGO</div>
                    <div>TOTAL LISTINGS TRACKED: 42,891+</div>
                  </div>
                </div>
              </div>

            </div>

          </div>
        </motion.div>
      </section>

      {/* ═══════════════════════════════════════════════
          SECTION 4 — COMMAND CONSOLE
          ═══════════════════════════════════════════════ */}
      <CommandConsoleSection />

    </main>
  );
}

function CommandConsoleSection() {
  const [query, setQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  const handleSearch = async (searchQuery) => {
    const q = (searchQuery || query).trim();
    if (!q) return;
    setIsLoading(true);
    setError(null);
    setResults(null);
    try {
      const data = await searchCars(q);
      setResults(data);
    } catch (err) {
      setError('Search failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      handleSearch().catch(error => {
        console.error('Search failed:', error);
        setError('Search failed. Please try again.');
      });
    }
  };

  return (
    <section id="console" className="relative z-10 py-16 md:py-24 px-5 sm:px-8 lg:px-12">
      <motion.div
        initial={{ opacity: 0, scale: 0.9, rotateX: 15, y: 80 }}
        whileInView={{ opacity: 1, scale: 1, rotateX: 0, y: 0 }}
        viewport={{ once: false, margin: "-10%" }}
        transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        className="w-full max-w-[1400px] mx-auto"
      >
        <div className="border-t-2 border-df-black dark:border-white pt-6 mb-16 sm:mb-20">
          <span className="font-mono text-xs sm:text-sm font-bold tracking-[0.08em] text-df-black/50 dark:text-white/50">
            // SECTION 04: EXECUTE SEARCH
          </span>
        </div>

        <div className="mb-10 sm:mb-14">
          <div className="bg-df-white dark:bg-black border-brutal shadow-[8px_8px_0px_#000000] dark:shadow-[8px_8px_0px_#ffffff] flex flex-col sm:flex-row focus-within:ring-2 focus-within:ring-[#E5202E] focus-within:border-[#E5202E]">
            <div className="flex items-center flex-1 px-4 sm:px-6 py-4 sm:py-5 gap-3 sm:gap-4">
              <svg
                className="w-5 h-5 sm:w-6 sm:h-6 text-df-black/30 dark:text-white/30 shrink-0"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                viewBox="0 0 24 24"
              >
                <circle cx="11" cy="11" r="8" />
                <path d="m21 21-4.3-4.3" />
              </svg>
              <input
                id="console-search-input"
                type="text"
                maxLength={200}
                required
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Honda Civic in Lahore under 50 Lakhs..."
                className="flex-1 bg-transparent font-mono text-sm sm:text-base text-df-black dark:text-zinc-100 placeholder:text-df-black/25 dark:placeholder:text-white/25 outline-none border-none min-w-0"
              />
            </div>
            <button
              id="console-execute-btn"
              onClick={() => {
                handleSearch().catch(error => {
                  if (import.meta.env.DEV) { console.error("Full error details:", error); }
                  console.error("Search failed:", error instanceof Error ? error.message : "Unknown error");
                  setError('Search failed. Please try again.');
                });
              }}
              disabled={isLoading || !query.trim()}
              className="px-6 sm:px-8 py-4 sm:py-5 bg-df-red text-df-white font-mono text-xs sm:text-sm font-bold tracking-[0.08em] border-t sm:border-t-0 sm:border-l border-df-black dark:border-white whitespace-nowrap transition-none hover:bg-[#C41A25] active:translate-x-[1px] active:translate-y-[1px] disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isLoading ? '[ SEARCHING... ]' : '[ EXECUTE SEARCH ]'}
            </button>
          </div>
          <div className="mt-3 font-mono text-[10px] text-df-black/20 dark:text-white/20 tracking-[0.06em]">
            [INPUT_MODE: NATURAL_LANGUAGE] — [BACKEND: AI_PARSE + MULTI_SCRAPE]
          </div>
        </div>

        {(isLoading || error || results) && (
          <div className="mb-16 sm:mb-20">
            {isLoading && (
              <div className="border-brutal-thin bg-df-grey dark:bg-zinc-800 px-6 py-8 flex items-center justify-center gap-3">
                <span className="inline-block w-3 h-3 bg-df-red animate-pulse" />
                <span className="font-mono text-xs sm:text-sm text-df-black/50 dark:text-white/50 tracking-[0.06em]">
                  [FETCHING_RESULTS] — Scanning platforms...
                </span>
              </div>
            )}
            {error && (
              <div className="border-brutal-thin bg-df-white dark:bg-zinc-900 px-6 py-5 flex items-center gap-3">
                <span className="inline-block w-2.5 h-2.5 bg-df-red" />
                <span className="font-mono text-xs sm:text-sm text-df-black/60 dark:text-white/60">{error}</span>
              </div>
            )}
            {results && results.length === 0 && !isLoading && (
              <div className="border-brutal-thin bg-df-grey dark:bg-zinc-800 px-6 py-8 text-center">
                <span className="font-mono text-xs sm:text-sm text-df-black/40 dark:text-white/40 tracking-[0.06em]">
                  [NO_RESULTS] — Try broadening your search or adjusting your budget.
                </span>
              </div>
            )}
            {results && results.length > 0 && !isLoading && (
              <FeatureErrorBoundary featureName="Search Results">
                <div className="space-y-3">
                  <div className="font-mono text-[10px] sm:text-xs font-bold tracking-[0.1em] text-df-black/30 dark:text-white/30 mb-4">
                    [{results.length} RESULT{results.length !== 1 ? 'S' : ''} FOUND]:
                  </div>
                  {results.map((car, i) => (
                    <CarResultCard key={car.id || i} car={car} userQuery={query} />
                  ))}
                </div>
              </FeatureErrorBoundary>
            )}
          </div>
        )}

        {/* ── FINANCIAL TOOLS TEASER ── */}
        <div>
          <div className="font-mono text-[10px] sm:text-xs font-bold tracking-[0.1em] text-df-black/30 dark:text-white/30 mb-4">
            FINANCIAL TOOLS:
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-5">
            {FINANCIAL_TOOLS.map((tool) => (
              <ScrollHoverCard
                as="button"
                key={tool.label}
                onClick={() => navigate('/calculators')}
                className="group bg-df-grey dark:bg-black border-brutal-thin px-5 py-5 sm:py-6 text-left flex flex-col gap-2.5 shadow-[3px_3px_0px_0px_#000000] dark:shadow-[3px_3px_0px_0px_#ffffff] transition-shadow duration-100 hover:bg-df-black dark:hover:bg-white"
                hoverClass="hover:shadow-[5px_5px_0px_0px_#000000] dark:hover:shadow-[5px_5px_0px_0px_#ffffff]"
              >
                <span className="font-mono text-xs sm:text-sm font-bold tracking-[0.06em] text-df-black dark:text-zinc-100 group-hover:text-df-white dark:group-hover:text-black transition-colors duration-[50ms]">
                  [ {tool.label} ]
                </span>
                <span className="font-body text-xs text-df-black/50 dark:text-white/50 leading-relaxed group-hover:text-df-white/60 dark:group-hover:text-black/60 transition-colors duration-[50ms]">
                  {tool.desc}
                </span>
              </ScrollHoverCard>
            ))}
          </div>
        </div>

      </motion.div>
    </section>
  );
}

