import { useState, useRef, useEffect, useMemo } from 'react';
import CarResultCard from '../components/CarResultCard';
import SEO from '../components/SEO';
import { recommendSchema } from '../config/seoSchemas';
import { Spinner } from '../components/ui/Loaders';
import SplitText from '../components/motion/SplitText';
import { useScrollTo } from '../components/motion/SmoothScroll';
import { stripEmoji } from '../utils/cityMeta';

const API_BASE = import.meta.env.VITE_API_URL || '';

const EXAMPLE_PROMPTS = [
  'Family SUV under 80 lac in Lahore, mostly city driving',
  'Fuel-efficient hybrid for a 50 km daily commute in Islamabad, under 45 lac',
  'Cheapest automatic car for a new driver in Karachi',
];

/** Things a useful brief mentions. Each is detected live as the user types. */
const BRIEF_PARTS = [
  { id: 'budget', label: 'Budget', test: /\b\d+(\.\d+)?\s*(lac|lacs|lakh|lakhs|crore|million|m|k)\b|\bunder\b|\bbudget\b|\bcheap/i, chips: ['under 30 lac', 'under 45 lac', 'under 80 lac'] },
  { id: 'city', label: 'City', test: /lahore|karachi|islamabad|rawalpindi|pindi|peshawar|multan|faisalabad|quetta|sialkot|gujranwala|hyderabad|abbottabad/i, chips: ['in Lahore', 'in Karachi', 'in Islamabad'] },
  { id: 'people', label: 'Who rides', test: /family|kids|children|seat|seater|people|passenger|myself|wife|parents|student|single|new driver|couple/i, chips: ['family of 4', 'family of 6', 'just me'] },
  { id: 'use', label: 'Daily use', test: /commute|daily|office|city|highway|trip|km|travel|driving|roads?\b|mountain|village/i, chips: ['mostly city driving', '40 km a day', 'long highway trips'] },
  { id: 'prefs', label: 'Gearbox or fuel', test: /automatic|\bauto\b|manual|hybrid|petrol|diesel|cng|electric|\bev\b|suv|sedan|hatch|crossover|4x4|awd|sunroof/i, chips: ['automatic', 'hybrid', 'no CNG'] },
];

const STAGES = [
  { id: 'mapping', label: 'Reading your brief' },
  { id: 'scraping', label: 'Searching 7 sites' },
  { id: 'aggregating', label: 'Scoring the ads' },
  { id: 'complete', label: 'Done' },
];
const STAGE_INDEX = { mapping: 0, scraping: 1, aggregating: 2, backfilling: 2, complete: 3 };

const targetLabel = (t) => {
  if (typeof t === 'string') return t;
  if (typeof t?.label === 'string' && t.label) return t.label;
  return [t?.make || t?.label?.make, t?.model || t?.label?.model, t?.trim || t?.label?.trim].filter(Boolean).join(' ');
};

/** Does a listing belong to a suggested model? Matched on the model name in the ad title. */
const listingMatches = (listing, target) => {
  const model = String(target?.model || '').toLowerCase().trim();
  const title = String(listing?.title || `${listing?.make || ''} ${listing?.model || ''}`).toLowerCase();
  if (model) return title.includes(model);
  const label = targetLabel(target).toLowerCase().split(' ').slice(0, 2).join(' ');
  return Boolean(label) && title.includes(label);
};

/** Reads a text/event-stream response and calls onEvent(type, data) per event. */
async function readSSE(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop();
    for (const part of parts) {
      let eventType = 'message';
      let dataStr = '';
      for (const line of part.trim().split('\n')) {
        if (line.startsWith('event:')) eventType = line.slice(6).trim();
        if (line.startsWith('data:')) dataStr = line.slice(5).trim();
      }
      if (!dataStr) continue;
      try { onEvent(eventType, JSON.parse(dataStr)); } catch { /* ignore malformed chunk */ }
    }
  }
}

function Check({ on }) {
  return (
    <span aria-hidden="true" className={`w-5 h-5 shrink-0 flex items-center justify-center border-2 transition-colors duration-300 ${on ? 'bg-df-red border-df-red text-white' : 'border-neutral-300 dark:border-zinc-700 text-transparent'}`}>
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.4" strokeLinecap="square"><path d="M4 12l5 5L20 6" /></svg>
    </span>
  );
}

export default function RecommendPage() {
  const [prompt, setPrompt] = useState('');
  const [status, setStatus] = useState('');
  const [stage, setStage] = useState('');
  const [targets, setTargets] = useState([]);
  const [listings, setListings] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [extLoading, setExtLoading] = useState(false);
  const [extTargets, setExtTargets] = useState([]);
  const [extListings, setExtListings] = useState([]);
  const [extDone, setExtDone] = useState(false);
  const [extError, setExtError] = useState('');
  const [strategyBrief, setStrategyBrief] = useState(null);
  const [lastPrompt, setLastPrompt] = useState('');
  const [modelFilter, setModelFilter] = useState(null); // index into targets, or null for all

  const abortRef = useRef(null);
  const inputRef = useRef(null);
  const scrollTo = useScrollTo();

  useEffect(() => () => abortRef.current?.abort(), []);

  const found = useMemo(() => BRIEF_PARTS.map((p) => p.test.test(prompt)), [prompt]);
  const foundCount = found.filter(Boolean).length;

  const resetExtension = () => {
    setExtTargets([]);
    setExtListings([]);
    setExtDone(false);
    setExtLoading(false);
    setExtError('');
  };

  const addPhrase = (phrase) => {
    setPrompt((prev) => {
      const base = prev.trim().replace(/[.,;]+$/, '');
      const next = base ? `${base}, ${phrase}` : phrase.charAt(0).toUpperCase() + phrase.slice(1);
      return next.slice(0, 500);
    });
    inputRef.current?.focus({ preventScroll: true });
  };

  const handleSearch = async () => {
    const p = prompt.trim();
    if (!p || loading) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setListings([]);
    setTargets([]);
    setError('');
    setStage('mapping');
    setLoading(true);
    resetExtension();
    setStrategyBrief(null);
    setModelFilter(null);
    setStatus('Connecting to the AI engine…');
    setLastPrompt(p);
    setTimeout(() => scrollTo('#mm-progress', { offset: -90 }), 80);

    try {
      const response = await fetch(`${API_BASE}/api/recommend`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ prompt: p }),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`The matchmaker is unavailable right now (error ${response.status}).`);

      await readSSE(response, (eventType, data) => {
        if (eventType === 'status') {
          setStatus(stripEmoji(data.message || ''));
          if (data.stage) setStage(data.stage);
          if (data.targets) setTargets(data.targets.map((t) => (typeof t === 'string' ? { label: t, rationale: '' } : { ...t, rationale: t.rationale || '' })));
        }
        if (eventType === 'strategy') {
          setStrategyBrief({ summary: data.summary || '', disclaimers: data.disclaimers || [], targets: data.targets || [] });
          if (data.targets?.length) setTargets((prev) => (prev.length ? prev : data.targets));
        }
        if (eventType === 'results') {
          setListings(data.listings || []);
          setTargets(data.targets || []);
          if (data.disclaimers?.length) setStrategyBrief((prev) => ({ summary: prev?.summary || '', targets: prev?.targets || [], disclaimers: data.disclaimers }));
          setStage('complete');
          setLoading(false);
        }
        if (eventType === 'error') {
          setError(stripEmoji(data.message || 'Something went wrong.'));
          setLoading(false);
          setStage('');
        }
      });
      setLoading(false);
      setStage((s) => (s && s !== 'complete' ? 'complete' : s));
    } catch (err) {
      if (err?.name === 'AbortError') return;
      setError(err instanceof Error ? err.message : 'Failed to connect to the server.');
      setLoading(false);
      setStage('');
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSearch();
    }
  };

  const handleClear = () => {
    abortRef.current?.abort();
    setPrompt('');
    setListings([]);
    setTargets([]);
    setError('');
    setStatus('');
    setStage('');
    setLoading(false);
    resetExtension();
    setStrategyBrief(null);
    setModelFilter(null);
    scrollTo(0);
    setTimeout(() => inputRef.current?.focus({ preventScroll: true }), 600);
  };

  const handleShowMore = async () => {
    if (extLoading || extDone) return;
    setExtLoading(true);
    setExtError('');
    const excludeModels = targets.map((t) => `${t.make || ''} ${t.model || ''}`.trim()).filter(Boolean);
    try {
      const response = await fetch(`${API_BASE}/api/recommend/extend`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ prompt: lastPrompt || prompt.trim(), exclude_models: excludeModels, city: '', max_budget: null }),
      });
      if (!response.ok) throw new Error(`Server error: ${response.status}`);
      await readSSE(response, (eventType, data) => {
        if (eventType === 'extension_results') {
          setExtTargets(data.targets || []);
          setExtListings(data.listings || []);
        }
        if (eventType === 'error') setExtError(stripEmoji(data.message || 'Couldn’t find more options.'));
        if (eventType === 'status' && data.stage === 'complete') {
          setExtDone(true);
          setExtLoading(false);
        }
      });
    } catch (err) {
      console.error('Extension error:', err instanceof Error ? err.message : 'Unknown error');
      setExtError('Couldn’t find more options. Try again later.');
    } finally {
      setExtLoading(false);
      setExtDone(true);
    }
  };

  const allTargets = useMemo(() => [...targets, ...extTargets], [targets, extTargets]);
  const allListings = useMemo(() => [...listings, ...extListings], [listings, extListings]);
  const countFor = (t) => allListings.filter((l) => listingMatches(l, t)).length;
  const visibleListings = modelFilter === null ? listings : allListings.filter((l) => listingMatches(l, allTargets[modelFilter]));
  const showMoreOptions = modelFilter === null && extListings.length > 0;

  const pickModel = (i) => {
    setModelFilter((cur) => (cur === i ? null : i));
    setTimeout(() => scrollTo('#mm-listings', { offset: -80 }), 60);
  };

  const stageIdx = STAGE_INDEX[stage] ?? -1;
  const showProgress = loading || stage === 'complete';
  const isEmpty = !loading && !error && listings.length === 0 && stage === 'complete';
  const hasResults = (strategyBrief || (targets.length > 0 && !loading)) && !error;

  return (
    <div className="w-full">
      <SEO
        title="AI Car Matchmaker | Find Your Ideal Car in Pakistan"
        description="Tell us your budget, city and lifestyle. DriveFetch's AI matchmaker picks three models that fit and finds live listings for each."
        path="/recommend"
        keywords={['AI car recommendation Pakistan', 'best car for my budget Pakistan', 'car matchmaker']}
        schema={recommendSchema}
      />

      {/* ═══ BRIEF ═══ */}
      <section className="bg-df-grey dark:bg-black border-b border-neutral-200 dark:border-zinc-800">
        <div className="px-5 sm:px-10 py-12 sm:py-16 grid gap-12 lg:gap-16 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] items-start">
          <div className="flex flex-col gap-7 lg:sticky lg:top-28">
            <span data-reveal="fade" className="flex items-center gap-3 font-mono text-[13px] font-semibold tracking-[0.08em]">
              <span data-reveal="line" className="w-8 h-[2px] bg-df-red" />AI MATCHMAKER
            </span>
            <h1 className="text-[length:clamp(40px,4.4vw,66px)] font-extrabold leading-[1.04] tracking-[-0.025em]">
              <SplitText text="Tell us how you’ll use the car." className="block" />
              <SplitText text="We’ll pick three that fit." className="block text-df-red" start={7} />
            </h1>
            <p data-reveal style={{ '--rd': '200ms' }} className="max-w-[460px] text-lg leading-relaxed df-muted">
              Write it the way you’d explain it to a friend. The more you mention, the better the picks.
            </p>
            <ol className="flex flex-col" data-stagger>
              {[
                ['Describe', 'Budget, city, who rides along, how far you drive.'],
                ['We pick 3 models', 'Each comes with the reason it fits you.'],
                ['You get live ads', 'Real listings for each model from 7 sites, already checked.'],
              ].map(([t, d], i) => (
                <li key={t} className="relative grid grid-cols-[40px_minmax(0,1fr)] gap-4 pb-6 last:pb-0">
                  {i < 2 ? <span aria-hidden="true" className="absolute left-[19px] top-10 bottom-0 w-px bg-neutral-300 dark:bg-zinc-700" /> : null}
                  <span className="w-10 h-10 flex items-center justify-center bg-black text-white dark:bg-zinc-50 dark:text-black font-bold">{i + 1}</span>
                  <span className="flex flex-col gap-0.5 pt-1.5">
                    <strong className="text-[17px]">{t}</strong>
                    <span className="text-[15px] df-muted leading-relaxed">{d}</span>
                  </span>
                </li>
              ))}
            </ol>
          </div>

          <div className="flex flex-col gap-5" data-reveal style={{ '--rd': '250ms' }}>
            <div className="bg-white dark:bg-df-night border border-black dark:border-zinc-700 shadow-[10px_10px_0_0_#E5202E]">
              <div className="flex items-center justify-between gap-3 px-5 sm:px-6 pt-5">
                <label htmlFor="mm-prompt" className="text-[15px] font-bold">Your brief</label>
                <span className="font-mono text-xs df-muted">{prompt.length}/500</span>
              </div>
              <textarea
                id="mm-prompt"
                ref={inputRef}
                rows={4}
                maxLength={500}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={loading}
                data-lenis-prevent
                placeholder="E.g. a fuel-efficient hybrid for my daily commute in Islamabad, under 45 lac"
                className="w-full px-5 sm:px-6 pt-3 pb-4 bg-transparent text-xl sm:text-[22px] leading-relaxed outline-none resize-none placeholder:text-neutral-400 dark:placeholder:text-zinc-600 disabled:opacity-60"
              />

              <div className="px-5 sm:px-6 py-5 border-t border-neutral-200 dark:border-zinc-800 flex flex-col gap-4">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-bold">Quick add</span>
                  <span className="text-sm df-muted">{foundCount} of {BRIEF_PARTS.length} covered</span>
                </div>
                <div aria-hidden="true" className="h-1 bg-neutral-200 dark:bg-zinc-800 overflow-hidden">
                  <div className="h-full bg-df-red transition-transform duration-700 ease-[cubic-bezier(.19,1,.22,1)] origin-left" style={{ transform: `scaleX(${foundCount / BRIEF_PARTS.length})` }} />
                </div>
                <ul className="flex flex-col">
                  {BRIEF_PARTS.map((part, i) => (
                    <li key={part.id} className="grid sm:grid-cols-[150px_minmax(0,1fr)] gap-x-4 gap-y-2 items-center py-2.5 border-b border-neutral-100 dark:border-zinc-900 last:border-b-0">
                      <span className={`flex items-center gap-2.5 text-[15px] font-semibold transition-colors ${found[i] ? '' : 'df-muted'}`}>
                        <Check on={found[i]} />{part.label}
                      </span>
                      <span className="flex flex-wrap gap-1.5">
                        {part.chips.map((chip) => (
                          <button
                            key={chip}
                            type="button"
                            disabled={loading}
                            onClick={() => addPhrase(chip)}
                            className="h-9 px-3 border border-neutral-300 dark:border-zinc-700 text-sm font-semibold transition-colors duration-300 hover:border-black hover:bg-black hover:text-white dark:hover:border-zinc-50 dark:hover:bg-zinc-50 dark:hover:text-black disabled:opacity-50"
                          >
                            + {chip}
                          </button>
                        ))}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="flex flex-wrap items-center gap-3 px-5 sm:px-6 py-4 border-t border-neutral-200 dark:border-zinc-800">
                <span className="text-xs df-muted mr-auto hidden sm:block">Enter to send · Shift+Enter for a new line</span>
                {prompt && !loading ? (
                  <button type="button" onClick={handleClear} className="df-btn-outline h-12 px-4">Clear</button>
                ) : null}
                <button
                  type="button"
                  onClick={handleSearch}
                  disabled={!prompt.trim() || loading}
                  className="df-btn-red h-12 px-6 text-[15px]"
                >
                  {loading ? <Spinner className="w-4 h-4" light /> : null}
                  {loading ? 'Finding matches…' : 'Find my matches →'}
                </button>
              </div>
            </div>

            {!loading && (
              <div className="flex flex-col gap-2">
                <span className="text-sm font-bold">Or start from an example</span>
                <div className="flex flex-col">
                  {EXAMPLE_PROMPTS.map((ex) => (
                    <button
                      key={ex}
                      type="button"
                      onClick={() => { setPrompt(ex); inputRef.current?.focus({ preventScroll: true }); }}
                      className="group flex items-center justify-between gap-4 text-left py-3 border-b border-neutral-300 dark:border-zinc-800 text-[15px] hover:text-df-red transition-colors"
                    >
                      <span>“{ex}”</span>
                      <span aria-hidden="true" className="transition-transform duration-500 group-hover:translate-x-1">→</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ═══ PROGRESS ═══ */}
      {showProgress && (
        <section id="mm-progress" aria-live="polite" className="px-5 sm:px-10 pt-12 pb-4 scroll-mt-24">
          <div className="flex flex-col gap-6 p-6 sm:p-8 border border-neutral-200 dark:border-zinc-800 animate-df-fade-up">
            <div className="flex items-center gap-4">
              {loading ? <Spinner className="w-6 h-6" /> : (
                <span aria-hidden="true" className="w-6 h-6 bg-df-red text-white flex items-center justify-center">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.4" strokeLinecap="square"><path d="M4 12l5 5L20 6" /></svg>
                </span>
              )}
              <strong className="text-xl">
                {loading ? (status || 'Reading your brief…') : isEmpty ? 'Finished. No live ads fit every condition.' : `Done. ${targets.length} model${targets.length === 1 ? '' : 's'}, ${listings.length} live ads.`}
              </strong>
            </div>
            <ol className="grid grid-cols-2 lg:grid-cols-4 gap-x-3 gap-y-5">
              {STAGES.map((s, i) => {
                const done = i < stageIdx || stage === 'complete';
                const active = i === stageIdx && loading;
                return (
                  <li key={s.id} className="flex flex-col gap-2.5">
                    <span className="relative h-1 bg-neutral-200 dark:bg-zinc-800 overflow-hidden">
                      <span
                        className={`absolute inset-0 origin-left transition-transform duration-700 ease-[cubic-bezier(.19,1,.22,1)] ${done ? 'bg-black dark:bg-zinc-50 scale-x-100' : active ? 'bg-df-red scale-x-50 animate-df-pulse' : 'scale-x-0'}`}
                      />
                    </span>
                    <span className={`flex items-center gap-2 text-sm ${active ? 'font-extrabold' : 'font-semibold'} ${done || active ? '' : 'df-muted'}`}>
                      <span className="font-mono text-xs">0{i + 1}</span>{s.label}
                    </span>
                  </li>
                );
              })}
            </ol>
            {targets.length > 0 && loading && (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm df-muted">Models picked so far</span>
                {targets.map((t, i) => (
                  <span key={i} style={{ animationDelay: `${i * 90}ms` }} className="h-9 px-3 flex items-center bg-black text-white dark:bg-zinc-50 dark:text-black text-sm font-bold animate-df-fade-up">{targetLabel(t)}</span>
                ))}
              </div>
            )}
          </div>
        </section>
      )}

      {/* ═══ ERROR ═══ */}
      {error && (
        <section className="px-5 sm:px-10 py-10">
          <div role="alert" className="flex flex-wrap items-center gap-4 p-6 border-l-4 border-df-red bg-df-grey dark:bg-black animate-df-fade-up">
            <div className="flex flex-col gap-1 flex-1 min-w-[240px]">
              <strong className="text-xl">The Matchmaker couldn’t finish.</strong>
              <span className="df-muted">{error} Your brief is still here.</span>
            </div>
            <button type="button" onClick={handleSearch} className="df-btn-red h-12 px-5">Try again</button>
          </div>
        </section>
      )}

      {/* ═══ WHY + MODELS ═══ */}
      {hasResults && (
        <section className="px-5 sm:px-10 pt-12 pb-6 flex flex-col gap-8">
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] items-start">
            <div className="flex flex-col gap-3" data-reveal>
              <span className="text-sm font-bold text-df-red-dark dark:text-df-red">Why these models</span>
              <p className="m-0 text-2xl sm:text-[28px] leading-snug font-bold tracking-[-0.01em]">
                {strategyBrief?.summary || 'Here are the models that fit your brief.'}
              </p>
            </div>
            {(strategyBrief?.disclaimers || []).length > 0 && (
              <ul className="flex flex-col gap-2" data-reveal style={{ '--rd': '120ms' }}>
                {strategyBrief.disclaimers.map((d, i) => (
                  <li key={i} className="flex gap-3 p-4 bg-df-grey dark:bg-black text-[15px] leading-relaxed">
                    <span aria-hidden="true" className="w-1 shrink-0 bg-df-red" />{d}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {allTargets.length > 0 && !loading && (
            <div className="flex flex-col gap-4">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="text-2xl font-extrabold tracking-[-0.01em]">Your matches</h2>
                <span className="text-sm df-muted">Pick a model to see only its ads</span>
              </div>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" data-stagger>
                {allTargets.map((t, i) => {
                  const selected = modelFilter === i;
                  const n = countFor(t);
                  const isExtra = i >= targets.length;
                  return (
                    <button
                      key={`${targetLabel(t)}-${i}`}
                      type="button"
                      aria-pressed={selected}
                      onClick={() => pickModel(i)}
                      className={`group flex flex-col gap-4 p-6 text-left border transition-colors duration-300 ${selected ? 'bg-black text-white border-black dark:bg-zinc-50 dark:text-black dark:border-zinc-50' : `bg-white dark:bg-df-night ${isExtra ? 'border-dashed' : ''} border-neutral-300 dark:border-zinc-700 hover:border-black dark:hover:border-zinc-50`}`}
                    >
                      <span className="flex items-center justify-between gap-3">
                        <span className="w-10 h-10 flex items-center justify-center font-bold text-[15px] bg-df-red text-white">{String(i + 1).padStart(2, '0')}</span>
                        <span className={`text-xs font-bold ${selected ? '' : 'df-muted'}`}>{isExtra ? 'More option' : 'Top pick'}</span>
                      </span>
                      <span className="flex flex-col gap-1.5">
                        <strong className="text-[24px] leading-tight tracking-[-0.01em]">{targetLabel(t)}</strong>
                        {t.rationale ? <span className={`text-[15px] leading-relaxed ${selected ? 'opacity-80' : 'df-muted'}`}>{t.rationale}</span> : null}
                      </span>
                      <span className={`mt-auto flex items-center justify-between gap-3 pt-4 border-t text-sm font-bold ${selected ? 'border-white/20 dark:border-black/20' : 'border-neutral-200 dark:border-zinc-800'}`}>
                        <span>{n} live {n === 1 ? 'ad' : 'ads'}</span>
                        <span className="transition-transform duration-500 group-hover:translate-x-1">{selected ? 'Showing ✓' : 'Show ads →'}</span>
                      </span>
                    </button>
                  );
                })}
              </div>
              {listings.length > 0 && !extDone && (
                <button type="button" onClick={handleShowMore} disabled={extLoading} className="df-btn-outline self-start h-12 px-5">
                  {extLoading ? <Spinner className="w-4 h-4" /> : null}
                  {extLoading ? 'Finding more models…' : 'Explore more models'}
                </button>
              )}
              {extError ? <p role="alert" className="text-sm font-bold">{extError}</p> : null}
            </div>
          )}
        </section>
      )}

      {/* ═══ EMPTY ═══ */}
      {isEmpty && (
        <section className="px-5 sm:px-10 py-12 flex flex-col gap-4 max-w-[720px]">
          <h2 className="text-[length:clamp(32px,3.6vw,48px)] font-extrabold tracking-[-0.02em]"><SplitText text="No live ads fit right now." /></h2>
          <p data-reveal className="df-muted text-lg">Loosen one part of your brief and try again:</p>
          <div data-reveal className="flex flex-wrap gap-2">
            {['Raise the budget a little', 'Allow any city', 'Allow a manual gearbox'].map((tip) => (
              <span key={tip} className="h-11 px-4 inline-flex items-center bg-df-grey dark:bg-black font-semibold">{tip}</span>
            ))}
          </div>
          <div data-reveal>
            <button type="button" onClick={() => { scrollTo(0); setTimeout(() => inputRef.current?.focus({ preventScroll: true }), 600); }} className="df-btn-red h-12 px-5 mt-2">Edit my brief</button>
          </div>
        </section>
      )}

      {/* ═══ LISTINGS ═══ */}
      {listings.length > 0 && !loading && (
        <section id="mm-listings" className="px-5 sm:px-10 pt-8 pb-20 scroll-mt-24 flex flex-col">
          <div className="flex flex-wrap items-end justify-between gap-3 pb-4 border-b-2 border-black dark:border-zinc-50">
            <h2 className="text-[length:clamp(28px,3vw,40px)] font-extrabold tracking-[-0.02em]">
              {modelFilter === null ? `${listings.length + extListings.length} live ads` : `${visibleListings.length} ads for ${targetLabel(allTargets[modelFilter])}`}
            </h2>
            <div className="flex flex-wrap gap-2">
              {modelFilter !== null && (
                <button type="button" onClick={() => setModelFilter(null)} className="df-btn-outline h-11">Show all models</button>
              )}
              <button type="button" onClick={handleClear} className="df-btn-ink h-11">New brief</button>
            </div>
          </div>
          {visibleListings.length === 0 ? (
            <p className="py-10 text-lg df-muted">No ads for this model in the results. Try another match above.</p>
          ) : (
            visibleListings.map((listing, idx) => (
              <div key={`${modelFilter}-${listing.listing_url || listing.id || idx}`} data-reveal style={{ '--rd': `${Math.min(idx, 5) * 80}ms` }}>
                <CarResultCard car={listing} userQuery={lastPrompt} />
              </div>
            ))
          )}
          {showMoreOptions && (
            <>
              <div className="flex items-center gap-4 mt-14 mb-2" data-reveal>
                <span className="h-px flex-1 bg-neutral-300 dark:bg-zinc-700" />
                <span className="text-xl font-extrabold">More options</span>
                <span className="h-px flex-1 bg-neutral-300 dark:bg-zinc-700" />
              </div>
              {extListings.map((listing, idx) => (
                <div key={`ext-${listing.listing_url || listing.id || idx}`} data-reveal style={{ '--rd': `${Math.min(idx, 5) * 80}ms` }}>
                  <CarResultCard car={listing} userQuery={lastPrompt} />
                </div>
              ))}
            </>
          )}
        </section>
      )}
    </div>
  );
}
