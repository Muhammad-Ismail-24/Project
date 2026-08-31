import { useState, useEffect, useRef } from 'react';
import { Sparkles, MapPin, Calendar, Gauge, ExternalLink, Loader2, ShieldAlert, TrendingUp } from 'lucide-react';
// @ts-ignore
import SaveCarButton from './SaveCarButton';
import { evaluateSingleCar } from '../utils/api';
import { Car, CarEvaluation } from '../types';


interface Tag {
  text: string;
  type: 'danger' | 'warning' | 'positive';
}

const generateHeuristicTags = (title: string = ''): Tag[] => {

  const tags: Tag[] = [];
  const lowerTitle = title.toLowerCase();

  // Negative / Warning tags
  if (lowerTitle.includes('shower')) {
    tags.push({ text: 'Danger: Showered', type: 'danger' as const });
  }
  if (lowerTitle.includes('touchup') || lowerTitle.includes('touch up')) {
    tags.push({ text: 'Warning: Touchups', type: 'warning' as const });
  }
  if (lowerTitle.includes('paint') || lowerTitle.includes('repaint')) {
    tags.push({ text: 'Warning: Painted', type: 'warning' as const });
  }

  // Positive tags
  if (lowerTitle.includes('genuine') || lowerTitle.includes('bumper to bumper')) {
    tags.push({ text: 'High Liquidity: Genuine', type: 'positive' as const });
  }
  if (lowerTitle.includes('non accident') || lowerTitle.includes('no accident')) {
    tags.push({ text: 'Positive: Non-Accidental', type: 'positive' as const });
  }

  return tags;
};


interface Props {
  car: Car;
  isHighlighted?: boolean;
  savedListingIds?: Set<string>;
  onUnsave?: (id: string) => void;
  userQuery?: string;
}

export default function CarResultCard({ car, isHighlighted = false, savedListingIds = new Set(), onUnsave, userQuery = '' }: Props) {

  // If core identifying fields haven't arrived yet, show a skeleton state
  const hasCoreFields = car?.title || (car?.make && car?.model);
  
  if (!hasCoreFields) {
    return (
      <div className={`border-2 border-black dark:border-white bg-white dark:bg-zinc-900 p-4 sm:p-6 flex flex-col md:flex-row gap-6 transition-transform duration-200 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_0px_rgba(255,255,255,1)] animate-pulse`}>
        <div className="w-full md:w-1/3 aspect-[4/3] bg-black/10 dark:bg-white/10 flex-shrink-0 border-b-2 md:border-b-0 md:border-r-2 border-black/10"></div>
        <div className="w-full md:w-2/3 flex flex-col gap-4">
          <div className="w-2/3 h-8 bg-black/10 dark:bg-white/10"></div>
          <div className="w-1/4 h-8 bg-black/10 dark:bg-white/10"></div>
          <div className="flex gap-2">
            <div className="w-16 h-6 bg-black/10 dark:bg-white/10 border border-black dark:border-white"></div>
            <div className="w-16 h-6 bg-black/10 dark:bg-white/10 border border-black dark:border-white"></div>
            <div className="w-16 h-6 bg-black/10 dark:bg-white/10 border border-black dark:border-white"></div>
          </div>
          <div className="w-full h-12 bg-black/10 dark:bg-white/10 mt-auto border-2 border-black dark:border-white"></div>
        </div>
      </div>
    );
  }

  const analysis = car?.ai_analysis || {};
  
  // ─── On-Demand AI Appraisal State ───
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [aiData, setAiData] = useState<CarEvaluation | null>(null);
  const [evalError, setEvalError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
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
      if (import.meta.env.DEV) { console.error("Full error details:", e); }
      console.error("Failed to parse red flags:", e instanceof Error ? e.message : "Unknown error");
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
    // Cancel any in-flight request from a previous click
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    
    // Create a fresh controller for this request
    const controller = new AbortController();
    abortControllerRef.current = controller;
    
    setIsEvaluating(true);
    setEvalError(null);
    
    try {
      const result = await evaluateSingleCar(car, userQuery, controller.signal);
      
      // Only update state if this request wasn't cancelled
      if (!controller.signal.aborted && result !== null) {
        setAiData(result);
      }
    } catch (error: unknown) {
      if (error instanceof Error && (error.name === 'CanceledError' || error.name === 'AbortError')) {
        return; // Request was intentionally cancelled
      }
      if (!controller.signal.aborted) {
        setEvalError('Appraisal failed. Please try again.');
        if (import.meta.env.DEV) { console.error("Full error details:", error); }
        console.error("Evaluation failed:", error instanceof Error ? error.message : "Unknown error");
      }
    } finally {
      if (!controller.signal.aborted) {
        setIsEvaluating(false);
      }
    }
  };

  // Descriptive alt text for image search and screen readers.
  // car.title already carries make/model/year ("Toyota Aqua 2015 GS for Sale"),
  // so the city is appended rather than rebuilding the whole phrase — which
  // would double up the year on most platforms.
  const imageAlt = (() => {
    const base = (car?.title || '').trim();
    if (!base) return 'Used car listing photo';
    const city = (car?.city || '').trim();
    const hasForSale = /for sale/i.test(base);
    if (city && !new RegExp(`\\b${city}\\b`, 'i').test(base)) {
      return hasForSale ? `${base} in ${city}` : `${base} for sale in ${city}`;
    }
    return hasForSale ? base : `${base} for sale`;
  })();

  // Liquidity badge color mapping
  

  return (
    <div className={`border-2 border-black dark:border-white bg-white dark:bg-zinc-900 p-4 sm:p-6 flex flex-col md:flex-row gap-6 transition-transform duration-200 hover:-translate-y-1 hover:-translate-x-1 hover:shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:hover:shadow-[6px_6px_0px_0px_rgba(255,255,255,1)] ${
      isHighlighted ? 'ring-4 ring-df-red shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_0px_rgba(255,255,255,1)]' : ''
    }`}>
      
      {/* ── Left: Image Container ── */}
      <div className="w-full md:w-1/3 aspect-video md:aspect-[4/3] relative overflow-hidden flex-shrink-0 border-b-2 md:border-b-0 md:border-r-2 border-black dark:border-white bg-gray-100 dark:bg-zinc-800 flex items-center justify-center">
        {(car?.image_url || car?.images?.[0]) ? (
          <img
            src={car.image_url || car.images?.[0]}
            alt={imageAlt}
            loading="lazy"
            decoding="async"
            className="w-full h-full object-cover transition-transform duration-500 hover:scale-105"
            onError={(e) => { 
              (e.target as HTMLImageElement).onerror = null; 
              (e.target as HTMLImageElement).style.display = 'none'; 
              if ((e.target as HTMLImageElement).nextElementSibling) ((e.target as HTMLImageElement).nextElementSibling as HTMLElement).style.display = 'flex'; 
            }} 
          />
        ) : null}
        
        {/* Fallback (shown if no image or error) */}
        <div className={`w-full h-full items-center justify-center text-black dark:text-zinc-100 font-mono text-xs font-bold tracking-widest text-center uppercase p-4 ${(car?.image_url || car?.images?.[0]) ? 'hidden' : 'flex'}`}>
          [ NO IMAGE PROVIDED ]
        </div>

        {car?.platform && (
          <div className="absolute top-3 left-3 bg-black text-white text-[10px] sm:text-xs font-mono font-bold px-3 py-1 border border-black dark:border-white uppercase tracking-wider shadow-sm">
            {car.platform}
          </div>
        )}
        
        <div className="absolute top-3 right-3 z-10 bg-white dark:bg-zinc-900 border border-black dark:border-white shadow-[2px_2px_0px_#000000] dark:shadow-[2px_2px_0px_#ffffff]">
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
          <h2 className="text-xl md:text-2xl font-black uppercase tracking-tight text-black dark:text-zinc-100 leading-none line-clamp-2">
            {car?.title || 'UNKNOWN VEHICLE'}
          </h2>
          <div className="text-left sm:text-right shrink-0">
            <p className="text-xl font-bold bg-gray-100 dark:bg-zinc-800 px-3 py-1 inline-block whitespace-nowrap">
              {priceDisplay}
            </p>
            {liquidityScore && (
              <div className="mt-2">
                <span className={`inline-block px-2 py-1 border font-mono text-[10px] font-bold uppercase tracking-wider ${
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
          {car?.year && <span className="text-xs font-mono border border-black dark:border-white px-2 py-1 flex items-center bg-white dark:bg-zinc-900"><Calendar className="w-3 h-3 mr-1.5"/> {car.year}</span>}
          {mileageDisplay && <span className="text-xs font-mono border border-black dark:border-white px-2 py-1 flex items-center bg-white dark:bg-zinc-900"><Gauge className="w-3 h-3 mr-1.5"/> {mileageDisplay}</span>}
          {car?.city && <span className="text-xs font-mono border border-black dark:border-white px-2 py-1 flex items-center bg-white dark:bg-zinc-900"><MapPin className="w-3 h-3 mr-1.5"/> {car.city}</span>}
          {car?.source && <span className="text-xs font-mono border border-black dark:border-white px-2 py-1 bg-white dark:bg-zinc-900 uppercase">SRC: {car.source}</span>}
        </div>

        {/* Instant Heuristic Tags & AI Warning Flags */}
        {(redFlags.length > 0 || heuristicTags.length > 0) && (
          <div className="flex flex-wrap gap-2 mb-4">
            {heuristicTags.map((tag, idx) => (
              <span key={`heuristic-${idx}`} className={`text-[10px] sm:text-xs font-mono font-bold px-2 py-1 border flex items-center gap-1.5 uppercase tracking-wide ${
                tag.type === 'danger' ? 'bg-red-100 border-red-600 text-red-700 shadow-[2px_2px_0px_#dc2626]' :
                tag.type === 'warning' ? 'bg-orange-100 border-orange-600 text-orange-700 shadow-[2px_2px_0px_#ea580c]' :
                'bg-green-100 border-green-600 text-green-700 shadow-[2px_2px_0px_#16a34a]'
              }`}>
                {tag.type === 'danger' || tag.type === 'warning' ? <ShieldAlert className="w-3 h-3" strokeWidth={2.5} /> : <Sparkles className="w-3 h-3" strokeWidth={2.5} />}
                {tag.text}
              </span>
            ))}
            {redFlags.map((flag: string, idx: number) => (
              <span key={`ai-${idx}`} className="text-[10px] sm:text-xs font-mono font-bold px-2 py-1 border border-black bg-black text-white shadow-[2px_2px_0px_#dc2626] flex items-center gap-1.5 uppercase tracking-wide">
                <ShieldAlert className="w-3 h-3 text-red-500" strokeWidth={2.5} />
                {flag}
              </span>
            ))}
          </div>
        )}

        {/* ── AI Appraisal Results ── */}
        {aiData && justification && (
          <div className="mb-6 bg-gray-50 dark:bg-zinc-800 border border-black dark:border-white p-4">
            <div className="mb-4">
              <span className="bg-red-600 text-white font-bold uppercase px-2 py-1 inline-block border-2 border-black font-mono text-[10px] sm:text-xs tracking-widest shadow-[2px_2px_0px_#000000] flex items-center gap-1.5 w-max">
                <TrendingUp className="w-3.5 h-3.5" />
                [ AI APPRAISAL ]
              </span>
            </div>
            <p className="text-sm font-body font-semibold text-black dark:text-zinc-100 leading-relaxed border-l-4 border-red-600 pl-4 ml-1">
              {justification}
            </p>
          </div>
        )}

        {/* Footer Area: Buttons */}
        <div className="mt-auto pt-6 flex flex-col sm:flex-row items-stretch sm:items-end justify-end gap-3 sm:gap-4 border-t-2 border-black dark:border-white border-dashed">
          
          {!aiData && (
            <div className="flex-grow sm:flex-grow-0 flex flex-col items-end">
              <button
                onClick={() => {
                  handleEvaluate().catch((error: unknown) => {
                    if (import.meta.env.DEV) { console.error("Full error details:", error); }
                    console.error("Appraisal failed:", error instanceof Error ? error.message : "Unknown error");
                    setEvalError('Appraisal failed. Please try again.');
                  });
                }}
                disabled={isEvaluating}
                className="w-full sm:w-auto border-2 border-black dark:border-white bg-red-600 text-white font-bold uppercase px-4 py-2 hover:-translate-y-0.5 hover:-translate-x-0.5 hover:shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:hover:shadow-[4px_4px_0px_0px_rgba(255,255,255,1)] transition-all disabled:opacity-60 disabled:cursor-not-allowed disabled:hover:translate-x-0 disabled:hover:translate-y-0 disabled:hover:shadow-none flex items-center justify-center gap-2 whitespace-nowrap"
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
            className="w-full sm:w-auto border-2 border-black dark:border-white bg-white dark:bg-zinc-900 text-black dark:text-zinc-100 font-bold uppercase px-4 py-2 hover:bg-black dark:hover:bg-white hover:text-white dark:hover:text-black transition-colors flex items-center justify-center gap-2 whitespace-nowrap active:translate-y-[2px] active:translate-x-[2px]"
          >
            <span>[ VIEW ORIGINAL AD ]</span>
            <ExternalLink className="w-4 h-4" />
          </a>
        </div>
      </div>
    </div>
  );
}