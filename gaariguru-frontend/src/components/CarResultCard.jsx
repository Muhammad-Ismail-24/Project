import React from 'react';
import { Sparkles, MapPin, Calendar, Gauge, ExternalLink } from 'lucide-react';
import SaveCarButton from './SaveCarButton';

export default function CarResultCard({ car, isHighlighted = false, savedListingIds = new Set(), onUnsave }) {
  const analysis = car.ai_analysis || {};
  
  let redFlags = [];
  if (analysis.red_flags) {
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

  const liquidityScore = analysis.liquidity_score || car.liquidity_score || 'Medium';
  const justification = analysis.justification || car.justification || 'Listing meets standard query parameters.';

  const priceDisplay = typeof car.price === 'number' 
    ? `PKR ${car.price.toLocaleString()}` 
    : car.price;
    
  const mileageDisplay = typeof car.mileage === 'number' 
    ? `${car.mileage.toLocaleString()} km` 
    : `${car.mileage} km`;

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
            {liquidityScore === 'High' && (
              <span className="inline-block mt-2 px-3 py-1 bg-white border border-black/20 text-black shadow-sm text-xs font-bold uppercase tracking-wider rounded-full">
                High Liquidity
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

        {/* Warning Flags (Strict Black & White) */}
        {redFlags.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-4">
            {redFlags.map((flag, idx) => (
              <span key={idx} className="bg-black border border-black text-white shadow-md text-xs font-bold px-3 py-1 rounded-full">
                {flag}
              </span>
            ))}
          </div>
        )}

        {/* Footer Area: AI Justification & External Link */}
        <div className="mt-auto flex flex-col md:flex-row items-stretch md:items-end gap-4">
          <div className="bg-white/40 backdrop-blur-sm rounded-xl p-4 flex items-start space-x-3 border border-black/10 flex-grow shadow-sm">
            <Sparkles className="w-5 h-5 text-black shrink-0 mt-0.5" />
            <p className="text-sm text-black/80 leading-relaxed font-bold">
              {justification}
            </p>
          </div>
          
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