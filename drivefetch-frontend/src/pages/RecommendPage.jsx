import { useState, useRef, useEffect } from 'react';
import CarResultCard from '../components/CarResultCard';
import SEO from '../components/SEO';
import { recommendSchema } from '../config/seoSchemas';
import { Spinner } from '../components/ui/Loaders';
import { stripEmoji } from '../utils/cityMeta';

const API_BASE = import.meta.env.VITE_API_URL || '';

const EXAMPLE_PROMPTS = [
  'Family SUV under 80 lac in Lahore',
  'Fuel efficient hybrid for daily commute',
  'Japanese import hatchback under 35 lac',
  'AWD crossover with sunroof in Islamabad',
  'Sports feel under 40 lac, no CNG',
  'Cheapest automatic car for a new driver',
];

const STAGES = [
  { id: 'mapping', label: 'Reading your brief' },
  { id: 'scraping', label: 'Searching 7 sites' },
  { id: 'aggregating', label: 'Scoring and removing duplicates' },
  { id: 'complete', label: 'Done' },
];
const STAGE_INDEX = { mapping: 0, scraping: 1, aggregating: 2, backfilling: 2, complete: 3 };

const targetLabel = (t) => {
  if (typeof t === 'string') return t;
  if (typeof t?.label === 'string' && t.label) return t.label;
  return [t?.make || t?.label?.make, t?.model || t?.label?.model, t?.trim || t?.label?.trim].filter(Boolean).join(' ');
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
  const [showPrompts, setShowPrompts] = useState(false);
  const [lastPrompt, setLastPrompt] = useState('');

  const abortRef = useRef(null);
  const inputRef = useRef(null);
  const resultsRef = useRef(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const resetExtension = () => {
    setExtTargets([]);
    setExtListings([]);
    setExtDone(false);
    setExtLoading(false);
    setExtError('');
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
    setStatus('Connecting to the AI engine…');
    setShowPrompts(false);
    setLastPrompt(p);

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

  useEffect(() => {
    if (stage === 'complete' && listings.length > 0) {
      resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [stage, listings.length]);

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
    setShowPrompts(false);
    window.scrollTo({ top: 0, behavior: 'smooth' });
    inputRef.current?.focus();
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

  const stageIdx = STAGE_INDEX[stage] ?? -1;
  const showProgress = loading || (stage === 'complete');
  const isEmpty = !loading && !error && listings.length === 0 && stage === 'complete';
  const isIdle = !loading && !error && !stage;

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
      <section className="bg-df-red text-white">
        <div className="px-5 sm:px-10 py-12 sm:py-14 flex flex-wrap gap-10 lg:gap-14 items-start">
          <div className="flex-[1_1_420px] min-w-0 flex flex-col gap-5">
            <span className="font-mono text-[13px] font-semibold tracking-[0.06em]">AI MATCHMAKER</span>
            <h1 className="df-display text-[length:clamp(56px,7.5vw,112px)]">Tell us what you need.<br /><span className="text-black">We’ll fetch the rest.</span></h1>
            <p className="max-w-[460px] text-lg leading-relaxed">Budget, city, family, commute, fuel. Write it like you’d tell a friend. We pick the models, then search 7 sites for each one.</p>
          </div>
          <div className="flex-[1_1_520px] flex flex-col gap-2.5 min-w-0">
            <div className="bg-white text-black flex flex-col">
              <label htmlFor="mm-prompt" className="px-4 sm:px-5 pt-4 text-[13px] font-bold">Your brief</label>
              <textarea
                id="mm-prompt"
                ref={inputRef}
                rows={4}
                maxLength={500}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={loading}
                placeholder="E.g. a fuel-efficient hybrid for my daily commute in Islamabad, under 45 lac"
                className="px-4 sm:px-5 pt-2 pb-4 bg-transparent text-lg sm:text-xl leading-relaxed outline-none resize-none placeholder:text-neutral-500 disabled:opacity-60"
              />
              <div className="flex flex-wrap items-center gap-2.5 px-3 sm:px-4 py-2.5 border-t border-neutral-200">
                <span className="font-mono text-xs text-neutral-600 mr-auto">{prompt.length}/500 · Enter to send, Shift+Enter for a new line</span>
                {prompt && !loading ? (
                  <button type="button" onClick={handleClear} className="h-11 px-4 border border-black text-sm font-bold hover:bg-black hover:text-white">Clear</button>
                ) : null}
                <button
                  type="button"
                  onClick={handleSearch}
                  disabled={!prompt.trim() || loading}
                  className="h-12 px-6 bg-black text-white text-[15px] font-extrabold tracking-[0.06em] hover:bg-df-red disabled:opacity-60 disabled:hover:bg-black flex items-center gap-2"
                >
                  {loading ? <Spinner className="w-4 h-4" light /> : null}
                  {loading ? 'MATCHING…' : 'INITIATE'}
                </button>
              </div>
            </div>
            {!loading && (
              <button
                type="button"
                aria-expanded={showPrompts}
                onClick={() => setShowPrompts((v) => !v)}
                className="self-start h-11 text-[15px] font-bold underline underline-offset-4"
              >
                {showPrompts ? 'Hide example briefs ▲' : 'Show example briefs ▼'}
              </button>
            )}
            {showPrompts && !loading && (
              <div className="flex flex-col bg-black animate-df-fade-up">
                {EXAMPLE_PROMPTS.map((ex) => (
                  <button
                    key={ex}
                    type="button"
                    onClick={() => { setPrompt(ex); setShowPrompts(false); inputRef.current?.focus(); }}
                    className="text-left min-h-[48px] px-4 sm:px-5 border-b border-zinc-800 last:border-b-0 text-white text-base hover:bg-white hover:text-black"
                  >
                    {ex} →
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ═══ PROGRESS ═══ */}
      {showProgress && (
        <section aria-live="polite" className="bg-df-grey dark:bg-black border-b border-neutral-200 dark:border-zinc-800">
          <div className="px-5 sm:px-10 py-7 flex flex-col gap-5">
            <div className="flex items-center gap-4">
              {loading ? <Spinner className="w-5 h-5" /> : null}
              <strong className="text-lg">{loading ? (status || 'Processing your brief…') : isEmpty ? 'Search finished · no listings fit' : `Done · ${targets.length} model${targets.length === 1 ? '' : 's'}, ${listings.length} listings`}</strong>
            </div>
            <ol className="grid grid-cols-2 lg:grid-cols-4 gap-2">
              {STAGES.map((s, i) => {
                const done = i < stageIdx || (stage === 'complete');
                const active = i === stageIdx && loading;
                return (
                  <li key={s.id} className="flex flex-col gap-2">
                    <span className={`h-1.5 transition-colors duration-300 ${done ? 'bg-black dark:bg-zinc-50' : active ? 'bg-df-red' : 'bg-neutral-300 dark:bg-zinc-800'}`} />
                    <span className={`text-sm ${active ? 'font-extrabold' : 'font-semibold'} ${done || active ? '' : 'df-muted'}`}>{s.label}</span>
                  </li>
                );
              })}
            </ol>
            {targets.length > 0 && loading && (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[13px] df-muted">Models found</span>
                {targets.map((t, i) => (
                  <span key={i} className="h-9 px-3 flex items-center bg-black text-white dark:bg-zinc-50 dark:text-black text-sm font-bold animate-df-fade-up">{targetLabel(t)}</span>
                ))}
              </div>
            )}
          </div>
        </section>
      )}

      {/* ═══ ERROR ═══ */}
      {error && (
        <section className="px-5 sm:px-10 py-12">
          <div role="alert" className="flex flex-wrap items-center gap-4 p-6 border-2 border-df-red">
            <div className="flex flex-col gap-1 flex-1 min-w-[240px]">
              <strong className="text-xl">The matchmaker couldn’t finish.</strong>
              <span className="df-muted">{error} Your brief is still here.</span>
            </div>
            <button type="button" onClick={handleSearch} className="df-btn-red h-12 px-5">Try again</button>
          </div>
        </section>
      )}

      {/* ═══ STRATEGY + MODELS ═══ */}
      {(strategyBrief || (targets.length > 0 && !loading)) && !error && (
        <section className="px-5 sm:px-10 pt-14 pb-6 grid gap-10 lg:gap-16 lg:grid-cols-2 items-start">
          <div className="flex flex-col gap-4 animate-df-fade-up">
            <span className="df-label">STRATEGY</span>
            {strategyBrief?.summary ? (
              <p className="m-0 text-xl sm:text-[22px] leading-snug font-semibold">{strategyBrief.summary}</p>
            ) : (
              <p className="m-0 text-xl font-semibold">Here are the models that fit your brief.</p>
            )}
            {(strategyBrief?.disclaimers || []).map((d, i) => (
              <div key={i} className="flex gap-3 p-4 border border-black dark:border-zinc-700">
                <span aria-hidden="true" className="w-2.5 shrink-0 bg-df-red" />
                <span className="text-[15px] leading-relaxed">{d}</span>
              </div>
            ))}
          </div>
          {targets.length > 0 && !loading && (
            <div className="flex flex-col border-t-2 border-black dark:border-zinc-50">
              {targets.map((t, i) => (
                <div key={i} className="grid grid-cols-[64px_minmax(0,1fr)] gap-4 py-4 border-b border-black dark:border-zinc-700 animate-df-fade-up">
                  <span className="df-display text-[44px] text-df-red">{String(i + 1).padStart(2, '0')}</span>
                  <span className="flex flex-col gap-1"><strong className="text-xl">{targetLabel(t)}</strong>{t.rationale ? <span className="text-[15px] leading-relaxed df-muted">{t.rationale}</span> : null}</span>
                </div>
              ))}
              {extTargets.map((t, i) => (
                <div key={`x-${i}`} className="grid grid-cols-[64px_minmax(0,1fr)] gap-4 py-4 border-b border-dashed border-black dark:border-zinc-700 animate-df-fade-up">
                  <span className="df-display text-[44px] df-muted">{String(targets.length + i + 1).padStart(2, '0')}</span>
                  <span className="flex flex-col gap-1"><strong className="text-xl">{targetLabel(t)}</strong>{t.rationale ? <span className="text-[15px] leading-relaxed df-muted">{t.rationale}</span> : null}</span>
                </div>
              ))}
              {listings.length > 0 && !extDone && (
                <button type="button" onClick={handleShowMore} disabled={extLoading} className="mt-4 h-13 min-h-[52px] border border-dashed border-black dark:border-zinc-600 text-[15px] font-extrabold flex items-center justify-center gap-2 hover:bg-black hover:text-white dark:hover:bg-zinc-50 dark:hover:text-black disabled:opacity-60">
                  {extLoading ? <Spinner className="w-4 h-4" /> : null}
                  {extLoading ? 'Finding more models…' : 'Explore more models'}
                </button>
              )}
              {extError ? <p role="alert" className="mt-3 text-sm font-bold">{extError}</p> : null}
            </div>
          )}
        </section>
      )}

      {/* ═══ EMPTY ═══ */}
      {isEmpty && (
        <section className="px-5 sm:px-10 py-14 flex flex-col gap-4">
          <h2 className="df-display text-[length:clamp(40px,5vw,72px)]">Zero matches.</h2>
          <p className="df-muted text-lg">No live ads fit every condition. Loosen one part of your brief and try again:</p>
          <div className="flex flex-wrap gap-2">
            {['Raise the budget a little', 'Allow any city', 'Allow a manual gearbox'].map((tip) => (
              <span key={tip} className="h-11 px-4 inline-flex items-center border border-black dark:border-zinc-700 font-bold">{tip}</span>
            ))}
          </div>
          <button type="button" onClick={() => inputRef.current?.focus()} className="df-btn-red self-start h-12 px-5 mt-2">Edit my brief</button>
        </section>
      )}

      {/* ═══ LISTINGS ═══ */}
      {listings.length > 0 && !loading && (
        <section ref={resultsRef} className="px-5 sm:px-10 pt-6 pb-20 scroll-mt-20 flex flex-col">
          <div className="flex flex-wrap items-end justify-between gap-3 pb-4 border-b-4 border-black dark:border-zinc-50">
            <h2 className="df-display text-[length:clamp(36px,4.5vw,64px)]">{listings.length + extListings.length} listings retrieved</h2>
            <button type="button" onClick={handleClear} className="df-btn-outline">New brief</button>
          </div>
          {listings.map((listing, idx) => (
            <CarResultCard key={listing.listing_url || listing.id || idx} car={listing} userQuery={lastPrompt} />
          ))}
          {extListings.length > 0 && (
            <>
              <div className="flex items-center gap-4 mt-12 mb-2">
                <span className="h-1 flex-1 bg-black dark:bg-zinc-50" />
                <span className="df-display text-3xl">More options</span>
                <span className="h-1 flex-1 bg-black dark:bg-zinc-50" />
              </div>
              {extListings.map((listing, idx) => (
                <CarResultCard key={`ext-${listing.listing_url || listing.id || idx}`} car={listing} userQuery={lastPrompt} />
              ))}
            </>
          )}
        </section>
      )}

      {/* ═══ IDLE: HOW IT WORKS ═══ */}
      {isIdle && (
        <section className="px-5 sm:px-10 py-16 sm:py-20 grid gap-10 sm:grid-cols-3">
          {[
            ['01', 'We read your brief', 'Budget, seats, city, fuel and must-haves are pulled out of your words.'],
            ['02', 'We pick the models', 'Each one comes with the reason it fits and what to watch out for.'],
            ['03', 'We find real ads', 'Live listings for each model from 7 sites, scored and de-duplicated.'],
          ].map(([n, t, d]) => (
            <div key={n} className="flex flex-col gap-2">
              <span className="df-display text-[56px] text-df-red">{n}</span>
              <strong className="text-xl">{t}</strong>
              <span className="df-muted leading-relaxed">{d}</span>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
