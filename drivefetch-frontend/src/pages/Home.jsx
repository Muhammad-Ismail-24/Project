import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import SEO from '../components/SEO';
import { homeSchema } from '../config/seoSchemas';
import { searchCars, searchCarsStream } from '../utils/api';
import CarResultCard from '../components/CarResultCard';
import FeatureErrorBoundary from '../components/FeatureErrorBoundary';
import Plate from '../components/ui/Plate';
import SplitText from '../components/motion/SplitText';
import useCountUp from '../components/motion/useCountUp';
import { useScrollTo } from '../components/motion/SmoothScroll';
import { HeroSearchInput, CtaCard, AdScanDemo, MatchDemo, ChatDemo } from '../components/home/HomeParts';
import { formatLac, toRupees, stripEmoji } from '../utils/cityMeta';
import { VehicleTaxAgent } from '../agents/calculators/VehicleTaxAgent';
import { FuelCostAgent } from '../agents/calculators/FuelCostAgent';

const SOURCES = ['PakWheels', 'OLX', 'Gari.pk', 'Drive.pk', 'FameWheels', 'AutoDeals', 'WiseWheels'];
const PLATES = [['PUNJAB', 'LHR 2019'], ['ISLAMABAD', 'ISB 2021'], ['SINDH', 'KHI 2018'], ['PUNJAB', 'RWP 2020'], ['PUNJAB', 'FSD 2017'], ['PUNJAB', 'MUX 2022'], ['KPK', 'PEW 2016']];

const SORTS = [
  { id: 'best', label: 'Best match' },
  { id: 'price', label: 'Lowest price' },
  { id: 'year', label: 'Newest' },
];

const FEATURES = [
  ['Condition scanner', 'If a seller says “genuine” but mentions a “shower”, the ad gets flagged, with the exact words shown.'],
  ['Fair price check', 'Every car is compared with similar live ads, so you know when an asking price is high.'],
  ['Risk detection', 'Duplicate files, odd mileage and pressure tactics are caught before you call the seller.'],
];

/** Worked example for the cost band, calculated with the same engine as /calculators. */
function useCostExample() {
  return useMemo(() => {
    const price = 4750000;
    const tax = VehicleTaxAgent.calculate({ province: 'PUNJAB', engineCc: 1800, invoiceVal: price, vehicleAge: 6, isFiler: true, isTransfer: true, paymentDate: new Date() });
    const fuel = FuelCostAgent.calculate({ cc: 1800, dailyKm: 40 });
    const total = price + tax.totalPayable + fuel.monthlyCost * 12;
    return { total, priceLac: formatLac(price) };
  }, []);
}

/** Endless row of plates. Two copies side by side so the loop is seamless. */
function Marquee({ items, reverse = false, duration = 40 }) {
  return (
    <div className="df-marquee overflow-hidden" aria-hidden="true">
      <div className="df-marquee-track flex w-max" style={{ '--marquee-dur': `${duration}s`, animationDirection: reverse ? 'reverse' : 'normal' }}>
        {[0, 1].map((copy) => (
          <div key={copy} className="flex gap-4 sm:gap-6 pr-4 sm:pr-6 py-2">
            {items.map(([top, main], i) => <Plate key={`${copy}-${i}`} top={top} main={main} size="lg" />)}
          </div>
        ))}
      </div>
    </div>
  );
}

function SectionLabel({ children, className = '' }) {
  return (
    <span data-reveal="fade" className={`flex items-center gap-3 font-mono text-[13px] font-semibold tracking-[0.08em] ${className}`}>
      <span data-reveal="line" className="w-8 h-[2px] bg-df-red" />
      {children}
    </span>
  );
}

export default function Home() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialQ = searchParams.get('q') || '';
  const [query, setQuery] = useState(initialQ);
  const [phase, setPhase] = useState('idle'); // idle | searching | done | error
  const [statusLine, setStatusLine] = useState('');
  const [results, setResults] = useState([]);
  const [error, setError] = useState('');
  const [lastQuery, setLastQuery] = useState('');
  const [sort, setSort] = useState('best');
  const requestId = useRef(0);
  const inputRef = useRef(null);
  const cost = useCostExample();
  const [costRef, costNow] = useCountUp(cost.total, { duration: 1800 });
  const scrollTo = useScrollTo();

  const runSearch = useCallback(async (raw) => {
    const q = String(raw || '').trim();
    if (!q) {
      inputRef.current?.focus();
      return;
    }
    const id = ++requestId.current;
    setPhase('searching');
    setStatusLine('Reading your search…');
    setResults([]);
    setError('');
    setLastQuery(q);
    setSort('best');

    let finished = false;
    try {
      await searchCarsStream(q, (msg) => {
        if (id !== requestId.current || !msg || typeof msg !== 'object') return;
        if (msg.error) {
          finished = true;
          setError(String(msg.error));
          setPhase('error');
          return;
        }
        if (msg.status === 'done') {
          finished = true;
          setResults(Array.isArray(msg.results) ? msg.results : []);
          setPhase('done');
          return;
        }
        if (msg.status) setStatusLine(stripEmoji(msg.status));
      });
      if (!finished && id === requestId.current) {
        // Stream ended without a result (old backend or proxy buffering): fall back to the plain endpoint.
        const data = await searchCars(q);
        if (id !== requestId.current) return;
        setResults(Array.isArray(data) ? data : []);
        setPhase('done');
      }
    } catch (err) {
      if (id !== requestId.current) return;
      console.error('Search failed:', err instanceof Error ? err.message : 'Unknown error');
      setError('Search failed. Check your connection and try again.');
      setPhase('error');
    }
  }, []);

  // Run the search in the URL (?q=) on load, so searches can be shared.
  useEffect(() => {
    if (initialQ) runSearch(initialQ);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Bring the results into view when a search finishes.
  useEffect(() => {
    if (phase !== 'done') return undefined;
    const t = setTimeout(() => scrollTo('#results', { offset: -72 }), 250);
    return () => clearTimeout(t);
  }, [phase, scrollTo]);

  const onSubmit = (e) => {
    e.preventDefault();
    const q = query.trim();
    if (q) setSearchParams({ q }, { replace: false });
    runSearch(q);
  };

  const focusSearch = () => {
    scrollTo(0);
    setTimeout(() => inputRef.current?.focus({ preventScroll: true }), 700);
  };

  const sorted = useMemo(() => {
    const list = [...results];
    if (sort === 'price') list.sort((a, b) => (toRupees(a.price) ?? Infinity) - (toRupees(b.price) ?? Infinity));
    if (sort === 'year') list.sort((a, b) => (parseInt(b.year, 10) || 0) - (parseInt(a.year, 10) || 0));
    return list;
  }, [results, sort]);

  return (
    <div className="w-full">
      <SEO
        path="/"
        description="Find the right used car in Pakistan. DriveFetch searches PakWheels, OLX, Gari.pk and four more sites at once, then reads every ad for resprays, duplicate files and overpricing."
        schema={homeSchema}
      />

      {/* ═══ HERO: one headline, one search box ═══ */}
      <section id="search" className="relative bg-df-red text-white overflow-hidden">
        <div className="px-5 sm:px-10 pt-12 sm:pt-16 pb-8 sm:pb-10 min-h-[calc(100svh-64px)] sm:min-h-[calc(100svh-68px)] flex flex-col">
          <span data-reveal="fade" className="font-mono text-[13px] font-semibold tracking-[0.08em]">USED CARS · PAKISTAN · 7 SITES</span>
          <h1 className="df-display mt-6 sm:mt-8 text-[length:clamp(58px,10.2vw,172px)]" data-parallax="0.08">
            <SplitText text="Find the right car." className="block" />
            <SplitText text="Skip the wrong ones." className="block text-black" start={4} />
          </h1>

          <div className="mt-auto pt-10 flex flex-wrap items-end justify-between gap-8">
            <form onSubmit={onSubmit} role="search" data-reveal style={{ '--rd': '650ms' }} className="w-full max-w-[920px] flex flex-col gap-4">
              <div className="flex bg-white shadow-[0_24px_60px_-20px_rgba(0,0,0,.45)]">
                <label htmlFor="home-q" className="sr-only">Search used cars</label>
                <HeroSearchInput ref={inputRef} value={query} onChange={(e) => setQuery(e.target.value)} />
                <button
                  type="submit"
                  disabled={phase === 'searching'}
                  className="df-btn h-16 sm:h-[72px] px-6 sm:px-9 bg-black text-white text-sm sm:text-base tracking-[0.08em] hover:text-black disabled:opacity-70"
                  style={{ '--df-fill': '#FFFFFF' }}
                >
                  {phase === 'searching' ? 'SEARCHING…' : 'SEARCH'}
                </button>
              </div>

              <div aria-live="polite" className="min-h-[28px] text-[15px]">
                {phase === 'idle' && (
                  <span className="text-white/85">Type it like you’d say it. We search seven sites and read every ad.</span>
                )}
                {phase === 'searching' && (
                  <span className="flex items-center gap-4 animate-df-fade-up">
                    <span aria-hidden="true" className="w-28 h-1.5 bg-white/25 df-road-white" />
                    <span className="font-mono text-[13px] font-semibold truncate">{statusLine}</span>
                  </span>
                )}
                {phase === 'error' && (
                  <span role="alert" className="flex flex-wrap items-center gap-3 animate-df-fade-up">
                    <strong>Search stalled.</strong> <span className="text-white/85">{error}</span>
                    <button type="button" onClick={() => runSearch(lastQuery)} className="df-btn h-10 px-4 bg-black text-white hover:text-black" style={{ '--df-fill': '#FFF' }}>Try again</button>
                  </span>
                )}
                {phase === 'done' && (
                  <span className="flex flex-wrap items-center gap-3 animate-df-fade-up">
                    <strong>{results.length} {results.length === 1 ? 'match' : 'matches'} for “{lastQuery}”</strong>
                    <button type="button" onClick={() => scrollTo('#results', { offset: -72 })} className="df-link font-bold">See them ↓</button>
                  </span>
                )}
              </div>
            </form>

            <button
              type="button"
              onClick={() => scrollTo('#ways', { offset: -40 })}
              data-reveal="fade"
              style={{ '--rd': '1100ms' }}
              className="hidden md:flex flex-col items-center gap-3 font-mono text-xs font-semibold tracking-[0.12em]"
            >
              SCROLL
              <span aria-hidden="true" className="relative block w-[2px] h-14 bg-white/25 overflow-hidden">
                <span className="absolute inset-0 bg-white df-scroll-cue" />
              </span>
            </button>
          </div>
        </div>
      </section>

      {/* ═══ RESULTS ═══ */}
      {phase === 'done' && (
        <section id="results" className="px-5 sm:px-10 pt-14 pb-20 scroll-mt-20">
          {results.length > 0 ? (
            <>
              <div className="flex flex-wrap items-end justify-between gap-4 pb-4 border-b-4 border-black dark:border-zinc-50">
                <h2 className="df-display text-[length:clamp(40px,5vw,72px)]"><SplitText text={`${results.length} listings`} /></h2>
                <div className="flex flex-wrap items-center gap-2" data-reveal="fade">
                  <div role="group" aria-label="Sort results" className="flex">
                    {SORTS.map((s) => (
                      <button
                        key={s.id}
                        type="button"
                        aria-pressed={sort === s.id}
                        onClick={() => setSort(s.id)}
                        className={`h-11 px-4 -ml-px first:ml-0 border border-black dark:border-zinc-700 text-sm font-bold transition-colors duration-300 ${sort === s.id ? 'bg-black text-white dark:bg-zinc-50 dark:text-black' : 'hover:bg-black/5 dark:hover:bg-white/10'}`}
                      >
                        {s.label}
                      </button>
                    ))}
                  </div>
                  <button type="button" onClick={focusSearch} className="df-btn-outline">New search</button>
                </div>
              </div>
              <FeatureErrorBoundary featureName="Search results">
                <div className="flex flex-col">
                  {sorted.map((car, i) => (
                    <div key={car.id || i} id={car.id ? `car-${car.id}` : undefined} data-reveal style={{ '--rd': `${Math.min(i, 5) * 80}ms` }} className="scroll-mt-24">
                      <CarResultCard car={car} userQuery={lastQuery} />
                    </div>
                  ))}
                </div>
              </FeatureErrorBoundary>
            </>
          ) : (
            <div className="flex flex-col gap-4 max-w-[640px]">
              <h2 className="df-display text-[length:clamp(44px,6vw,88px)]"><SplitText text="Zero matches." /></h2>
              <p data-reveal className="df-muted text-lg">Nothing live fits “{lastQuery}”. Try a bigger budget or another city, or describe what you need and let the Matchmaker pick models for you.</p>
              <div data-reveal className="flex flex-wrap gap-2">
                <Link to="/recommend" className="df-btn-red h-12 px-5">Open the Matchmaker</Link>
                <button type="button" onClick={focusSearch} className="df-btn-outline h-12 px-5">Edit search</button>
              </div>
            </div>
          )}
        </section>
      )}

      {/* ═══ TWO WAYS IN ═══ */}
      <section id="ways" className="px-5 sm:px-10 py-20 sm:py-28 scroll-mt-10">
        <div className="flex flex-wrap items-end justify-between gap-6 mb-10 sm:mb-14">
          <div className="flex flex-col gap-5">
            <SectionLabel>START HERE</SectionLabel>
            <h2 className="df-display text-[length:clamp(48px,6.4vw,104px)]"><SplitText text="Two ways to find it." /></h2>
          </div>
          <p data-reveal className="max-w-[400px] text-lg leading-relaxed df-muted">Know the car you want? Search for it. Not sure yet? Describe your life and let the Matchmaker choose.</p>
        </div>
        <div className="grid md:grid-cols-2 gap-4 sm:gap-5" data-stagger>
          <CtaCard
            n="01"
            kicker="I KNOW WHAT I WANT"
            title="Direct search"
            desc="Make, model, city, budget. Typed like a sentence, searched across seven sites, every ad checked."
            action="Start searching"
            onClick={focusSearch}
            plate={<Plate top="PUNJAB" main="LHR 2019" size="sm" />}
          />
          <CtaCard
            n="02"
            kicker="HELP ME CHOOSE"
            title="AI Matchmaker"
            desc="Tell us your budget, family and commute. Get three models that fit, each with live ads."
            action="Open the Matchmaker"
            to="/recommend"
            plate={<Plate top="MATCHES" main="3 MODELS" size="sm" />}
          />
        </div>
      </section>

      {/* ═══ DIRECT SEARCH ═══ */}
      <section className="bg-df-grey dark:bg-black border-y border-neutral-200 dark:border-zinc-800">
        <div className="px-5 sm:px-10 py-20 sm:py-28 grid gap-14 lg:gap-20 lg:grid-cols-2 items-center">
          <div className="flex flex-col gap-7">
            <SectionLabel>01 · DIRECT SEARCH</SectionLabel>
            <h2 className="df-display text-[length:clamp(48px,6vw,96px)]">
              <SplitText text="We read the ad." className="block" />
              <SplitText text="You read the verdict." className="block text-df-red" start={4} />
            </h2>
            <div className="flex flex-col" data-stagger>
              {FEATURES.map(([t, d], i) => (
                <div key={t} className={`grid grid-cols-[40px_minmax(0,1fr)] gap-4 py-5 border-t border-black dark:border-zinc-700 ${i === FEATURES.length - 1 ? 'border-b' : ''}`}>
                  <span className="font-mono text-sm font-semibold text-df-red-dark dark:text-df-red pt-1">0{i + 1}</span>
                  <span className="flex flex-col gap-1.5">
                    <strong className="text-[22px]">{t}</strong>
                    <span className="text-[17px] leading-relaxed df-muted">{d}</span>
                  </span>
                </div>
              ))}
            </div>
            <div data-reveal>
              <button type="button" onClick={focusSearch} className="df-btn-red h-14 px-7 text-base">Try a search</button>
            </div>
          </div>
          <AdScanDemo />
        </div>
      </section>

      {/* ═══ SOURCES ═══ */}
      <section className="py-20 sm:py-28 flex flex-col gap-12 overflow-hidden">
        <div className="px-5 sm:px-10 flex flex-wrap justify-between items-end gap-6">
          <div className="flex flex-col gap-5">
            <SectionLabel>WHERE WE LOOK</SectionLabel>
            <h2 className="df-display text-[length:clamp(48px,6vw,96px)]">
              <SplitText text="Seven sites," className="block" />
              <SplitText text="one search." className="block text-df-red" start={2} />
            </h2>
          </div>
          <p data-reveal className="max-w-[420px] text-lg df-muted leading-relaxed">Searched live when you press search. We link back to every original ad and never host the seller’s photos or text as our own.</p>
        </div>
        <div data-reveal="fade" className="flex flex-col gap-5 -rotate-1">
          <Marquee items={SOURCES.map((s) => ['SOURCE', s.toUpperCase()])} duration={36} />
          <Marquee items={PLATES} reverse duration={44} />
        </div>
      </section>

      {/* ═══ MATCHMAKER ═══ */}
      <section className="bg-black text-white dark:border-y dark:border-zinc-800">
        <div className="px-5 sm:px-10 py-20 sm:py-28 grid gap-14 lg:gap-20 lg:grid-cols-2 items-center">
          <div className="flex flex-col gap-7">
            <SectionLabel className="text-white">02 · AI MATCHMAKER</SectionLabel>
            <h2 className="df-display text-[length:clamp(48px,6vw,96px)]">
              <SplitText text="Not sure what to buy?" className="block" />
              <SplitText text="Describe your life." className="block text-df-red" start={5} />
            </h2>
            <p data-reveal className="max-w-[480px] text-lg leading-relaxed text-zinc-300">Budget, city, family, commute, fuel. Write it like you’d tell a friend. The Matchmaker picks three models that fit, explains why, and finds live ads for each.</p>
            <div data-reveal>
              <Link to="/recommend" className="df-btn-red h-14 px-7 text-base hover:text-black" style={{ '--df-fill': '#FFF' }}>
                Open the Matchmaker →
              </Link>
            </div>
          </div>
          <MatchDemo />
        </div>
      </section>

      {/* ═══ CHAT ═══ */}
      <section className="bg-df-grey dark:bg-df-night">
        <div className="px-5 sm:px-10 py-20 sm:py-28 grid gap-14 lg:gap-20 lg:grid-cols-2 items-center">
          <div className="lg:order-2 flex flex-col gap-7">
            <SectionLabel>03 · ASSISTANT CHAT</SectionLabel>
            <h2 className="df-display text-[length:clamp(48px,6vw,96px)]">
              <SplitText text="Ask like you’d ask" className="block" />
              <SplitText text="your ustaad." className="block text-df-red" start={4} />
            </h2>
            <p data-reveal className="max-w-[480px] text-lg leading-relaxed df-muted">Fuel averages, auction sheets, transfer rules, which variant to pick. Ask in plain words, any time, without being sold to.</p>
            <div data-reveal>
              <Link to="/chat" className="df-btn-ink h-14 px-7 text-base">Start a chat →</Link>
            </div>
          </div>
          <div className="lg:order-1"><ChatDemo /></div>
        </div>
      </section>

      {/* ═══ CALCULATORS ═══ */}
      <section className="bg-df-red text-white overflow-hidden">
        <div className="px-5 sm:px-10 py-16 sm:py-20 flex flex-wrap items-end justify-between gap-8">
          <div className="flex flex-col gap-3">
            <SectionLabel className="text-white [&>span]:bg-white">04 · CALCULATORS</SectionLabel>
            <span data-reveal className="text-lg font-bold mt-2">A {cost.priceLac} 2019 Civic in Punjab costs about</span>
            <span ref={costRef} data-reveal="clip" className="df-display text-[length:clamp(56px,9vw,152px)] tabular-nums">
              {formatLac(costNow)} <span className="text-black">in year one.</span>
            </span>
            <span data-reveal className="text-[15px] text-white/85">Transfer, token tax and 40 km of petrol a day, at this year’s rates.</span>
          </div>
          <div data-reveal>
            <Link to="/calculators" className="df-btn h-14 px-7 bg-black text-white text-base hover:text-black" style={{ '--df-fill': '#FFF' }}>
              Open the calculators →
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
