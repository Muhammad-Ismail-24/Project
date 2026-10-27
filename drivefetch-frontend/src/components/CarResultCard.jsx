import { useState, useEffect, useRef } from 'react';
import SaveCarButton from './SaveCarButton';
import Plate from './ui/Plate';
import { Spinner } from './ui/Loaders';
import { evaluateSingleCar } from '../utils/api';
import { cityMeta, formatLac, formatPKR } from '../utils/cityMeta';

/**
 * Instant tags read from the ad title before any AI call.
 * type: 'danger' | 'warning' | 'positive'
 */
const generateHeuristicTags = (title = '') => {
  const tags = [];
  const t = title.toLowerCase();
  if (t.includes('shower')) tags.push({ text: 'Showered', type: 'danger' });
  if (t.includes('touchup') || t.includes('touch up') || t.includes('touch-up')) tags.push({ text: 'Touch-ups', type: 'warning' });
  if (t.includes('repaint') || /\bpaint(ed)?\b/.test(t)) tags.push({ text: 'Painted', type: 'warning' });
  if (t.includes('duplicate')) tags.push({ text: 'Duplicate file', type: 'danger' });
  if (t.includes('urgent')) tags.push({ text: 'Urgent sale', type: 'warning' });
  if (t.includes('genuine') || t.includes('bumper to bumper')) tags.push({ text: 'Genuine (claimed)', type: 'positive' });
  if (t.includes('non accident') || t.includes('no accident')) tags.push({ text: 'Non-accidental', type: 'positive' });
  if (t.includes('first owner') || t.includes('1st owner')) tags.push({ text: 'First owner', type: 'positive' });
  return tags;
};

const FLAG_CLASS = { danger: 'df-flag-risk', warning: 'df-flag-warn', positive: 'df-flag-good' };

function parseRedFlags(car, analysis, aiData) {
  if (aiData?.red_flags?.length) return aiData.red_flags;
  if (analysis?.red_flags?.length) return analysis.red_flags;
  if (car?.red_flags_json) {
    try {
      const parsed = typeof car.red_flags_json === 'string' ? JSON.parse(car.red_flags_json) : car.red_flags_json;
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
  return [];
}

export default function CarResultCard({ car, isHighlighted = false, savedListingIds = new Set(), onUnsave, userQuery = '' }) {
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [aiData, setAiData] = useState(null);
  const [evalError, setEvalError] = useState(null);
  const [imgFailed, setImgFailed] = useState(false);
  const abortControllerRef = useRef(null);

  useEffect(() => () => abortControllerRef.current?.abort(), []);

  const hasCoreFields = car?.title || (car?.make && car?.model);
  if (!hasCoreFields) {
    return (
      <div className="flex flex-wrap gap-6 py-6 border-b border-neutral-200 dark:border-zinc-800 animate-pulse" aria-hidden="true">
        <div className="w-full sm:w-[300px] h-[200px] bg-neutral-200 dark:bg-zinc-800" />
        <div className="flex-1 min-w-[240px] flex flex-col gap-3">
          <div className="w-2/3 h-7 bg-neutral-200 dark:bg-zinc-800" />
          <div className="w-1/3 h-4 bg-neutral-200 dark:bg-zinc-800" />
          <div className="w-1/2 h-8 bg-neutral-200 dark:bg-zinc-800 mt-auto" />
        </div>
      </div>
    );
  }

  const analysis = car?.ai_analysis || {};
  const redFlags = parseRedFlags(car, analysis, aiData);

  const instantLiquidity = ((car?.relevance_score ?? 0) > 85 || (car?.score ?? 0) > 85 || isHighlighted)
    ? 'High'
    : ['corolla', 'civic', 'alto', 'city', 'vitz', 'cultus'].some((m) => (car?.title ?? '').toLowerCase().includes(m))
      ? 'High'
      : null;
  const liquidityScore = aiData?.liquidity_score || instantLiquidity;
  const justification = aiData?.justification || null;
  const heuristicTags = generateHeuristicTags(car?.title ?? '');

  const mileageDisplay = typeof car?.mileage === 'number'
    ? `${car.mileage.toLocaleString('en-US')} km`
    : (car?.mileage ? `${String(car.mileage).replace(/\s*km$/i, '')} km` : '');
  const { region, code } = cityMeta(car?.city);
  const imageSrc = car?.image_url || car?.images?.[0];
  const platform = car?.platform || car?.source || '';
  const adUrl = car?.listing_url || car?.url || '';

  const imageAlt = (() => {
    const base = (car?.title || '').trim();
    if (!base) return 'Used car listing photo';
    const city = (car?.city || '').trim();
    const hasForSale = /for sale/i.test(base);
    if (city && !new RegExp(`\\b${city.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'i').test(base)) {
      return hasForSale ? `${base} in ${city}` : `${base} for sale in ${city}`;
    }
    return hasForSale ? base : `${base} for sale`;
  })();

  const handleEvaluate = async () => {
    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;
    setIsEvaluating(true);
    setEvalError(null);
    try {
      const result = await evaluateSingleCar(car, userQuery, controller.signal);
      if (!controller.signal.aborted && result !== null) setAiData(result);
    } catch (error) {
      if (error instanceof Error && (error.name === 'CanceledError' || error.name === 'AbortError')) return;
      if (!controller.signal.aborted) setEvalError('Appraisal failed. Please try again.');
    } finally {
      if (!controller.signal.aborted) setIsEvaluating(false);
    }
  };

  const specs = [
    car?.year ? String(car.year) : null,
    mileageDisplay || null,
    car?.city || null,
    car?.transmission ? String(car.transmission) : null,
    car?.fuel_type ? String(car.fuel_type) : null,
  ].filter(Boolean);

  return (
    <article
      className={`flex flex-wrap gap-5 sm:gap-7 py-6 border-b border-neutral-200 dark:border-zinc-800 animate-df-fade-up ${
        isHighlighted ? 'border-l-8 border-l-df-red pl-4' : ''
      }`}
    >
      {/* Photo */}
      <div className="relative w-full sm:w-[300px] h-[210px] shrink-0 bg-neutral-200 dark:bg-zinc-800 overflow-hidden flex items-center justify-center">
        {imageSrc && !imgFailed ? (
          <img
            src={imageSrc}
            alt={imageAlt}
            loading="lazy"
            decoding="async"
            onError={() => setImgFailed(true)}
            className="w-full h-full object-cover transition-transform duration-500 hover:scale-105"
          />
        ) : (
          <span className="text-sm df-muted">No photo in the ad</span>
        )}
        {platform ? (
          <span className="absolute top-0 left-0 px-2.5 py-1.5 bg-black text-white text-xs font-extrabold tracking-[0.06em] uppercase">
            {platform}
          </span>
        ) : null}
        <div className="absolute top-2 right-2">
          <SaveCarButton
            listingId={car?.id}
            platform={platform}
            title={car?.title ?? ''}
            savedListingIds={savedListingIds}
            onUnsave={onUnsave}
          />
        </div>
        <Plate top={region} main={`${code} ${car?.year ?? ''}`.trim()} size="sm" className="absolute bottom-2.5 left-2.5" ring={false} />
      </div>

      {/* Body */}
      <div className="flex-1 min-w-[260px] flex flex-col gap-3">
        <div className="flex flex-wrap justify-between items-start gap-x-5 gap-y-2">
          <h3 className="m-0 text-xl sm:text-2xl leading-tight font-extrabold max-w-[560px]">{car?.title || 'Unknown vehicle'}</h3>
          <div className="flex flex-col items-start sm:items-end gap-1.5">
            <span className="text-3xl leading-none font-black [font-stretch:78%] whitespace-nowrap">{formatLac(car?.price)}</span>
            {formatPKR(car?.price) ? <span className="text-xs df-muted">{formatPKR(car?.price)}</span> : null}
            {liquidityScore ? (
              <span
                className={`px-2 py-0.5 text-[11px] font-extrabold tracking-[0.06em] border border-black dark:border-zinc-600 ${
                  liquidityScore === 'High' ? 'bg-black text-white dark:bg-zinc-50 dark:text-black' : ''
                }`}
                title="How easily this car resells"
              >
                {String(liquidityScore).toUpperCase()} LIQUIDITY
              </span>
            ) : null}
          </div>
        </div>

        {specs.length ? (
          <div className="flex flex-wrap gap-1.5 font-mono text-[12.5px]">
            {specs.map((s) => (
              <span key={s} className="px-2 py-1 border border-neutral-200 dark:border-zinc-800 capitalize">{s}</span>
            ))}
          </div>
        ) : null}

        {(heuristicTags.length > 0 || redFlags.length > 0) ? (
          <div className="flex flex-wrap gap-1.5">
            {heuristicTags.map((tag) => (
              <span key={`h-${tag.text}`} className={FLAG_CLASS[tag.type]}>{tag.text}</span>
            ))}
            {redFlags.map((flag, idx) => (
              <span key={`ai-${idx}`} className="df-flag-risk" title="Flagged by the AI reviewer">{flag}</span>
            ))}
          </div>
        ) : null}

        {isEvaluating ? (
          <div className="flex items-center gap-2.5 text-sm df-muted" role="status">
            <Spinner className="w-3.5 h-3.5" /> Reading the ad and comparing prices…
          </div>
        ) : null}

        {aiData && justification ? (
          <div className="p-4 sm:p-5 bg-df-grey dark:bg-zinc-900 flex flex-col gap-2.5 animate-df-fade-up">
            <span className="font-mono text-xs font-semibold text-df-red-dark dark:text-zinc-300">AI APPRAISAL</span>
            <p className="m-0 text-base sm:text-[17px] leading-relaxed font-semibold">{justification}</p>
            {(aiData.pros?.length || aiData.cons?.length) ? (
              <div className="grid sm:grid-cols-2 gap-x-6 gap-y-1 text-sm leading-relaxed">
                {(aiData.pros || []).map((p) => <span key={`p-${p}`}>+ {p}</span>)}
                {(aiData.cons || []).map((c) => <span key={`c-${c}`}>− {c}</span>)}
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-2 mt-auto pt-1">
          {!aiData ? (
            <button type="button" onClick={handleEvaluate} disabled={isEvaluating} className="df-btn-red">
              {isEvaluating ? 'Appraising…' : 'AI review'}
            </button>
          ) : null}
          {adUrl ? (
            <a href={adUrl} target="_blank" rel="noopener noreferrer" className="df-btn-outline">
              View original ad <span aria-hidden="true">↗</span>
            </a>
          ) : null}
          {evalError ? <span className="text-sm font-bold text-df-red-dark dark:text-zinc-50" role="alert">{evalError}</span> : null}
        </div>
      </div>
    </article>
  );
}
