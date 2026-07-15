import React, { useState } from 'react';
import { Search, TrendingUp } from 'lucide-react';

// ─── Suggestion data ───────────────────────────────────────────────────────────
// Edit this array freely to update what appears in the dropdown.
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

  // ── Existing submit logic (unchanged) ───────────────────────────────────────
  const handleSubmit = (e) => {
    e.preventDefault();
    if (query.trim() && onSearch) {
      onSearch(query);
    }
  };

  // Fill the input with a suggestion and immediately submit it
  const handleSuggestionPick = (text) => {
    setQuery(text);
    setFocused(false);
    if (onSearch) onSearch(text);
  };

  const showDropdown = focused && !isLoading;

  return (
    // Outer wrapper — relative so the absolute dropdown is anchored to it
    <div className="w-full max-w-4xl mx-auto relative z-20">

      {/* ── Search form ─────────────────────────────────────────────────────── */}
      <form
        onSubmit={handleSubmit}
        className={[
          'flex items-center w-full',
          'bg-white/70 backdrop-blur-xl',
          'border rounded-2xl px-5 py-1',
          'transition-all duration-300 ease-out',
          showDropdown
            // open state: square bottom corners, elevated ring
            ? 'border-black/20 shadow-[0_8px_40px_rgba(0,0,0,0.18)] ring-2 ring-black/8 rounded-b-none'
            // idle / focused without dropdown
            : focused
              ? 'border-black/20 shadow-[0_8px_32px_rgba(0,0,0,0.14)] ring-2 ring-black/5'
              : 'border-white/50 shadow-2xl',
        ].join(' ')}
      >
        {/* Left: icon */}
        <Search
          className={`shrink-0 w-5 h-5 mr-3 transition-colors duration-200 ${
            focused ? 'text-black' : 'text-neutral-400'
          }`}
        />

        {/* Centre: text input */}
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={()  => setFocused(false)}
          placeholder="E.g., Honda Civic in Lahore under 50 Lakhs"
          disabled={isLoading}
          className="flex-1 bg-transparent border-none outline-none text-black py-4 text-lg font-medium placeholder-neutral-400 disabled:opacity-60"
        />

        {/* Right: loading pill (only visible while analysing) */}
        {isLoading && (
          <span className="ml-3 shrink-0 inline-flex items-center gap-1.5 text-xs font-bold tracking-widest uppercase text-neutral-400 animate-pulse">
            <span className="w-1.5 h-1.5 rounded-full bg-neutral-400 animate-bounce [animation-delay:0ms]"   />
            <span className="w-1.5 h-1.5 rounded-full bg-neutral-400 animate-bounce [animation-delay:150ms]" />
            <span className="w-1.5 h-1.5 rounded-full bg-neutral-400 animate-bounce [animation-delay:300ms]" />
            Analysing
          </span>
        )}
      </form>

      {/* ── Suggestion dropdown ──────────────────────────────────────────────── */}
      {/*
        onMouseDown e.preventDefault() on every interactive element inside the
        dropdown prevents the input's onBlur from firing before onClick,
        which would close the panel before the click registers.
      */}
      <div
        className={[
          'absolute left-0 right-0',
          'bg-white/80 backdrop-blur-xl',
          'border border-t-0 border-black/10',
          'rounded-b-2xl',
          'shadow-[0_20px_50px_rgba(0,0,0,0.12)]',
          'overflow-hidden',
          'transition-all duration-200 ease-out origin-top',
          showDropdown
            ? 'opacity-100 scale-y-100 pointer-events-auto'
            : 'opacity-0 scale-y-95 pointer-events-none',
        ].join(' ')}
        // Keep input focused when interacting anywhere inside the dropdown
        onMouseDown={(e) => e.preventDefault()}
      >
        {/* Header row */}
        <div className="flex items-center gap-2 px-5 pt-3 pb-2">
          <TrendingUp className="w-3.5 h-3.5 text-neutral-400" />
          <span className="text-[11px] font-black tracking-widest uppercase text-neutral-400">
            Suggested searches
          </span>
        </div>

        {/* Suggestion list */}
        <ul className="pb-2">
          {SUGGESTIONS.map((s, i) => (
            <li key={i}>
              <button
                type="button"
                onClick={() => handleSuggestionPick(s.label)}
                className="w-full flex items-center justify-between gap-4 px-5 py-2.5 text-left hover:bg-black/[0.04] transition-colors duration-100 group"
              >
                {/* Search icon + label */}
                <span className="flex items-center gap-3 min-w-0">
                  <Search className="w-3.5 h-3.5 text-neutral-300 group-hover:text-neutral-500 shrink-0 transition-colors" />
                  <span className="text-sm font-medium text-neutral-700 group-hover:text-black truncate transition-colors">
                    {s.label}
                  </span>
                </span>

                {/* Category pill */}
                <span className={`shrink-0 text-[10px] font-black tracking-widest uppercase px-2.5 py-0.5 rounded-full ${
                  s.category === 'Trending'
                    ? 'bg-amber-50 text-amber-600'
                    : 'bg-neutral-100 text-neutral-400'
                }`}>
                  {s.category}
                </span>
              </button>
            </li>
          ))}
        </ul>

        {/* Footer hint */}
        <div className="px-5 py-2.5 border-t border-neutral-100 flex items-center justify-between">
          <span className="text-[11px] text-neutral-400 font-medium">
            Or describe any car in plain English
          </span>
          <kbd className="text-[10px] font-bold bg-neutral-100 text-neutral-500 px-2 py-0.5 rounded-md tracking-wide">
            ↵ Enter
          </kbd>
        </div>
      </div>

    </div>
  );
}
