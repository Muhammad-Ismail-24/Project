import React, { useState } from 'react';
import { Search, TrendingUp } from 'lucide-react';

// ─── Suggestion data ───────────────────────────────────────────────────────────
const SUGGESTIONS = [
  { label: 'Honda Civic Oriel 2020 in Islamabad under 55 lacs',  category: 'Popular'  },
  { label: 'Suzuki Swift GLX 2019 Lahore under 30 lacs',         category: 'Popular'  },
  { label: 'Toyota Corolla GLi 2015 Karachi under 40 lacs',      category: 'Trending' },
  { label: 'Daihatsu Hijet in Rawalpindi',                       category: 'Trending' },
  { label: 'Kia Sportage 2022 automatic Islamabad',              category: 'Popular'  },
];

export default function SearchBar({ onSearch, isLoading }) {
  const [query,   setQuery]   = useState('');
  const [focused, setFocused] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (query.trim() && onSearch) {
      onSearch(query);
    }
  };

  const handleSuggestionPick = (text) => {
    setQuery(text);
    setFocused(false);
    if (onSearch) onSearch(text);
  };

  const showDropdown = focused && !isLoading;

  return (
    <div className="w-full max-w-4xl mx-auto relative z-20">

      {/* ── Flat Grey Search form with Black Border ── */}
      <form
        onSubmit={handleSubmit}
        className={[
          'flex items-center w-full',
          'bg-[#a3a3a3]', 
          'border border-black px-5 py-1',
          'transition-all duration-300 ease-out',
          showDropdown
            ? 'rounded-t-2xl border-b-transparent shadow-none'
            : 'rounded-full shadow-lg hover:shadow-xl'
        ].join(' ')}
      >
        <Search className="shrink-0 w-5 h-5 mr-3 text-black" />

        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={()  => setFocused(false)}
          placeholder="E.g., Honda Civic in Lahore under 50 Lakhs"
          disabled={isLoading}
          className="flex-1 bg-transparent border-none outline-none text-black py-4 text-lg font-bold placeholder-black/60 disabled:opacity-60"
        />

        {isLoading && (
          <span className="ml-3 shrink-0 inline-flex items-center gap-1.5 text-xs font-bold tracking-widest uppercase text-black animate-pulse">
            <span className="w-1.5 h-1.5 rounded-full bg-black animate-bounce [animation-delay:0ms]"   />
            <span className="w-1.5 h-1.5 rounded-full bg-black animate-bounce [animation-delay:150ms]" />
            <span className="w-1.5 h-1.5 rounded-full bg-black animate-bounce [animation-delay:300ms]" />
            Analysing
          </span>
        )}
      </form>

      {/* ── Flat Grey Suggestion dropdown ── */}
      <div
        className={[
          'absolute left-0 right-0 z-50',
          'bg-[#a3a3a3]',
          'border border-black border-t-0',
          'rounded-b-2xl',
          'overflow-hidden',
          'transition-all duration-200 ease-out origin-top',
          showDropdown
            ? 'opacity-100 scale-y-100 pointer-events-auto shadow-2xl'
            : 'opacity-0 scale-y-95 pointer-events-none',
        ].join(' ')}
        onMouseDown={(e) => e.preventDefault()}
      >
        <div className="flex items-center gap-2 px-5 pt-3 pb-2">
          <TrendingUp className="w-3.5 h-3.5 text-black" />
          <span className="text-[11px] font-black tracking-widest uppercase text-black">
            Suggested searches
          </span>
        </div>

        <ul className="pb-2">
          {SUGGESTIONS.map((s, i) => (
            <li key={i}>
              <button
                type="button"
                onClick={() => handleSuggestionPick(s.label)}
                className="w-full flex items-center justify-between gap-4 px-5 py-2.5 text-left hover:bg-black/10 transition-colors duration-100 group"
              >
                <span className="flex items-center gap-3 min-w-0">
                  <Search className="w-3.5 h-3.5 text-black/60 group-hover:text-black shrink-0 transition-colors" />
                  <span className="text-sm font-bold text-black/80 group-hover:text-black truncate transition-colors">
                    {s.label}
                  </span>
                </span>

                <span className={`shrink-0 text-[10px] font-black tracking-widest uppercase px-2.5 py-0.5 rounded-full border border-black ${
                  s.category === 'Trending'
                    ? 'bg-black text-white'
                    : 'bg-transparent text-black'
                }`}>
                  {s.category}
                </span>
              </button>
            </li>
          ))}
        </ul>

        <div className="px-5 py-2.5 border-t border-black/20 flex items-center justify-between">
          <span className="text-[11px] text-black/80 font-bold">
            Or describe any car in plain English
          </span>
          <kbd className="text-[10px] font-bold bg-transparent border border-black text-black px-2 py-0.5 rounded-md tracking-wide">
            ↵ Enter
          </kbd>
        </div>
      </div>

    </div>
  );
}