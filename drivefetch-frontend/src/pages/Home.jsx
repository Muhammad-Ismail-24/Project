import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import DynamicBackground from '../components/DynamicBackground';
import { searchCars } from '../utils/api';

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
    action: 'scroll',       // smooth-scroll to #console
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
 * 2px black border, 4px hard offset shadow, instant-invert hover on button.
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
    <div className="group bg-df-grey border-brutal flex flex-col shadow-[4px_4px_0px_#000000] transition-all duration-200 hover:-translate-y-2 hover:shadow-[8px_8px_0px_#000000]">
      {/* Top bar — step index */}
      <div className="px-5 sm:px-6 pt-5 sm:pt-6 pb-3">
        <span className="font-mono text-xs sm:text-sm font-bold tracking-[0.1em] text-df-red">
          {card.index} / {card.tag}
        </span>
      </div>

      {/* Content */}
      <div className="px-5 sm:px-6 flex-1 flex flex-col">
        <h3 className="text-xl md:text-2xl font-bold text-df-black mb-3 sm:mb-4">
          {card.headline}
        </h3>
        <p className="font-body text-sm sm:text-base text-df-black/60 leading-relaxed mb-6 sm:mb-8">
          {card.body}
        </p>
      </div>

      {/* Action button — pinned to bottom */}
      <div className="px-5 sm:px-6 pb-5 sm:pb-6 mt-auto">
        <button
          onClick={handleClick}
          className="w-full px-4 py-3 sm:py-3.5 border-brutal-thin bg-df-white text-df-black font-mono text-xs sm:text-sm font-bold tracking-[0.06em] transition-all duration-100 hover:bg-df-black hover:text-df-white hover:shadow-none active:translate-x-[2px] active:translate-y-[2px]"
        >
          [ LAUNCH TOOL → ]
        </button>
      </div>
    </div>
  );
}

export default function Home() {
  return (
    <main className="relative w-full overflow-x-hidden">
      <Helmet>
        <title>DriveFetch — Find the Right Used Car in Pakistan, Powered by AI</title>
        <meta name="description" content="Find the perfect used car in Pakistan with DriveFetch. AI-powered search across PakWheels, OLX, Drive.pk, and Gari.pk." />
        <link rel="canonical" href="https://carfinderproject.vercel.app/" />
      </Helmet>

      {/* Scroll-Linked SVG Background (Framer Motion) */}
      <DynamicBackground />

      {/* ═══════════════════════════════════════════════
          SECTION 1 — HERO
          Pure landing. Massive fluid typography.
          No search bar. No CTAs. Just the statement.
          ═══════════════════════════════════════════════ */}
      <section
        id="hero"
        className="relative z-10 min-h-screen flex items-center justify-center px-5 sm:px-8 lg:px-12"
      >
        {/* System diagnostic tags */}
        <SystemTags />

        {/* Hero Content */}
        <div className="w-full max-w-[1400px] mx-auto">
          <h1 className="text-4xl sm:text-6xl md:text-7xl lg:text-[5.5rem] leading-[0.95] tracking-tight font-black text-df-black">
            <span className="block">FIND THE RIGHT CAR.</span>
            <span className="block">
              <span className="bg-[#E5202E] text-white px-2 py-1 mx-1 inline-block">SKIP</span>
              {' '}THE WRONG ONES.
            </span>
          </h1>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════
          SECTION 2 — GATEWAY CTAs
          3 mission cards: Direct Search, AI Matchmaker, Assistant Chat
          ═══════════════════════════════════════════════ */}
      <section id="gateway" className="relative z-10 min-h-screen py-24 sm:py-32 px-5 sm:px-8 lg:px-12">
        <div className="w-full max-w-[1400px] mx-auto">

          {/* Section Header */}
          <div className="border-t-2 border-df-black pt-6 mb-16 sm:mb-20">
            <span className="font-mono text-xs sm:text-sm font-bold tracking-[0.08em] text-df-black/50">
              // SECTION 02: CHOOSE YOUR MISSION
            </span>
          </div>

          {/* Gateway Cards Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 lg:gap-8">
            {GATEWAY_CARDS.map((card) => (
              <GatewayCard key={card.index} card={card} />
            ))}
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════
          SECTION 3 — INTELLIGENCE ENGINE & MARKET COVERAGE
          Left: AI Risk Terminal. Right: Platform coverage pills.
          ═══════════════════════════════════════════════ */}
      <section id="engine" className="relative z-10 min-h-screen py-24 sm:py-32 px-5 sm:px-8 lg:px-12">
        <div className="w-full max-w-[1400px] mx-auto">

          {/* Section Header */}
          <div className="border-t-2 border-df-black pt-6 mb-16 sm:mb-20">
            <span className="font-mono text-xs sm:text-sm font-bold tracking-[0.08em] text-df-black/50">
              // SECTION 03: INTELLIGENCE ENGINE & COVERAGE
            </span>
          </div>

          {/* Asymmetric Two-Column Layout */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12 items-start">

            {/* ── LEFT COLUMN: Risk Detection Terminal ── */}
            <div className="lg:col-span-7">
              <div className="bg-df-white border-brutal shadow-[6px_6px_0px_0px_#000000]">

                {/* Terminal Top Bar */}
                <div className="bg-df-grey px-4 sm:px-5 py-3 border-b border-df-black flex items-center justify-between">
                  <span className="font-mono text-[10px] sm:text-xs font-bold tracking-[0.08em] text-df-black/60">
                    [ SYS_LOG // RISK_DETECTOR_V2 ]
                  </span>
                  <div className="flex gap-1.5">
                    <span className="w-2.5 h-2.5 bg-df-black/15 border border-df-black/20" />
                    <span className="w-2.5 h-2.5 bg-df-black/15 border border-df-black/20" />
                    <span className="w-2.5 h-2.5 bg-df-black/15 border border-df-black/20" />
                  </div>
                </div>

                {/* Terminal Body */}
                <div className="px-4 sm:px-5 py-5 sm:py-6 space-y-4 font-mono text-xs sm:text-sm leading-relaxed">
                  <div>
                    <span className="text-df-black/40 select-none">{'>'} </span>
                    <span className="text-df-black/70">INIT: </span>
                    <span className="text-df-black">SCRAPE_REQUEST // PLATFORM: PAKWHEELS</span>
                  </div>
                  <div>
                    <span className="text-df-black/40 select-none">{'>'} </span>
                    <span className="text-df-black/70">EXTRACT: </span>
                    <span className="text-df-black">2017 Honda Civic Oriel | 85,000 km | Rs. 5,200,000</span>
                  </div>
                  <div className="border-t border-dashed border-df-black/10" />
                  <div>
                    <span className="text-df-black/40 select-none">{'>'} </span>
                    <span className="text-df-black/70">LLM_EVAL: </span>
                    <span className="text-df-black">Parsing unstructured seller description...</span>
                  </div>
                  <div>
                    <span className="text-df-black/40 select-none">{'>'} </span>
                    <span className="text-df-black/70">TARGET_TEXT: </span>
                    <span className="text-df-black">"Bumper to bumper genuine, just minor shower on left side for fresh look."</span>
                  </div>
                  <div>
                    <span className="text-df-black/40 select-none">{'>'} </span>
                    <span className="text-df-black/70">CONTRADICTION_DETECTED: </span>
                    <span className="text-df-black">"Genuine" vs "Minor Shower"</span>
                  </div>
                  <div className="border-t border-dashed border-df-black/10" />
                  <div>
                    <span className="text-df-black/40 select-none">{'>'} </span>
                    <span className="text-df-black/70">ALERT: </span>
                    <span className="inline-block bg-[#E5202E] text-white px-1.5 py-0.5 font-bold tracking-[0.06em] mr-1">
                      [RISK_FLAG: REPAINT_DETECTED]
                    </span>
                    <span className="text-df-black/50">(Confidence: 98%)</span>
                  </div>
                  <div>
                    <span className="text-df-black/40 select-none">{'>'} </span>
                    <span className="text-df-black/70">VERDICT: </span>
                    <span className="text-df-black">Seller language contradicts vehicle condition. Proceed with caution.</span>
                  </div>
                  <div className="pt-2">
                    <span className="text-df-black/40 select-none">{'>'} </span>
                    <span className="inline-block w-2 h-4 bg-df-black/70 animate-pulse" />
                  </div>
                </div>
              </div>

              {/* Terminal footnote */}
              <div className="mt-4 font-mono text-[10px] sm:text-xs text-df-black/25 tracking-[0.06em]">
                [LOG_STREAM: LIVE] — 30+ heuristic signals per listing
              </div>
            </div>

            {/* ── RIGHT COLUMN: Market Coverage & Trust ── */}
            <div className="lg:col-span-5 flex flex-col gap-8 sm:gap-10">

              {/* Headline */}
              <h2 className="text-display-lg text-df-black leading-[0.95]">
                SCANNING EVERY MAJOR PLATFORM IN PAKISTAN.
              </h2>

              {/* Platform Coverage Pills */}
              <div className="flex flex-wrap gap-3">
                {['PAKWHEELS', 'OLX PAKISTAN', 'GARI.PK', 'DRIVE.PK'].map((platform) => (
                  <span
                    key={platform}
                    className="px-4 sm:px-5 py-2.5 sm:py-3 border-brutal-thin bg-df-white text-df-black font-mono text-xs sm:text-sm font-bold tracking-[0.06em] cursor-default select-none transition-all duration-[50ms] hover:bg-df-black hover:text-df-white"
                  >
                    [ {platform} ]
                  </span>
                ))}
              </div>

              {/* Live Stats Readout */}
              <div className="border-t border-df-black/15 pt-5">
                <div className="font-mono text-[10px] sm:text-xs text-df-black/40 tracking-[0.05em] space-y-1.5">
                  <div className="flex items-center gap-2">
                    <span className="w-1.5 h-1.5 bg-df-red inline-block" />
                    <span>30+ Risk Signals Detected Per Listing</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-1.5 h-1.5 bg-df-red inline-block" />
                    <span>~0.8s Average Query Speed</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-1.5 h-1.5 bg-df-black/20 inline-block" />
                    <span>Cross-Platform Deduplication Active</span>
                  </div>
                </div>
              </div>

              {/* Subtext tag */}
              <div className="font-mono text-[10px] text-df-black/15 tracking-[0.08em]">
                [ENGINE_STATUS: OPERATIONAL] — [UPTIME: 99.7%]
              </div>
            </div>

          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════
          SECTION 4 — COMMAND CONSOLE
          The final action. Massive search bar + filters.
          ═══════════════════════════════════════════════ */}
      <CommandConsoleSection />

      {/* ═══════════════════════════════════════════════
          FOOTER — Neo-Brutalist
          ═══════════════════════════════════════════════ */}
      <BrutalistFooter />
    </main>
  );
}

/* ═══════════════════════════════════════════════════════
   SECTION 4 — COMMAND CONSOLE (extracted component)
   ═══════════════════════════════════════════════════════ */
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
    if (e.key === 'Enter') handleSearch();
  };

  return (
    <section id="console" className="relative z-10 py-24 sm:py-32 px-5 sm:px-8 lg:px-12">
      <div className="w-full max-w-[1400px] mx-auto">

        {/* Section Header */}
        <div className="border-t-2 border-df-black pt-6 mb-16 sm:mb-20">
          <span className="font-mono text-xs sm:text-sm font-bold tracking-[0.08em] text-df-black/50">
            // SECTION 04: EXECUTE SEARCH
          </span>
        </div>

        {/* ── THE COMMAND CONSOLE ── */}
        <div className="mb-10 sm:mb-14">

          {/* Search Bar Container */}
          <div className="bg-df-white border-brutal shadow-[8px_8px_0px_#000000] flex flex-col sm:flex-row focus-within:ring-2 focus-within:ring-[#E5202E] focus-within:border-[#E5202E]">

            {/* Input Area */}
            <div className="flex items-center flex-1 px-4 sm:px-6 py-4 sm:py-5 gap-3 sm:gap-4">
              {/* Search Icon */}
              <svg
                className="w-5 h-5 sm:w-6 sm:h-6 text-df-black/30 shrink-0"
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
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Honda Civic in Lahore under 50 Lakhs..."
                className="flex-1 bg-transparent font-mono text-sm sm:text-base text-df-black placeholder:text-df-black/25 outline-none border-none min-w-0"
              />
            </div>

            {/* Execute Button */}
            <button
              id="console-execute-btn"
              onClick={() => handleSearch()}
              disabled={isLoading}
              className="px-6 sm:px-8 py-4 sm:py-5 bg-df-red text-df-white font-mono text-xs sm:text-sm font-bold tracking-[0.08em] border-t sm:border-t-0 sm:border-l border-df-black whitespace-nowrap transition-none hover:bg-[#C41A25] active:translate-x-[1px] active:translate-y-[1px] disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isLoading ? '[ SEARCHING... ]' : '[ EXECUTE SEARCH ]'}
            </button>
          </div>

          {/* Console footnote */}
          <div className="mt-3 font-mono text-[10px] text-df-black/20 tracking-[0.06em]">
            [INPUT_MODE: NATURAL_LANGUAGE] — [BACKEND: AI_PARSE + MULTI_SCRAPE]
          </div>
        </div>

        {/* ── SEARCH RESULTS AREA ── */}
        {(isLoading || error || results) && (
          <div className="mb-16 sm:mb-20">
            {isLoading && (
              <div className="border-brutal-thin bg-df-grey px-6 py-8 flex items-center justify-center gap-3">
                <span className="inline-block w-3 h-3 bg-df-red animate-pulse" />
                <span className="font-mono text-xs sm:text-sm text-df-black/50 tracking-[0.06em]">
                  [FETCHING_RESULTS] — Scanning platforms...
                </span>
              </div>
            )}
            {error && (
              <div className="border-brutal-thin bg-df-white px-6 py-5 flex items-center gap-3">
                <span className="inline-block w-2.5 h-2.5 bg-df-red" />
                <span className="font-mono text-xs sm:text-sm text-df-black/60">{error}</span>
              </div>
            )}
            {results && results.length === 0 && !isLoading && (
              <div className="border-brutal-thin bg-df-grey px-6 py-8 text-center">
                <span className="font-mono text-xs sm:text-sm text-df-black/40 tracking-[0.06em]">
                  [NO_RESULTS] — Try broadening your search or adjusting your budget.
                </span>
              </div>
            )}
            {results && results.length > 0 && !isLoading && (
              <div className="space-y-3">
                <div className="font-mono text-[10px] sm:text-xs font-bold tracking-[0.1em] text-df-black/30 mb-4">
                  [{results.length} RESULT{results.length !== 1 ? 'S' : ''} FOUND]:
                </div>
                {results.map((car, i) => (
                  <div key={car.id || i} className="border-brutal-thin bg-df-white px-5 py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-df-grey transition-colors duration-[50ms]">
                    <div className="flex-1 min-w-0">
                      <div className="font-mono text-xs sm:text-sm font-bold text-df-black truncate">
                        {car.title}
                      </div>
                      <div className="font-mono text-[10px] sm:text-xs text-df-black/40 mt-1">
                        {car.platform && <span className="mr-3">[{car.platform.toUpperCase()}]</span>}
                        {car.city && <span className="mr-3">{car.city}</span>}
                        {car.year && <span>{car.year}</span>}
                      </div>
                    </div>
                    <div className="flex items-center gap-4 shrink-0">
                      <span className="font-mono text-sm sm:text-base font-bold text-df-black">
                        {typeof car.price === 'number'
                          ? `PKR ${(car.price / 100000).toFixed(1)} Lacs`
                          : car.price}
                      </span>
                      {car.url && (
                        <a
                          href={car.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="px-3 py-1.5 border-brutal-thin font-mono text-[10px] font-bold tracking-[0.06em] text-df-black hover:bg-df-black hover:text-df-white transition-all duration-[50ms]"
                        >
                          [ VIEW → ]
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── FINANCIAL TOOLS TEASER ── */}
        <div>
          <div className="font-mono text-[10px] sm:text-xs font-bold tracking-[0.1em] text-df-black/30 mb-4">
            FINANCIAL TOOLS:
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-5">
            {FINANCIAL_TOOLS.map((tool) => (
              <button
                key={tool.label}
                onClick={() => navigate('/calculators')}
                className="group bg-df-grey border-brutal-thin px-5 py-5 sm:py-6 text-left flex flex-col gap-2.5 shadow-[3px_3px_0px_0px_#000000] hover:shadow-[5px_5px_0px_0px_#000000] transition-shadow duration-100 hover:bg-df-black"
              >
                <span className="font-mono text-xs sm:text-sm font-bold tracking-[0.06em] text-df-black group-hover:text-df-white transition-colors duration-[50ms]">
                  [ {tool.label} ]
                </span>
                <span className="font-body text-xs text-df-black/50 leading-relaxed group-hover:text-df-white/60 transition-colors duration-[50ms]">
                  {tool.desc}
                </span>
              </button>
            ))}
          </div>
        </div>

      </div>
    </section>
  );
}

/* ═══════════════════════════════════════════════════════
   FOOTER — Neo-Brutalist
   ═══════════════════════════════════════════════════════ */
function BrutalistFooter() {
  return (
    <footer className="relative z-10 border-t-2 border-df-black bg-df-white">
      <div className="w-full max-w-[1400px] mx-auto px-5 sm:px-8 lg:px-12 py-6 sm:py-8">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-5 md:gap-4">

          {/* Left — Copyright */}
          <div className="font-mono text-[10px] sm:text-xs font-bold tracking-[0.06em] text-df-black/50">
            [ DRIVEFETCH // ALL RIGHTS RESERVED ]
          </div>

          {/* Center — Links */}
          <nav className="flex flex-wrap items-center gap-x-1 gap-y-2">
            {[
              { label: 'PRIVACY POLICY', href: '#' },
              { label: 'TERMS', href: '#' },
              { label: 'GITHUB', href: 'https://github.com' },
              { label: 'CONTACT', href: '#' },
            ].map((link, i, arr) => (
              <span key={link.label} className="flex items-center">
                <a
                  href={link.href}
                  target={link.href.startsWith('http') ? '_blank' : undefined}
                  rel={link.href.startsWith('http') ? 'noopener noreferrer' : undefined}
                  className="font-mono text-[10px] sm:text-xs font-bold tracking-[0.06em] text-black bg-transparent hover:bg-black hover:text-white px-2 py-1 transition-colors"
                >
                  {link.label}
                </a>
                {i < arr.length - 1 && (
                  <span className="text-df-black/15 font-light mx-0.5 select-none">|</span>
                )}
              </span>
            ))}
          </nav>

          {/* Right — Build version */}
          <div className="font-mono text-[10px] sm:text-xs tracking-[0.06em] text-df-black/25">
            BUILD_VER: 2.0.4_BRUTALIST
          </div>

        </div>
      </div>
    </footer>
  );
}
