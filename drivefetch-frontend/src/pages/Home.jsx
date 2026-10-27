import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import SEO from '../components/SEO';
import { homeSchema } from '../config/seoSchemas';
import { searchCars, searchCarsStream } from '../utils/api';
import CarResultCard from '../components/CarResultCard';
import FeatureErrorBoundary from '../components/FeatureErrorBoundary';
import Plate from '../components/ui/Plate';
import { RoadLoader } from '../components/ui/Loaders';
import { cityMeta, formatLac, toRupees, stripEmoji } from '../utils/cityMeta';
import { VehicleTaxAgent } from '../agents/calculators/VehicleTaxAgent';
import { FuelCostAgent } from '../agents/calculators/FuelCostAgent';

const SOURCES = ['PakWheels', 'OLX', 'Gari.pk', 'Drive.pk', 'FameWheels', 'AutoDeals', 'WiseWheels'];

const TOOLS = [
  { n: '01', name: 'Direct search', desc: 'Make, model, city, budget. Typed like a sentence.', to: '#search' },
  { n: '02', name: 'AI Matchmaker', desc: 'Describe your family and commute. Get three models and live ads for each.', to: '/recommend' },
  { n: '03', name: 'Assistant chat', desc: 'Fuel averages, auction sheets, transfer rules.', to: '/chat' },
  { n: '04', name: 'Calculators', desc: 'Token tax, transfer fees and fuel, together.', to: '/calculators' },
];

const EXAMPLES = ['Civic 2018+ in Lahore under 50 lac', 'Corolla Karachi under 40 lac', 'Aqua 2016+ Islamabad'];

const SORTS = [
  { id: 'best', label: 'Best match' },
  { id: 'price', label: 'Lowest price' },
  { id: 'year', label: 'Newest' },
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

export default function Home() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialQ = searchParams.get('q') || '';
  const [query, setQuery] = useState(initialQ);
  const [phase, setPhase] = useState('idle'); // idle | searching | done | error
  const [statusLines, setStatusLines] = useState([]);
  const [results, setResults] = useState([]);
  const [error, setError] = useState('');
  const [lastQuery, setLastQuery] = useState('');
  const [sort, setSort] = useState('best');
  const requestId = useRef(0);
  const inputRef = useRef(null);
  const cost = useCostExample();

  const runSearch = useCallback(async (raw) => {
    const q = String(raw || '').trim();
    if (!q) {
      inputRef.current?.focus();
      return;
    }
    const id = ++requestId.current;
    setPhase('searching');
    setStatusLines(['Reading your search…']);
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
        if (msg.status) setStatusLines((prev) => [...prev.slice(-4), stripEmoji(msg.status)]);
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

  const onSubmit = (e) => {
    e.preventDefault();
    const q = query.trim();
    if (q) setSearchParams({ q }, { replace: false });
    runSearch(q);
  };

  const sorted = useMemo(() => {
    const list = [...results];
    if (sort === 'price') list.sort((a, b) => (toRupees(a.price) ?? Infinity) - (toRupees(b.price) ?? Infinity));
    if (sort === 'year') list.sort((a, b) => (parseInt(b.year, 10) || 0) - (parseInt(a.year, 10) || 0));
    return list;
  }, [results, sort]);

  const scrollToResults = (id) => {
    const el = document.getElementById(id ? `car-${id}` : 'results');
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div className="w-full">
      <SEO
        path="/"
        description="Find the right used car in Pakistan. DriveFetch searches PakWheels, OLX, Gari.pk and four more sites at once, then reads every ad for resprays, duplicate files and overpricing."
        schema={homeSchema}
      />

      {/* ═══ HERO ═══ */}
      <section className="flex flex-wrap">
        <div id="search" className="flex-[7_1_560px] min-w-0 bg-df-red text-white px-5 sm:px-10 pt-12 sm:pt-14 pb-10 flex flex-col gap-7 min-h-[560px] lg:min-h-[680px]">
          <div className="font-mono text-[13px] font-semibold tracking-[0.06em]">USED CARS · PAKISTAN · 7 SITES</div>
          <h1 className="df-display text-[length:clamp(60px,9vw,132px)]">
            <span className="block">Find the right car.</span>
            <span className="block text-black">Skip the wrong ones.</span>
          </h1>
          <form onSubmit={onSubmit} className="mt-auto flex flex-col gap-3" role="search">
            <div className="flex bg-white">
              <label htmlFor="home-q" className="sr-only">Search used cars</label>
              <input
                id="home-q"
                ref={inputRef}
                type="search"
                maxLength={200}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Civic, Lahore, under 50 lac"
                autoComplete="off"
                className="flex-1 min-w-0 h-16 sm:h-[68px] px-5 sm:px-6 bg-transparent text-black text-lg sm:text-[22px] font-medium outline-none placeholder:text-neutral-500"
              />
              <button
                type="submit"
                disabled={phase === 'searching'}
                className="h-16 sm:h-[68px] px-6 sm:px-8 bg-black text-white text-sm sm:text-base font-extrabold tracking-[0.06em] hover:bg-white hover:text-black hover:outline hover:outline-2 hover:outline-black disabled:opacity-70 transition-colors"
              >
                {phase === 'searching' ? 'SEARCHING…' : 'SEARCH'}
              </button>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-semibold">Try</span>
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  type="button"
                  onClick={() => { setQuery(ex); setSearchParams({ q: ex }); runSearch(ex); }}
                  className="h-9 px-3 border border-white/70 hover:bg-white hover:text-df-red font-semibold transition-colors"
                >
                  {ex}
                </button>
              ))}
            </div>
          </form>
          <div className="flex flex-wrap gap-x-7 gap-y-2 text-base font-semibold">
            <Link to="/recommend" className="underline underline-offset-4 hover:text-black">Not sure what to buy? Matchmaker →</Link>
            <Link to="/chat" className="underline underline-offset-4 hover:text-black">Got a question? Chat →</Link>
          </div>
        </div>

        <div className="flex-[5_1_420px] bg-df-grey dark:bg-black px-5 sm:px-10 py-10 flex flex-col min-w-0" aria-live="polite">
          {phase === 'idle' && (
            <>
              <div className="flex justify-between items-baseline pb-3.5 border-b border-neutral-300 dark:border-zinc-800">
                <span className="text-[15px] font-bold">Three ways in, plus the maths</span>
                <span className="font-mono text-xs df-muted">04 tools</span>
              </div>
              {TOOLS.map((tool, i) => {
                const inner = (
                  <>
                    <Plate top="TOOL" main={tool.n} size="md" />
                    <span className="flex flex-col gap-1 min-w-0">
                      <span className="text-lg font-extrabold">{tool.name}</span>
                      <span className="text-sm df-muted leading-snug">{tool.desc}</span>
                    </span>
                    <span aria-hidden="true" className="text-2xl transition-transform group-hover:translate-x-1">→</span>
                  </>
                );
                const cls = 'group grid grid-cols-[88px_minmax(0,1fr)_auto] gap-4 items-center py-4 border-b border-neutral-300 dark:border-zinc-800 hover:text-df-red animate-df-fade-up';
                return tool.to.startsWith('#') ? (
                  <button key={tool.n} type="button" style={{ animationDelay: `${i * 60}ms` }} onClick={() => inputRef.current?.focus()} className={`${cls} text-left`}>{inner}</button>
                ) : (
                  <Link key={tool.n} to={tool.to} style={{ animationDelay: `${i * 60}ms` }} className={cls}>{inner}</Link>
                );
              })}
            </>
          )}

          {phase === 'searching' && (
            <div className="flex flex-col gap-6 py-4">
              <span className="text-[15px] font-bold">Searching 7 sites for “{lastQuery}”</span>
              <RoadLoader className="w-full" />
              <ol className="flex flex-col gap-2 font-mono text-[13px]">
                {statusLines.map((line, i) => (
                  <li key={`${line}-${i}`} className={`animate-df-fade-up ${i === statusLines.length - 1 ? 'font-semibold' : 'df-muted'}`}>
                    {i === statusLines.length - 1 ? '› ' : '✓ '}{line}
                  </li>
                ))}
              </ol>
            </div>
          )}

          {phase === 'error' && (
            <div role="alert" className="flex flex-col gap-4 py-4">
              <span className="df-display text-5xl">Search stalled.</span>
              <p className="df-muted">{error}</p>
              <button type="button" onClick={() => runSearch(lastQuery)} className="df-btn-red self-start h-12 px-5">Try again</button>
            </div>
          )}

          {phase === 'done' && (
            <>
              <div className="flex justify-between items-baseline gap-4 pb-3.5 border-b border-neutral-300 dark:border-zinc-800">
                <span className="text-[15px] font-bold truncate">Matches for “{lastQuery}”</span>
                <span className="font-mono text-xs df-muted whitespace-nowrap">{results.length} found</span>
              </div>
              {results.length === 0 ? (
                <div className="flex flex-col gap-3 py-6">
                  <span className="df-display text-5xl">Zero matches.</span>
                  <p className="df-muted">Try a bigger budget, another city, or describe your needs to the Matchmaker.</p>
                  <Link to="/recommend" className="df-btn-ink self-start h-12 px-5">Open the Matchmaker</Link>
                </div>
              ) : (
                <>
                  {results.slice(0, 5).map((car, i) => {
                    const { region, code } = cityMeta(car.city);
                    return (
                      <button
                        key={car.id || i}
                        type="button"
                        onClick={() => scrollToResults(car.id)}
                        style={{ animationDelay: `${i * 60}ms` }}
                        className="grid grid-cols-[130px_minmax(0,1fr)_auto] gap-4 items-center py-4 border-b border-neutral-300 dark:border-zinc-800 text-left hover:text-df-red animate-df-fade-up"
                      >
                        <Plate top={region} main={`${code} ${car.year ?? ''}`.trim()} size="md" />
                        <span className="flex flex-col gap-1 min-w-0">
                          <span className="text-[16px] font-bold leading-snug line-clamp-2">{car.title}</span>
                          <span className="font-mono text-xs df-muted truncate">
                            {[car.mileage ? `${typeof car.mileage === 'number' ? car.mileage.toLocaleString('en-US') : car.mileage} km` : null, car.platform].filter(Boolean).join(' · ')}
                          </span>
                        </span>
                        <span className="text-2xl font-extrabold whitespace-nowrap">{formatLac(car.price)}</span>
                      </button>
                    );
                  })}
                  <button type="button" onClick={() => scrollToResults()} className="mt-4 self-start text-[15px] font-bold underline underline-offset-4 hover:text-df-red">
                    See all {results.length} below ↓
                  </button>
                </>
              )}
            </>
          )}
        </div>
      </section>

      {/* ═══ RESULTS ═══ */}
      {phase === 'done' && results.length > 0 && (
        <section id="results" className="px-5 sm:px-10 pt-14 pb-20 scroll-mt-20">
          <div className="flex flex-wrap items-end justify-between gap-4 pb-4 border-b-4 border-black dark:border-zinc-50">
            <h2 className="df-display text-[length:clamp(40px,5vw,72px)]">{results.length} listings</h2>
            <div className="flex flex-wrap items-center gap-2">
              <div role="group" aria-label="Sort results" className="flex">
                {SORTS.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    aria-pressed={sort === s.id}
                    onClick={() => setSort(s.id)}
                    className={`h-11 px-4 -ml-px first:ml-0 border border-black dark:border-zinc-700 text-sm font-bold ${sort === s.id ? 'bg-black text-white dark:bg-zinc-50 dark:text-black' : ''}`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
              <button type="button" onClick={() => { window.scrollTo({ top: 0, behavior: 'smooth' }); inputRef.current?.focus(); }} className="df-btn-outline">
                New search
              </button>
            </div>
          </div>
          <FeatureErrorBoundary featureName="Search results">
            <div className="flex flex-col">
              {sorted.map((car, i) => (
                <div key={car.id || i} id={car.id ? `car-${car.id}` : undefined} className="scroll-mt-24">
                  <CarResultCard car={car} userQuery={lastQuery} />
                </div>
              ))}
            </div>
          </FeatureErrorBoundary>
        </section>
      )}

      {/* ═══ ENGINE ═══ */}
      <section className="bg-df-grey dark:bg-black border-y border-neutral-200 dark:border-zinc-800">
        <div className="px-5 sm:px-10 py-20 sm:py-24 grid gap-12 lg:gap-16 lg:grid-cols-2 items-start">
          <h2 className="df-display text-[length:clamp(48px,6vw,96px)]">
            We read<br />the ad.<br /><span className="text-df-red">You read<br />the verdict.</span>
          </h2>
          <div className="flex flex-col">
            {[
              ['Condition scanner', 'If a seller says “genuine” but mentions a “shower”, the ad gets flagged, with the exact words shown.'],
              ['Fair price check', 'Every car is compared with similar live ads so you know when an asking price is high.'],
              ['Risk detection', 'Duplicate files, odd mileage and pressure tactics are caught before you call the seller.'],
            ].map(([t, d], i) => (
              <div key={t} className={`py-6 border-t border-black dark:border-zinc-700 flex flex-col gap-1.5 ${i === 2 ? 'border-b' : ''}`}>
                <strong className="text-[22px]">{t}</strong>
                <span className="text-[17px] leading-relaxed df-muted">{d}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ SOURCES ═══ */}
      <section className="px-5 sm:px-10 py-20 flex flex-col gap-8">
        <div className="flex flex-wrap justify-between items-end gap-4">
          <h2 className="df-display text-[length:clamp(44px,5.5vw,84px)]">Seven sites, <span className="text-df-red">one search.</span></h2>
          <p className="max-w-[420px] df-muted leading-relaxed">Searched live when you press search. We link back to every original ad and never host the seller’s photos or text as our own.</p>
        </div>
        <div className="flex flex-wrap gap-4">
          {SOURCES.map((s) => <Plate key={s} top="SOURCE" main={s.toUpperCase()} size="md" />)}
        </div>
      </section>

      {/* ═══ COST BAND ═══ */}
      <section className="bg-df-red text-white">
        <div className="px-5 sm:px-10 py-14 flex flex-wrap items-center justify-between gap-6">
          <div className="flex flex-col gap-2">
            <span className="text-[15px] font-bold">A {cost.priceLac} 2019 Civic in Punjab costs about</span>
            <span className="df-display text-[length:clamp(48px,7vw,104px)]">{formatLac(cost.total)} <span className="text-black">in year one.</span></span>
            <span className="text-sm">Transfer, token tax and 40 km of petrol a day, at this year’s rates.</span>
          </div>
          <Link to="/calculators" className="h-14 px-6 inline-flex items-center bg-black text-white text-base font-extrabold hover:bg-white hover:text-black transition-colors">
            Open the calculators →
          </Link>
        </div>
      </section>
    </div>
  );
}
