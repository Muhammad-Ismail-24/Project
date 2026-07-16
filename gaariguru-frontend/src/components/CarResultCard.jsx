import React, { useState } from 'react';
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
  const analysis = car.ai_analysis || {};
  
  // ─── On-Demand AI Appraisal State ───
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [aiData, setAiData] = useState(null);
  const [evalError, setEvalError] = useState(null);

  // Red flags: prefer on-demand data, then existing analysis, then raw JSON field
  let redFlags = [];
  if (aiData?.red_flags?.length) {
    redFlags = aiData.red_flags;
  } else if (analysis.red_flags?.length) {
    redFlags = analysis.red_flags;
  } else if (car.red_flags_json) {
    try {
      redFlags = typeof car.red_flags_json === 'string' 
        ? JSON.parse(car.red_flags_json) 
        : car.red_flags_json;
    } catch (e) {
      console.error("Failed to parse red flags:", e);
    }
  }

  const liquidityScore = aiData?.liquidity_score || null;
  const justification = aiData?.justification || null;
  const heuristicTags = generateHeuristicTags(car.title);

  const priceDisplay = typeof car.price === 'number' 
    ? `PKR ${car.price.toLocaleString()}` 
    : car.price;
    
  const mileageDisplay = typeof car.mileage === 'number' 
    ? `${car.mileage.toLocaleString()} km` 
    : `${car.mileage} km`;

  // ─── On-Demand Evaluate Handler ───
  const handleEvaluate = async () => {
    setIsEvaluating(true);
    setEvalError(null);
    try {
      const result = await evaluateSingleCar(car, userQuery);
      setAiData(result);
    } catch (err) {
      setEvalError('Appraisal failed. Please try again.');
    } finally {
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
    <div className={`backdrop-blur-md rounded-2xl overflow-hidden transition-all duration-300 flex flex-col md:flex-row ${
      isHighlighted 
        ? 'bg-white/80 border border-black/30 shadow-2xl scale-[1.01]' 
        : 'bg-white/60 border border-black/15 shadow-xl hover:shadow-2xl hover:bg-white/70'
    }`}>
      
      {/* ── Left: Image Container ── */}
      <div className="w-full md:w-1/3 h-64 md:auto bg-black/5 relative overflow-hidden flex-shrink-0 border-r border-black/10">
        {car.image_url ? (
          <img 
            src={car.image_url} 
            alt={car.title} 
            className="w-full h-full object-cover transition-transform duration-500 hover:scale-105"
            onError={(e) => { e.target.src = 'https://via.placeholder.com/400x300?text=No+Image+Available' }} 
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-black/40 font-bold">
            No Image Provided
          </div>
        )}

        <div className="absolute top-4 left-4 bg-black text-white text-xs font-bold px-4 py-1.5 rounded-full uppercase tracking-wider shadow-md">
          {car.platform}
        </div>
        
        <div className="absolute top-3 right-3 z-10">
          <SaveCarButton 
            listingId={car.id} 
            platform={car.platform} 
            title={car.title} 
            savedListingIds={savedListingIds} 
            onUnsave={onUnsave}
          />
        </div>
      </div>

      {/* ── Right: Data Content ── */}
      <div className="w-full md:w-2/3 p-6 flex flex-col">
        <div className="flex justify-between items-start mb-2">
          <h2 className="text-2xl font-black tracking-tight text-black line-clamp-2 pr-4">{car.title}</h2>
          <div className="text-right flex-shrink-0">
            <p className="text-2xl font-black text-black">{priceDisplay}</p>
            {liquidityScore && (
              <span className={`inline-block mt-2 px-3 py-1 border shadow-sm text-xs font-bold uppercase tracking-wider rounded-full ${liquidityBadge[liquidityScore] || liquidityBadge.Medium}`}>
                {liquidityScore} Liquidity
              </span>
            )}
          </div>
        </div>

        {/* Specs */}
        <div className="flex items-center space-x-6 text-black/60 text-sm font-bold mb-4 mt-2">
          <span className="flex items-center"><Calendar className="w-4 h-4 mr-2 text-black"/> {car.year}</span>
          <span className="flex items-center"><Gauge className="w-4 h-4 mr-2 text-black"/> {mileageDisplay}</span>
          <span className="flex items-center"><MapPin className="w-4 h-4 mr-2 text-black"/> {car.city}</span>
        </div>

        {/* Warning Flags (only shown after AI Review) */}
        {(redFlags.length > 0 || heuristicTags.length > 0) && (
          <div className="flex flex-wrap gap-2 mb-4">
            {heuristicTags.map((tag, idx) => (
              <span key={`heuristic-${idx}`} className={`inline-flex items-center gap-1.5 border shadow-sm text-xs font-bold px-3 py-1 rounded-full ${
                tag.type === 'danger' ? 'bg-red-50 border-red-200 text-red-700' :
                tag.type === 'warning' ? 'bg-orange-50 border-orange-200 text-orange-700' :
                'bg-green-50 border-green-200 text-green-700'
              }`}>
                {tag.type === 'danger' || tag.type === 'warning' ? <ShieldAlert className="w-3 h-3" /> : <Sparkles className="w-3 h-3" />}
                {tag.text}
              </span>
            ))}
            {redFlags.map((flag, idx) => (
              <span key={`ai-${idx}`} className="inline-flex items-center gap-1.5 bg-black border border-black text-white shadow-md text-xs font-bold px-3 py-1 rounded-full">
                <ShieldAlert className="w-3 h-3" />
                {flag}
              </span>
            ))}
          </div>
        )}

        {/* ── AI Appraisal Results (shown after review) ── */}
        {aiData && justification && (
          <div className="mb-4 bg-white/40 backdrop-blur-sm rounded-xl p-4 border border-black/10 shadow-sm space-y-3 animate-in fade-in slide-in-from-top-2 duration-300">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-full bg-black flex items-center justify-center">
                <TrendingUp className="w-3.5 h-3.5 text-white" />
              </div>
              <h4 className="text-xs font-black uppercase tracking-widest text-black">AI Market Appraisal</h4>
            </div>
            <p className="text-sm text-black/80 leading-relaxed font-bold">
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
                className="group w-full md:w-auto inline-flex items-center justify-center gap-2 bg-white/60 backdrop-blur-md border border-black/20 hover:border-black hover:bg-white/80 text-black font-bold text-sm px-5 py-3 rounded-xl transition-all duration-300 shadow-sm hover:shadow-md disabled:opacity-60 disabled:cursor-not-allowed"
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
                <p className="text-xs font-bold text-black/60 mt-2">{evalError}</p>
              )}
            </div>
          )}
          
          <a 
            href={car.listing_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center space-x-2 bg-black hover:bg-neutral-800 shadow-md text-white font-bold py-3 px-6 rounded-xl transition-colors shrink-0"
          >
            <span>View Ad</span>
            <ExternalLink className="w-4 h-4" />
          </a>
        </div>
      </div>
    </div>
  );
}