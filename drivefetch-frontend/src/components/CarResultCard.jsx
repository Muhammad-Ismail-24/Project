import React, { useState, useEffect, useRef } from 'react';
import { Sparkles, MapPin, Calendar, Gauge, ExternalLink, Loader2, ShieldAlert, TrendingUp } from 'lucide-react';
import SaveCarButton from './SaveCarButton';
import { evaluateSingleCar } from '../utils/api';

const generateHeuristicTags = (title = '') => {
  const tags = [];
  const lowerTitle = title.toLowerCase();

  // Negative / Warning tags
  if (lowerTitle.includes('shower')) {
    tags.push({ text: 'Danger: Showered', type: 'danger' });
  }
  if (lowerTitle.includes('touchup') || lowerTitle.includes('touch up')) {
    tags.push({ text: 'Warning: Touchups', type: 'warning' });
  }
  if (lowerTitle.includes('paint') || lowerTitle.includes('repaint')) {
    tags.push({ text: 'Warning: Painted', type: 'warning' });
  }

  // Positive tags
  if (lowerTitle.includes('genuine') || lowerTitle.includes('bumper to bumper')) {
    tags.push({ text: 'High Liquidity: Genuine', type: 'positive' });
  }
  if (lowerTitle.includes('non accident') || lowerTitle.includes('no accident')) {
    tags.push({ text: 'Positive: Non-Accidental', type: 'positive' });
  }

  return tags;
};

export default function CarResultCard({ car, isHighlighted = false, savedListingIds = new Set(), onUnsave, userQuery = '' }) {
  // If core identifying fields haven't arrived yet, show a skeleton state
  const hasCoreFields = car?.title || (car?.make && car?.model);
  
  if (!hasCoreFields) {
    return (
      <div className={`border-2 border-black bg-white p-4 sm:p-6 flex flex-col md:flex-row gap-6 transition-all duration-200 shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] animate-pulse`}>
        <div className="w-full md:w-1/3 aspect-[4/3] bg-black/10 border-2 border-black flex-shrink-0"></div>
        <div className="w-full md:w-2/3 flex flex-col gap-4">
          <div className="w-2/3 h-8 bg-black/10"></div>
          <div className="w-1/4 h-8 bg-black/10"></div>
          <div className="flex gap-2">
            <div className="w-16 h-6 bg-black/10 border border-black"></div>
            <div className="w-16 h-6 bg-black/10 border border-black"></div>
            <div className="w-16 h-6 bg-black/10 border border-black"></div>
          </div>
          <div className="w-full h-12 bg-black/10 mt-auto border-2 border-black"></div>
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

  // Liquidity badge color mapping
  const liquidityBadge = {
    High: 'bg-black text-white border-black',
    Medium: 'bg-white text-black border-black/30',
    Low: 'bg-white/60 text-black/60 border-black/15',
  };

  return (
    <div className={`border-2 border-black bg-white p-4 sm:p-6 flex flex-col md:flex-row gap-6 transition-all duration-200 hover:-translate-y-1 hover:-translate-x-1 hover:shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] ${
      isHighlighted ? 'ring-4 ring-df-red shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]' : ''
    }`}>
      
      {/* ── Left: Image Container ── */}
      <div className="w-full md:w-1/3 aspect-video md:aspect-[4/3] relative overflow-hidden flex-shrink-0 border-2 border-black bg-gray-100 flex items-center justify-center">
        {(car?.image_url || car?.images?.[0]) ? (
          <img 
            src={car.image_url || car.images[0]} 
            alt={car?.title ?? 'Vehicle'} 
            className="w-full h-full object-cover transition-transform duration-500 hover:scale-105"
            onError={(e) => { 
              e.target.onerror = null; 
              e.target.style.display = 'none'; 
              if (e.target.nextElementSibling) e.target.nextElementSibling.style.display = 'flex'; 
            }} 
          />
        ) : null}
        
        {/* Fallback (shown if no image or error) */}
        <div className={`w-full h-full items-center justify-center text-black font-mono text-xs font-bold tracking-widest text-center uppercase p-4 ${(car?.image_url || car?.images?.[0]) ? 'hidden' : 'flex'}`}>
          [ NO IMAGE PROVIDED ]
        </div>

        {car?.platform && (
          <div className="absolute top-3 left-3 bg-black text-white text-[10px] sm:text-xs font-mono font-bold px-3 py-1 border border-black uppercase tracking-wider shadow-sm">
            {car.platform}
          </div>
        )}
        
        <div className="absolute top-3 right-3 z-10 bg-white border border-black shadow-[2px_2px_0px_#000000]">
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
      <div className="w-full md:w-2/3 flex flex-col">
        <div className="flex flex-col sm:flex-row justify-between items-start mb-4 gap-4">
          <h2 className="text-2xl md:text-3xl font-black uppercase tracking-tight text-black leading-none line-clamp-2">
            {car?.title || 'UNKNOWN VEHICLE'}
          </h2>
          <div className="text-left sm:text-right shrink-0">
            <p className="text-xl font-bold bg-gray-100 px-3 py-1 border-2 border-black inline-block whitespace-nowrap">
              {priceDisplay}
            </p>
            {liquidityScore && (
              <div className="mt-2">
                <span className={`inline-block px-2 py-1 border-2 font-mono text-[10px] font-bold uppercase tracking-wider ${
                  liquidityScore === 'High' ? 'bg-black text-white border-black' :
                  liquidityScore === 'Medium' ? 'bg-gray-200 text-black border-black' :
                  'bg-white text-gray-500 border-gray-300'
                }`}>
                  {liquidityScore} Liquidity
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Specs Badges */}
        <div className="flex flex-wrap items-center gap-2 mb-4">
          {car?.year && <span className="text-xs font-mono border border-black px-2 py-1 flex items-center bg-white"><Calendar className="w-3 h-3 mr-1.5"/> {car.year}</span>}
          {mileageDisplay && <span className="text-xs font-mono border border-black px-2 py-1 flex items-center bg-white"><Gauge className="w-3 h-3 mr-1.5"/> {mileageDisplay}</span>}
          {car?.city && <span className="text-xs font-mono border border-black px-2 py-1 flex items-center bg-white"><MapPin className="w-3 h-3 mr-1.5"/> {car.city}</span>}
          {car?.source && <span className="text-xs font-mono border border-black px-2 py-1 bg-white uppercase">SRC: {car.source}</span>}
        </div>

        {/* Instant Heuristic Tags & AI Warning Flags */}
        {(redFlags.length > 0 || heuristicTags.length > 0) && (
          <div className="flex flex-wrap gap-2 mb-4">
            {heuristicTags.map((tag, idx) => (
              <span key={`heuristic-${idx}`} className={`text-[10px] sm:text-xs font-mono font-bold px-2 py-1 border-2 flex items-center gap-1.5 uppercase tracking-wide ${
                tag.type === 'danger' ? 'bg-red-100 border-red-600 text-red-700 shadow-[2px_2px_0px_#dc2626]' :
                tag.type === 'warning' ? 'bg-orange-100 border-orange-600 text-orange-700 shadow-[2px_2px_0px_#ea580c]' :
                'bg-green-100 border-green-600 text-green-700 shadow-[2px_2px_0px_#16a34a]'
              }`}>
                {tag.type === 'danger' || tag.type === 'warning' ? <ShieldAlert className="w-3 h-3" strokeWidth={2.5} /> : <Sparkles className="w-3 h-3" strokeWidth={2.5} />}
                {tag.text}
              </span>
            ))}
            {redFlags.map((flag, idx) => (
              <span key={`ai-${idx}`} className="text-[10px] sm:text-xs font-mono font-bold px-2 py-1 border-2 border-black bg-black text-white shadow-[2px_2px_0px_#dc2626] flex items-center gap-1.5 uppercase tracking-wide">
                <ShieldAlert className="w-3 h-3 text-red-500" strokeWidth={2.5} />
                {flag}
              </span>
            ))}
          </div>
        )}

        {/* ── AI Appraisal Results ── */}
        {aiData && justification && (
          <div className="mb-6 bg-white border-2 border-black p-4 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
            <div className="flex items-center gap-2 mb-3 pb-3 border-b-2 border-black">
              <span className="bg-black text-white px-2 py-0.5 font-mono text-[10px] font-bold tracking-widest uppercase flex items-center gap-1">
                <TrendingUp className="w-3 h-3" />
                AI APPRAISAL
              </span>
            </div>
            <p className="text-sm font-body font-semibold text-black leading-relaxed">
              {justification}
            </p>
          </div>
        )}

        {/* Footer Area: Buttons */}
        <div className="mt-auto pt-6 flex flex-col sm:flex-row items-stretch sm:items-end justify-end gap-3 sm:gap-4 border-t-2 border-black border-dashed">
          
          {!aiData && (
            <div className="flex-grow sm:flex-grow-0 flex flex-col items-end">
              <button
                onClick={handleEvaluate}
                disabled={isEvaluating}
                className="w-full sm:w-auto border-2 border-black bg-red-600 text-white font-bold uppercase px-4 py-2 hover:-translate-y-0.5 hover:-translate-x-0.5 hover:shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] transition-all disabled:opacity-60 disabled:cursor-not-allowed disabled:hover:translate-x-0 disabled:hover:translate-y-0 disabled:hover:shadow-none flex items-center justify-center gap-2 whitespace-nowrap"
              >
                {isEvaluating ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>APPRAISING...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" />
                    <span>[ AI REVIEW ]</span>
                  </>
                )}
              </button>
              {evalError && (
                <p className="text-[10px] font-mono font-bold text-red-600 mt-1 uppercase tracking-wider">{evalError}</p>
              )}
            </div>
          )}
          
          <a 
            href={car?.listing_url || car?.url || '#'}
            target="_blank"
            rel="noopener noreferrer"
            className="w-full sm:w-auto border-2 border-black bg-white text-black font-bold uppercase px-4 py-2 hover:bg-black hover:text-white transition-colors flex items-center justify-center gap-2 whitespace-nowrap active:translate-y-[2px] active:translate-x-[2px]"
          >
            <span>[ VIEW ORIGINAL AD ]</span>
            <ExternalLink className="w-4 h-4" />
          </a>
        </div>
      </div>
    </div>
  );
}