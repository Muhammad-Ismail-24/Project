import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { Link, useOutletContext } from 'react-router-dom';
import SEO from '../components/SEO';
import SplitText from '../components/motion/SplitText';
import Plate from '../components/ui/Plate';
import { Spinner } from '../components/ui/Loaders';
import { cityMeta, formatLac, formatPKR, toRupees } from '../utils/cityMeta';

const STAGES = ['Saved', 'Contacted', 'Inspected', 'Decided'];
const STORE_KEY = 'df-garage-v1';
const RISK_WORDS = ['shower', 'duplicate', 'repaint', 'touch', 'urgent'];

/* Stage and notes live in this browser (the backend has no field for them yet). */
function readGarage() {
  try { return JSON.parse(localStorage.getItem(STORE_KEY) || '{}') || {}; } catch { return {}; }
}
function writeGarage(data) {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(data)); } catch { /* storage blocked */ }
}

const carId = (car) => car.id || car.listing_id;
const riskCount = (car) => RISK_WORDS.filter((w) => String(car.title || '').toLowerCase().includes(w)).length;

function CompareDialog({ cars, onClose }) {
  const ref = useRef(null);
  useEffect(() => {
    ref.current?.querySelector('button')?.focus();
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    const node = ref.current;
    node?.addEventListener('keydown', onKey);
    return () => node?.removeEventListener('keydown', onKey);
  }, [onClose]);

  const prices = cars.map((c) => toRupees(c.price) ?? Infinity);
  const years = cars.map((c) => parseInt(c.year, 10) || 0);
  const kms = cars.map((c) => toRupees(c.mileage) ?? Infinity);
  const risks = cars.map(riskCount);
  const best = (vals, low) => {
    const target = low ? Math.min(...vals) : Math.max(...vals);
    return vals.map((v) => v === target && vals.filter((x) => x === target).length === 1 && Number.isFinite(v));
  };
  const rows = [
    ['Price', cars.map((c) => formatLac(c.price)), best(prices, true)],
    ['Year', cars.map((c) => String(c.year || '—')), best(years, false)],
    ['Mileage', cars.map((c) => (c.mileage ? `${typeof c.mileage === 'number' ? c.mileage.toLocaleString('en-US') : c.mileage} km` : '—')), best(kms, true)],
    ['City', cars.map((c) => c.city || '—'), cars.map(() => false)],
    ['Site', cars.map((c) => c.platform || '—'), cars.map(() => false)],
    ['Warning words in ad', cars.map((c) => (riskCount(c) ? `${riskCount(c)} found` : 'None')), best(risks, true)],
  ];

  return (
    <div className="fixed inset-0 z-[95] bg-black/60 flex items-end sm:items-center justify-center sm:p-6" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div ref={ref} data-lenis-prevent role="dialog" aria-modal="true" aria-labelledby="cmp-title" className="w-full max-w-5xl max-h-[90vh] overflow-auto bg-white text-black dark:bg-df-night dark:text-zinc-50 animate-df-fade-up">
        <div className="flex items-center justify-between px-6 py-5 border-b-2 border-black dark:border-zinc-50 sticky top-0 bg-inherit">
          <h2 id="cmp-title" className="df-display text-[44px]">Side by side</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="w-11 h-11 border border-black dark:border-zinc-700 text-2xl leading-none">×</button>
        </div>
        <div className="overflow-x-auto px-6 py-5">
          <table className="w-full min-w-[640px] border-collapse text-[15px]">
            <thead>
              <tr>
                <th scope="col" className="w-40" />
                {cars.map((c) => (
                  <th key={carId(c)} scope="col" className="text-left align-bottom px-3 pb-4 font-extrabold text-base leading-snug">
                    {c.title}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(([label, vals, wins]) => (
                <tr key={label} className="border-t border-neutral-200 dark:border-zinc-800">
                  <th scope="row" className="text-left py-3 pr-3 text-[13px] font-bold align-top">{label}</th>
                  {vals.map((v, i) => (
                    <td key={i} className={`px-3 py-3 align-top ${wins[i] ? 'font-extrabold bg-df-grey dark:bg-zinc-900' : ''}`}>
                      {v}{wins[i] ? <span className="block text-[11px] font-extrabold text-df-red-dark dark:text-zinc-300 mt-0.5">BEST</span> : null}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-4 text-sm df-muted">“Warning words” counts words like showered, duplicate or repainted in the ad title. Run an AI review on each car for the full check.</p>
        </div>
      </div>
    </div>
  );
}

export default function SavedCarsPage() {
  const outlet = useOutletContext() || {};
  const isAuthenticated = outlet.isAuthenticated ?? false;
  const authLoading = outlet.isLoading ?? true;
  const openSignIn = outlet.openSignIn || (() => {});

  const [savedCars, setSavedCars] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [garage, setGarage] = useState(readGarage);
  const [filter, setFilter] = useState('All');
  const [sort, setSort] = useState('recent');
  const [compareIds, setCompareIds] = useState([]);
  const [showCompare, setShowCompare] = useState(false);
  const [removed, setRemoved] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const toastTimer = useRef(null);

  const load = useCallback(async (signal) => {
    setIsLoading(true);
    setLoadError('');
    try {
      const response = await fetch('/user/saved-listings', { method: 'GET', credentials: 'include', signal });
      if (response.ok) {
        const data = await response.json();
        if (!signal?.aborted) setSavedCars(Array.isArray(data) ? data : []);
      } else {
        if (response.status === 401) document.cookie = 'has_auth=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
        if (!signal?.aborted) {
          setSavedCars([]);
          if (response.status !== 401) setLoadError('Couldn’t load your saved cars.');
        }
      }
    } catch (error) {
      if (error.name === 'AbortError') return;
      setLoadError('Couldn’t load your saved cars. Check your connection.');
    } finally {
      if (!signal?.aborted) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authLoading) return undefined;
    if (!isAuthenticated) { setIsLoading(false); return undefined; }
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [authLoading, isAuthenticated, load]);

  useEffect(() => () => clearTimeout(toastTimer.current), []);

  const updateGarage = (id, patch) => {
    setGarage((prev) => {
      const next = { ...prev, [id]: { ...(prev[id] || {}), ...patch } };
      writeGarage(next);
      return next;
    });
  };

  const removeCar = async (car) => {
    const id = carId(car);
    setBusyId(id);
    try {
      const res = await fetch(`/user/saved-listings/${encodeURIComponent(id)}`, { method: 'DELETE', credentials: 'include' });
      if (res.status === 401) { openSignIn('saved'); return; }
      if (!res.ok) throw new Error('delete failed');
      const idx = savedCars.findIndex((c) => carId(c) === id);
      setSavedCars((prev) => prev.filter((c) => carId(c) !== id));
      setCompareIds((prev) => prev.filter((x) => x !== id));
      clearTimeout(toastTimer.current);
      setRemoved({ car, idx });
      toastTimer.current = setTimeout(() => setRemoved(null), 6000);
    } catch {
      setLoadError('Couldn’t remove that car. Try again.');
    } finally {
      setBusyId(null);
    }
  };

  const undoRemove = async () => {
    if (!removed) return;
    const { car, idx } = removed;
    clearTimeout(toastTimer.current);
    setRemoved(null);
    try {
      const res = await fetch('/user/saved-listings', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ listing_id: carId(car), platform: car.platform || '', title: car.title || '' }),
      });
      if (!res.ok && res.status !== 201) throw new Error('restore failed');
      setSavedCars((prev) => { const next = [...prev]; next.splice(Math.min(idx, next.length), 0, car); return next; });
    } catch {
      setLoadError('Couldn’t restore that car.');
    }
  };

  const stageOf = (car) => garage[carId(car)]?.stage ?? 0;
  const counts = useMemo(() => {
    const c = { All: savedCars.length };
    STAGES.forEach((s, i) => { c[s] = savedCars.filter((car) => stageOf(car) === i).length; });
    return c;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [savedCars, garage]);

  const shown = useMemo(() => {
    let list = savedCars.filter((car) => filter === 'All' || STAGES[stageOf(car)] === filter);
    if (sort === 'price') list = [...list].sort((a, b) => (toRupees(a.price) ?? Infinity) - (toRupees(b.price) ?? Infinity));
    if (sort === 'year') list = [...list].sort((a, b) => (parseInt(b.year, 10) || 0) - (parseInt(a.year, 10) || 0));
    return list;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [savedCars, filter, sort, garage]);

  const compareCars = savedCars.filter((c) => compareIds.includes(carId(c)));
  const signedOut = !authLoading && !isAuthenticated;
  const loading = authLoading || (isAuthenticated && isLoading);
  const empty = !loading && isAuthenticated && savedCars.length === 0 && !loadError;

  return (
    <div className="w-full relative">
      <SEO title="Saved Vehicles" description="Your saved vehicles on DriveFetch." path="/saved" noindex />

      <section className="px-5 sm:px-10 pt-12 sm:pt-14 pb-7 flex flex-wrap justify-between items-end gap-5">
        <div className="flex flex-col gap-2">
          <span data-reveal="fade" className="df-label">YOUR GARAGE</span>
          <h1 className="df-display text-[length:clamp(60px,9vw,136px)]"><SplitText text="Saved" /> <SplitText text="cars." className="text-df-red" start={1} /></h1>
        </div>
        {isAuthenticated && savedCars.length > 0 && (
          <div className="flex flex-wrap items-center gap-2.5">
            <label htmlFor="saved-sort" className="text-sm df-muted">Sort</label>
            <select id="saved-sort" value={sort} onChange={(e) => setSort(e.target.value)} className="df-select w-auto h-12">
              <option value="recent">Recently saved</option>
              <option value="price">Price, low to high</option>
              <option value="year">Newest model</option>
            </select>
            <button type="button" disabled={compareIds.length < 2} onClick={() => setShowCompare(true)} className="df-btn-red h-12 px-5">
              Compare{compareIds.length ? ` (${compareIds.length})` : ''}
            </button>
          </div>
        )}
      </section>

      {loadError && (
        <div role="alert" className="mx-5 sm:mx-10 mb-6 flex flex-wrap items-center gap-3 p-4 border-2 border-df-red">
          <strong className="flex-1">{loadError}</strong>
          <button type="button" onClick={() => load()} className="df-btn-outline">Retry</button>
        </div>
      )}

      {loading && (
        <section aria-busy="true" aria-label="Loading saved cars" className="px-5 sm:px-10 border-t-2 border-black dark:border-zinc-50">
          {[0, 1, 2].map((k) => (
            <div key={k} className="flex flex-wrap gap-7 py-6 border-b border-neutral-200 dark:border-zinc-800 animate-pulse">
              <div className="w-full sm:w-[220px] h-[150px] bg-neutral-200 dark:bg-zinc-800" />
              <div className="flex-1 min-w-[220px] flex flex-col gap-3">
                <div className="w-1/2 h-6 bg-neutral-200 dark:bg-zinc-800" />
                <div className="w-1/3 h-4 bg-neutral-200 dark:bg-zinc-800" />
                <div className="w-4/5 h-2 bg-neutral-200 dark:bg-zinc-800 mt-auto" />
              </div>
            </div>
          ))}
        </section>
      )}

      {signedOut && (
        <section className="px-5 sm:px-10 pt-6 pb-24 flex flex-wrap gap-10 lg:gap-16 border-t-2 border-black dark:border-zinc-50">
          <div className="flex-[1_1_420px] min-w-0 flex flex-col gap-5 pt-6">
            <p className="df-display text-[length:clamp(40px,5vw,72px)]"><SplitText text="Sign in to see your garage." /></p>
            <button type="button" data-reveal onClick={() => openSignIn('saved')} className="df-btn-ink self-start h-14 px-6 text-base">Continue with Google</button>
          </div>
          <ul data-stagger className="flex-[1_1_360px] min-w-0 mt-6 flex flex-col text-[17px] leading-snug">
            {['Keep cars across devices', 'Track each car from saved to decided, with your own notes', 'Keep your chat history and your assistant’s name'].map((t) => (
              <li key={t} className="py-3.5 border-t border-black dark:border-zinc-700 last:border-b">{t}</li>
            ))}
          </ul>
        </section>
      )}

      {empty && (
        <section className="px-5 sm:px-10 pt-6 pb-24 flex flex-col gap-6 border-t-2 border-black dark:border-zinc-50">
          <p className="df-display text-[length:clamp(40px,5vw,72px)] mt-6"><SplitText text="Nothing saved yet." /></p>
          <p data-reveal className="max-w-[560px] text-lg leading-relaxed df-muted">Tap the bookmark on any car to keep it here. You can track each one from first call to final decision and keep notes as you go.</p>
          <div className="flex flex-wrap gap-2.5">
            <Link to="/" className="df-btn-red h-14 px-6 text-base">Search cars</Link>
            <Link to="/recommend" className="df-btn-outline h-14 px-6 text-base">Try the Matchmaker</Link>
          </div>
        </section>
      )}

      {!loading && isAuthenticated && savedCars.length > 0 && (
        <>
          <div role="tablist" aria-label="Filter by stage" className="px-5 sm:px-10 flex flex-wrap border-b-2 border-black dark:border-zinc-50">
            {['All', ...STAGES].map((s) => (
              <button
                key={s}
                type="button"
                role="tab"
                aria-selected={filter === s}
                onClick={() => setFilter(s)}
                className={`h-[52px] px-4 -mb-[2px] border-b-4 text-[15px] ${filter === s ? 'border-df-red font-extrabold' : 'border-transparent font-medium hover:border-neutral-300 dark:hover:border-zinc-700'}`}
              >
                {s} <span className="font-mono text-xs df-muted">{counts[s] ?? 0}</span>
              </button>
            ))}
          </div>

          <section className="px-5 sm:px-10 pb-24 flex flex-col">
            {shown.length === 0 && (
              <p className="py-10 df-muted">No cars at this stage yet.</p>
            )}
            {shown.map((car) => {
              const id = carId(car);
              const stage = stageOf(car);
              const note = garage[id]?.note || '';
              const { region, code } = cityMeta(car.city);
              const inCompare = compareIds.includes(id);
              const imageSrc = car.image_url;
              return (
                <article key={id} data-reveal className="flex flex-wrap gap-6 lg:gap-7 py-6 border-b border-neutral-200 dark:border-zinc-800">
                  <div className="relative w-full sm:w-[220px] h-[150px] shrink-0 bg-neutral-200 dark:bg-zinc-800 overflow-hidden">
                    {imageSrc ? <img src={imageSrc} alt={car.title || 'Saved car'} loading="lazy" className="w-full h-full object-cover" /> : null}
                    <Plate top={region} main={`${code} ${car.year ?? ''}`.trim()} size="sm" ring={false} className="absolute bottom-2.5 left-2.5" />
                  </div>
                  <div className="flex-[1_1_320px] min-w-0 flex flex-col gap-2.5">
                    <div className="flex flex-wrap justify-between items-baseline gap-x-4 gap-y-1">
                      <h2 className="text-xl sm:text-2xl font-extrabold leading-tight">{car.title}</h2>
                      <span className="text-3xl font-black [font-stretch:78%] whitespace-nowrap">{formatLac(car.price)}</span>
                    </div>
                    <span className="font-mono text-[12.5px] df-muted">
                      {[car.mileage ? `${typeof car.mileage === 'number' ? car.mileage.toLocaleString('en-US') : car.mileage} km` : null, car.city, car.platform, car.saved_at ? `saved ${new Date(car.saved_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}` : null].filter(Boolean).join(' · ')}
                    </span>
                    {formatPKR(car.price) ? <span className="text-xs df-muted">{formatPKR(car.price)}</span> : null}
                    <div role="radiogroup" aria-label="Buying stage" className="grid grid-cols-4 gap-1 mt-2">
                      {STAGES.map((s, i) => (
                        <button
                          key={s}
                          type="button"
                          role="radio"
                          aria-checked={stage === i}
                          onClick={() => updateGarage(id, { stage: i })}
                          className={`flex flex-col gap-1.5 pb-1 text-left text-[13px] ${stage === i ? 'font-extrabold' : 'font-medium'} ${i <= stage ? '' : 'df-muted'} hover:text-df-red`}
                        >
                          <span className={`h-1.5 w-full ${i <= stage ? 'bg-df-red' : 'bg-neutral-200 dark:bg-zinc-800'}`} />
                          {s}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="flex-[1_1_260px] min-w-0 flex flex-col gap-2">
                    <label htmlFor={`note-${id}`} className="text-[13px] df-muted">Notes (kept on this device)</label>
                    <textarea
                      id={`note-${id}`}
                      rows={3}
                      maxLength={500}
                      value={note}
                      onChange={(e) => updateGarage(id, { note: e.target.value })}
                      placeholder="Seller’s number, viewing time, mechanic’s verdict…"
                      className="resize-none px-3 py-2.5 border border-black dark:border-zinc-700 bg-transparent text-sm leading-relaxed outline-none focus:border-df-red placeholder:text-neutral-500"
                    />
                    <div className="flex flex-wrap gap-1.5">
                      <label className={`h-10 px-3 flex items-center gap-2 border border-black dark:border-zinc-700 text-[13px] font-bold cursor-pointer ${inCompare ? 'bg-black text-white dark:bg-zinc-50 dark:text-black' : ''}`}>
                        <input
                          type="checkbox"
                          checked={inCompare}
                          disabled={!inCompare && compareIds.length >= 3}
                          onChange={() => setCompareIds((prev) => (inCompare ? prev.filter((x) => x !== id) : [...prev, id]))}
                          className="w-4 h-4 accent-df-red"
                        />
                        Compare
                      </label>
                      {car.listing_url ? (
                        <a href={car.listing_url} target="_blank" rel="noopener noreferrer" className="h-10 px-3 inline-flex items-center border border-black dark:border-zinc-700 text-[13px] font-bold hover:bg-black hover:text-white dark:hover:bg-zinc-50 dark:hover:text-black">Open ad ↗</a>
                      ) : null}
                      <button type="button" onClick={() => removeCar(car)} disabled={busyId === id} className="h-10 px-2 text-[13px] font-bold underline underline-offset-2 flex items-center gap-2 disabled:opacity-50">
                        {busyId === id ? <Spinner className="w-3.5 h-3.5" /> : null}Remove
                      </button>
                    </div>
                  </div>
                </article>
              );
            })}
            {compareIds.length > 0 && compareIds.length < 2 && (
              <p className="pt-4 text-sm df-muted">Tick one more car to compare (up to 3).</p>
            )}
          </section>
        </>
      )}

      {removed && (
        <div role="status" className="fixed left-4 right-4 sm:left-10 sm:right-auto bottom-6 z-[70] flex items-center gap-5 pl-5 pr-2 py-2 bg-black text-white dark:bg-zinc-50 dark:text-black animate-df-fade-up">
          <span className="text-[15px] font-bold truncate">Removed {removed.car.title}.</span>
          <button type="button" onClick={undoRemove} className="h-10 px-4 bg-df-red text-white text-sm font-extrabold shrink-0">Undo</button>
        </div>
      )}

      {showCompare && compareCars.length >= 2 && (
        <CompareDialog cars={compareCars} onClose={() => setShowCompare(false)} />
      )}
    </div>
  );
}
