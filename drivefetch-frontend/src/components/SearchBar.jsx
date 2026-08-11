import React, { useState, useRef } from 'react';
import { Search } from 'lucide-react';

export default function SearchBar({ onSearch, isLoading }) {
  const [query, setQuery] = useState('');
  const inputRef = useRef(null);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (query.trim() && onSearch) {
      onSearch(query);
      // Drop the mobile keyboard immediately after searching
      if (inputRef.current) {
        inputRef.current.blur();
      }
    }
  };

  return (
    <div className="w-full max-w-4xl mx-auto relative z-20">

      <form
        onSubmit={handleSubmit}
        className="glass !rounded-full flex items-center w-full px-5 py-1"
      >
        <Search className="shrink-0 w-5 h-5 mr-3 text-text-dim" />

        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="E.g., Honda Civic in Lahore under 50 Lakhs"
          disabled={isLoading}
          className="flex-1 bg-transparent border-none outline-none text-text py-4 text-base md:text-lg font-medium placeholder-text-faint disabled:opacity-60"
        />

        {isLoading && (
          <span className="ml-3 shrink-0 inline-flex items-center gap-1.5 text-xs font-bold tracking-widest uppercase text-text-dim animate-pulse">
            <span className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce [animation-delay:0ms]"   />
            <span className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce [animation-delay:150ms]" />
            <span className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce [animation-delay:300ms]" />
            Analysing
          </span>
        )}
      </form>

    </div>
  );
}