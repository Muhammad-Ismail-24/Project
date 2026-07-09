import React, { useState } from 'react';
import { Search } from 'lucide-react';

export default function SearchBar({ onSearch, isLoading }) {
  const [query, setQuery] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    if (query.trim() && onSearch) {
      onSearch(query);
    }
  };

  return (
    <form 
      onSubmit={handleSubmit} 
      className="w-full max-w-4xl mx-auto flex bg-white/60 backdrop-blur-xl border border-white/50 shadow-2xl rounded-2xl p-2 relative z-20"
    >
      <div className="flex items-center pl-4 w-full">
        <Search className="text-neutral-500 w-7 h-7" />
        <input 
          type="text" 
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="E.g., Honda Civic in Lahore under 50 Lakhs"
          className="w-full bg-transparent border-none outline-none text-black px-5 py-4 text-xl font-medium placeholder-neutral-500"
        />
      </div>
      <button 
        type="submit" 
        disabled={isLoading}
        className="bg-black text-white px-10 py-4 rounded-xl font-bold text-lg hover:bg-neutral-800 transition-all disabled:opacity-50 shadow-md"
      >
        {isLoading ? "Analyzing..." : "Find"}
      </button>
    </form>
  );
}