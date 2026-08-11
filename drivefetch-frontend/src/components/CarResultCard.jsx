import React, { useState, useEffect, useRef } from 'react';
import { Sparkles, MapPin, Calendar, Gauge, ExternalLink, Loader2, TrendingUp } from 'lucide-react';
import SaveCarButton from './SaveCarButton';
import RedFlagChip from './RedFlagChip';
import { evaluateSingleCar } from '../utils/api';

const generateHeuristicTags = (title = '') => {
  const tags = [];
  const lowerTitle = title.toLowerCase();

  // Negative / Warning tags
  if (lowerTitle.includes('shower')) {
    tags.push({ text: 'Danger: Showered', tone: 'danger' });
  }
  if (lowerTitle.includes('touchup') || lowerTitle.includes('touch up')) {
    tags.push({ text: 'Warning: Touchups', tone: 'warning' });
  }
  if (lowerTitle.includes('paint') || lowerTitle.includes('repaint')) {
    tags.push({ text: 'Warning: Painted', tone: 'warning' });
  }

  // Positive tags
  if (lowerTitle.includes('genuine') || lowerTitle.includes('bumper to bumper')) {
    tags.push({ text: 'High Liquidity: Genuine', tone: 'positive' });
  }
  if (lowerTitle.includes('non accident') || lowerTitle.includes('no accident')) {
    tags.push({ text: 'Positive: Non-Accidental', tone: 'positive' });
  }

  return tags;
};

function CarResultCard({ car, isHighlighted = false, savedListingIds = new Set(), onUnsave, userQuery = '' }) {
  // If core identifying fields haven't arrived yet, show a skeleton state
  const hasCoreFields = car?.title || (car?.make && car?.model);

  if (!hasCoreFields) {
    return (
      <div className="glass overflow-hidden flex flex-col md:flex-row animate-pulse">
        <div className="w-full md:w-1/3 h-64 md:h-auto bg-white/5 relative overflow-hidden flex-shrink-0"></div>
        <div className="w-full md:w-2/3 p-[clamp(1.25rem,2vw,1.75rem)] flex flex-col">
          <div className="flex justify-between items-start mb-2 gap-4">
            <div className="w-2/3 h-8 bg-white/10 rounded" />
            <div className="w-1/4 h-8 bg-white/10 rounded" />
          </div>
          <div className="flex space-x-6 mb-4 mt-2">
            <div className="w-16 h-4 bg-white/10 rounded" />
            <div className="w-16 h-4 bg-white/10 rounded" />
            <div className="w-16 h-4 bg-white/10 rounded" />
          </div>
          <div className="w-full h-12 bg-white/10 rounded mt-auto" />
        </div>
      </div>
    );
  }

  const analysis = car?.ai_analysis || {};

  // ─── On-Demand AI Appraisal State ───
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [aiData, setAiData] = useState(null);
  const [evalError, setEvalError] = useState(null);
  const abortControllerRef = useRef(null);

  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  // Red flags: prefer on-demand data, then existing analysis, then raw JSON field
  let redFlags = [];
  if (aiData?.red_flags?.length) {
    redFlags = aiData.red_flags;
  } else if (analysis.red_flags?.length) {
    redFlags = analysis.red_flags;
  } else if (car?.red_flags_json) {
    try {
      redFlags = typeof car.red_flags_json === 'string'
        ? JSON.parse(car.red_flags_json)
        : car.red_flags_json;
    } catch (e) {
      console.error("Failed to parse red flags:", e);
    }
  }

  // Algorithmic Liquidity Tagging: Instant heuristic evaluation
  const instantLiquidity = ((car?.relevance_score ?? 0) > 85 || (car?.score ?? 0) > 85 || isHighlighted)
    ? 'High'
    : ['corolla', 'civic', 'alto', 'city', 'vitz', 'cultus'].some(m => (car?.title ?? '').toLowerCase().includes(m))
      ? 'High'
      : null;

  const liquidityScore = aiData?.liquidity_score || instantLiquidity;
  const justification = aiData?.justification || null;
  const heuristicTags = generateHeuristicTags(car?.title ?? '');

  const priceDisplay = typeof car?.price === 'number'
    ? `PKR ${car.price.toLocaleString()}`
    : (car?.price ?? '');

  const mileageDisplay = typeof car?.mileage === 'number'
    ? `${car.mileage.toLocaleString()} km`
    : (car?.mileage ? `${car.mileage} km` : '');

  // ─── On-Demand Evaluate Handler ───
  const handleEvaluate = async () => {
    setIsEvaluating(true);
    setEvalError(null);
    abortControllerRef.current = new AbortController();
    try {
      const result = await evaluateSingleCar(car, userQuery, {
        signal: abortControllerRef.current.signal
      });
      setAiData(result);
      setIsEvaluating(false);
    } catch (err) {
      if (err.name === 'CanceledError') {
        return;
      }
      setEvalError('Appraisal failed. Please try again.');
      setIsEvaluating(false);
    }
  };

  // Liquidity badge tone mapping
  const liquidityTone = {
    High: 'bg-good/10 border-good/30 text-good',
    Medium: 'bg-warn/10 border-warn/30 text-warn',
    Low: 'bg-white/5 border-glass-hi text-text-faint',
  };

  return (
    <div
      className={`glass glass-hover overflow-hidden flex flex-col md:flex-row ${isHighlighted ? 'border-accent/40' : ''}`}
    >

      {/* ── Left: Image Container ── */}
      <div className="w-full md:w-1/3 h-64 md:h-auto bg-white/5 relative overflow-hidden flex-shrink-0">
        {car?.image_url ? (
          <img
            src={car.image_url}
            alt={car?.title ?? ''}
            className="w-full h-full object-cover transition-transform duration-500 hover:scale-105 rounded-df-sm"
            onError={(e) => { e.target.src = 'https://via.placeholder.com/400x300?text=No+Image+Available' }}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-text-faint font-bold">
            No Image Provided
          </div>
        )}

        {car?.platform && (
          <div className="glass-thin absolute top-4 left-4 text-text text-xs font-bold px-4 py-1.5 uppercase tracking-wider">
            {car.platform}
          </div>
        )}

        <div className="absolute top-3 right-3 z-10">
          <SaveCarButton
            listingId={car?.id}
            platform={car?.platform ?? ''}
            title={car?.title ?? ''}
            savedListingIds={savedListingIds}
            onUnsave={onUnsave}
          />
        </div>
      </div>

      {/* ── Right: Data Content ── */}
      <div className="w-full md:w-2/3 p-[clamp(1.25rem,2vw,1.75rem)] flex flex-col">

        {/* Title row — title truncates/wraps in its own column, price never collides */}
        <div className="flex items-start gap-4 mb-2">
          <h2 className="min-w-0 flex-1 text-2xl font-display font-black tracking-tight text-text line-clamp-2">
            {car?.title ?? ''}
          </h2>
          <div className="shrink-0 text-right">
            <p className="text-2xl font-display font-black text-text whitespace-nowrap">{priceDisplay}</p>
            {liquidityScore && (
              <span className={`inline-block mt-2 px-3 py-1 border text-xs font-bold uppercase tracking-wider rounded-full ${liquidityTone[liquidityScore] || liquidityTone.Medium}`}>
                {liquidityScore} Liquidity
              </span>
            )}
          </div>
        </div>

        {/* Specs */}
        <div className="flex items-center flex-wrap gap-x-6 gap-y-1 text-text-dim text-sm font-medium mb-4 mt-2">
          <span className="flex items-center"><Calendar className="w-4 h-4 mr-2 text-text-faint"/> {car?.year ?? ''}</span>
          <span className="flex items-center"><Gauge className="w-4 h-4 mr-2 text-text-faint"/> {mileageDisplay}</span>
          <span className="flex items-center"><MapPin className="w-4 h-4 mr-2 text-text-faint"/> {car?.city ?? ''}</span>
        </div>

        {/* Instant Heuristic Tags & AI Warning Flags */}
        {(redFlags.length > 0 || heuristicTags.length > 0) && (
          <div className="flex flex-wrap gap-2 mb-4">
            {heuristicTags.map((tag, idx) => (
              <RedFlagChip key={`heuristic-${idx}`} tone={tag.tone}>{tag.text}</RedFlagChip>
            ))}
            {redFlags.map((flag, idx) => (
              <RedFlagChip key={`ai-${idx}`} tone="danger">{flag}</RedFlagChip>
            ))}
          </div>
        )}

        {/* ── AI Appraisal Results (shown after review) ── */}
        {aiData && justification && (
          <div className="glass-thin mb-4 p-4 space-y-3">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-full bg-accent flex items-center justify-center">
                <TrendingUp className="w-3.5 h-3.5 text-white" />
              </div>
              <h4 className="text-xs font-black uppercase tracking-widest text-text">AI Market Appraisal</h4>
            </div>
            <p className="text-sm text-text-dim leading-relaxed font-medium">
              {justification}
            </p>
          </div>
        )}

        {/* Footer Area: AI Review Button + View Ad */}
        <div className="mt-auto flex flex-col md:flex-row items-stretch md:items-end gap-4">

          {/* AI Review Button (replaces old justification box) */}
          {!aiData && (
            <div className="flex-grow">
              <button
                onClick={handleEvaluate}
                disabled={isEvaluating}
                className="btn-ghost group w-full md:w-auto inline-flex items-center justify-center gap-2 text-sm font-semibold disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {isEvaluating ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Appraising...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4 group-hover:animate-pulse" />
                    <span>AI Review</span>
                  </>
                )}
              </button>
              {evalError && (
                <p className="text-xs font-medium text-text-faint mt-2">{evalError}</p>
              )}
            </div>
          )}

          <a
            href={car?.listing_url ?? '#'}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-primary shrink-0 justify-center"
          >
            <span>View Ad</span>
            <ExternalLink className="w-4 h-4" />
          </a>
        </div>
      </div>
    </div>
  );
}

export default React.memo(CarResultCard);
