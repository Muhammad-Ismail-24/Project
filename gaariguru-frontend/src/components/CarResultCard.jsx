import React from 'react';
import { Sparkles, MapPin, Calendar, Gauge, ExternalLink } from 'lucide-react';

export default function CarResultCard({ car, isHighlighted = false }) {
  // Safely parse red flags and AI justifications (accounting for both nested ai_analysis or flat structures)
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

  // Format details
  const priceDisplay = typeof car.price === 'number' 
    ? `PKR ${car.price.toLocaleString()}` 
    : car.price;
    
  const mileageDisplay = typeof car.mileage === 'number' 
    ? `${car.mileage.toLocaleString()} km` 
    : `${car.mileage} km`;

  return (
    <div className={`bg-white/80 backdrop-blur-md border border-white/50 rounded-2xl overflow-hidden shadow-lg hover:shadow-xl transition-all duration-300 flex flex-col md:flex-row ${
      isHighlighted ? 'bg-gradient-to-br from-amber-50/50 to-white/90 border-amber-200' : ''
    }`}>
      
      {/* Left: Dynamic Image Container */}
      <div className="w-full md:w-1/3 h-64 md:auto bg-neutral-200 relative overflow-hidden flex-shrink-0">
        {car.image_url ? (
          <img 
            src={car.image_url} 
            alt={car.title} 
            className="w-full h-full object-cover transition-transform duration-500 hover:scale-105"
            onError={(e) => { e.target.src = 'https://via.placeholder.com/400x300?text=No+Image+Available' }} 
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-neutral-400 font-medium">
            No Image Provided
          </div>
        )}

        <div className="absolute top-4 left-4 bg-black text-white text-xs font-bold px-3 py-1 rounded-full uppercase tracking-wider shadow-md">
          {car.platform}
        </div>
      </div>

      {/* Right: Data Content */}
      <div className="w-full md:w-2/3 p-6 flex flex-col">
        <div className="flex justify-between items-start mb-2">
          <h2 className="text-2xl font-black tracking-tight text-black line-clamp-2 pr-4">{car.title}</h2>
          <div className="text-right flex-shrink-0">
            <p className="text-2xl font-black text-black">{priceDisplay}</p>
            {liquidityScore === 'High' && (
              <span className="inline-block mt-1 px-3 py-1 bg-emerald-50 text-emerald-700 text-xs font-bold uppercase tracking-wider rounded-full border border-emerald-100">
                High Liquidity
              </span>
            )}
          </div>
        </div>

        {/* Specs */}
        <div className="flex items-center space-x-6 text-neutral-500 text-sm font-medium mb-4 mt-2">
          <span className="flex items-center"><Calendar className="w-4 h-4 mr-2"/> {car.year}</span>
          <span className="flex items-center"><Gauge className="w-4 h-4 mr-2"/> {mileageDisplay}</span>
          <span className="flex items-center"><MapPin className="w-4 h-4 mr-2"/> {car.city}</span>
        </div>

        {/* Warning Flags */}
        {redFlags.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-4">
            {redFlags.map((flag, idx) => (
              <span key={idx} className="bg-red-50 border border-red-200 text-red-600 text-xs font-bold px-3 py-1 rounded-md">
                {flag}
              </span>
            ))}
          </div>
        )}

        {/* Footer Area: AI Justification & External Link */}
        <div className="mt-auto flex flex-col md:flex-row items-stretch md:items-end gap-4">
          <div className="bg-neutral-50/80 backdrop-blur-sm rounded-xl p-4 flex items-start space-x-3 border border-neutral-200/50 flex-grow">
            <Sparkles className="w-5 h-5 text-black shrink-0 mt-0.5" />
            <p className="text-sm text-neutral-700 leading-relaxed font-medium">
              {justification}
            </p>
          </div>
          
          <a 
            href={car.listing_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center space-x-2 bg-black hover:bg-neutral-800 text-white font-bold py-3 px-6 rounded-xl transition-colors shrink-0"
          >
            <span>View Ad</span>
            <ExternalLink className="w-4 h-4" />
          </a>
        </div>
      </div>
    </div>
  );
}