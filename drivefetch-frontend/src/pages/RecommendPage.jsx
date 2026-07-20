/**
 * src/pages/RecommendPage.jsx
 *
 * The AI Matchmaker page — feature-based car search.
 * Users describe what they want in plain language; the backend
 * maps it to real car models and searches all platforms in parallel.
 *
 * Matches the visual language of the existing search results page.
 * SSE streaming reuses the same event format as /api/search.
 */

import { useState, useRef, useEffect } from "react";
import { Sparkles, Search, X, ChevronRight, Car } from "lucide-react";
import CarResultCard from "../components/CarResultCard";

const API_BASE = import.meta.env.VITE_API_URL || "https://carfinder-project-backend.onrender.com";

// Example prompts shown as chips to help users get started
const EXAMPLE_PROMPTS = [
  "AWD crossover with sunroof under 80 lacs in Islamabad",
  "Cheapest automatic car for new driver under 15 lacs",
  "Family SUV 7 seater, budget 60-90 lacs Lahore",
  "Fuel efficient hybrid under 50 lacs",
  "Sports feel under 40 lacs, no CNG",
  "Japanese import hatchback, budget 25-35 lacs Karachi",
];

export default function RecommendPage() {
  const [prompt, setPrompt]       = useState("");
  const [status, setStatus]       = useState("");   // status message from SSE
  const [stage, setStage]         = useState("");   // mapping | scraping | aggregating | complete
  const [targets, setTargets]     = useState([]);   // [{make, model, rationale}]
  const [listings, setListings]   = useState([]);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState("");
  const eventSourceRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) eventSourceRef.current.close();
    };
  }, []);

  const handleSearch = async () => {
    if (!prompt.trim() || loading) return;

    // Reset state
    setListings([]);
    setTargets([]);
    setError("");
    setStage("mapping");
    setLoading(true);
    setStatus("Connecting...");

    if (eventSourceRef.current) eventSourceRef.current.close();

    try {
      const response = await fetch(`${API_BASE}/api/recommend`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ prompt: prompt.trim() }),
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      const processChunk = (chunk) => {
        buffer += chunk;
        const parts = buffer.split("\n\n");
        buffer = parts.pop(); // keep incomplete last part

        for (const part of parts) {
          const lines = part.trim().split("\n");
          let eventType = "message";
          let dataStr = "";

          for (const line of lines) {
            if (line.startsWith("event:")) eventType = line.slice(6).trim();
            if (line.startsWith("data:")) dataStr = line.slice(5).trim();
          }

          if (!dataStr) continue;

          try {
            const data = JSON.parse(dataStr);

            if (eventType === "status") {
              setStatus(data.message || "");
              if (data.stage) setStage(data.stage);
              if (data.targets) setTargets(data.targets.map(t => ({ label: t, rationale: "" })));
            }

            if (eventType === "results") {
              setListings(data.listings || []);
              setTargets(data.targets || []);
              setStage("complete");
              setLoading(false);
            }

            if (eventType === "error") {
              setError(data.message || "Something went wrong.");
              setLoading(false);
              setStage("");
            }
          } catch {
            // ignore malformed SSE chunks
          }
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        processChunk(decoder.decode(value, { stream: true }));
      }

      setLoading(false);

    } catch (err) {
      setError(err.message || "Failed to connect to the server.");
      setLoading(false);
      setStage("");
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSearch();
    }
  };

  const handleExampleClick = (example) => {
    setPrompt(example);
    inputRef.current?.focus();
  };

  const handleClear = () => {
    setPrompt("");
    setListings([]);
    setTargets([]);
    setError("");
    setStatus("");
    setStage("");
    inputRef.current?.focus();
  };

  const stageLabel = {
    mapping:     "Understanding your requirements...",
    scraping:    "Searching all platforms simultaneously...",
    aggregating: "Ranking results...",
    complete:    "",
  }[stage] || "";

  return (
    <div className="min-h-screen bg-white">
      {/* ── Hero Header ───────────────────────────────────────────────── */}
      <div className="border-b border-neutral-100 bg-neutral-950 text-white">
        <div className="max-w-3xl mx-auto px-4 py-10">
          <div className="flex items-center gap-2 mb-3">
            <Sparkles className="w-5 h-5 text-yellow-400" />
            <span className="text-xs font-medium tracking-widest uppercase text-neutral-400">
              AI Matchmaker
            </span>
          </div>
          <h1 className="text-3xl font-bold mb-2">
            What kind of car do you need?
          </h1>
          <p className="text-neutral-400 text-sm leading-relaxed">
            Describe features, budget, lifestyle — not make and model.
            Our AI maps your needs to the right cars and searches every platform at once.
          </p>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-4 py-8">

        {/* ── Input Area ─────────────────────────────────────────────── */}
        <div className="relative mb-4">
          <textarea
            ref={inputRef}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder='e.g. "AWD crossover with sunroof under 80 lacs in Lahore"'
            rows={3}
            disabled={loading}
            className="w-full px-4 py-3 pr-24 bg-neutral-50 border border-neutral-200 rounded-xl
                       text-sm text-neutral-900 placeholder-neutral-400 resize-none
                       focus:outline-none focus:border-neutral-900 focus:bg-white
                       transition-colors disabled:opacity-50"
          />
          <div className="absolute bottom-3 right-3 flex items-center gap-2">
            {prompt && !loading && (
              <button
                onClick={handleClear}
                className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            )}
            <button
              onClick={handleSearch}
              disabled={!prompt.trim() || loading}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-neutral-950 text-white
                         text-xs font-medium rounded-lg disabled:opacity-40
                         hover:bg-neutral-800 active:scale-95 transition-all"
            >
              <Search className="w-3.5 h-3.5" />
              Search
            </button>
          </div>
        </div>

        {/* ── Example Prompts ────────────────────────────────────────── */}
        {!loading && listings.length === 0 && !error && (
          <div className="mb-8">
            <p className="text-xs text-neutral-400 mb-2 uppercase tracking-wide font-medium">
              Try an example
            </p>
            <div className="flex flex-wrap gap-2">
              {EXAMPLE_PROMPTS.map((ex) => (
                <button
                  key={ex}
                  onClick={() => handleExampleClick(ex)}
                  className="flex items-center gap-1 px-3 py-1.5 bg-neutral-50 border border-neutral-200
                             text-xs text-neutral-600 rounded-full hover:bg-neutral-100
                             hover:border-neutral-300 transition-colors"
                >
                  <ChevronRight className="w-3 h-3 text-neutral-400" />
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── Loading State ──────────────────────────────────────────── */}
        {loading && (
          <div className="mb-8">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-2 h-2 rounded-full bg-neutral-950 animate-pulse" />
              <span className="text-sm text-neutral-600">{status}</span>
            </div>

            {/* Stage progress bar */}
            <div className="h-1 bg-neutral-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-neutral-950 rounded-full transition-all duration-700"
                style={{
                  width: stage === "mapping" ? "25%" :
                         stage === "scraping" ? "60%" :
                         stage === "aggregating" ? "85%" : "100%"
                }}
              />
            </div>
            {stageLabel && (
              <p className="text-xs text-neutral-400 mt-2">{stageLabel}</p>
            )}

            {/* Show targets as they arrive */}
            {targets.length > 0 && (
              <div className="mt-4">
                <p className="text-xs text-neutral-400 mb-2 uppercase tracking-wide font-medium">
                  Searching for
                </p>
                <div className="flex flex-wrap gap-2">
                  {targets.map((t, i) => (
                    <span
                      key={i}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-neutral-100
                                 text-xs text-neutral-700 rounded-full"
                    >
                      <Car className="w-3 h-3" />
                      {typeof t === "string" ? t : `${t.make} ${t.model}`}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── Error State ────────────────────────────────────────────── */}
        {error && (
          <div className="mb-8 p-4 bg-red-50 border border-red-100 rounded-xl">
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {/* ── Results ────────────────────────────────────────────────── */}
        {listings.length > 0 && !loading && (
          <div>
            {/* What the AI searched for */}
            {targets.length > 0 && (
              <div className="mb-6 p-4 bg-neutral-50 border border-neutral-100 rounded-xl">
                <p className="text-xs font-medium text-neutral-500 uppercase tracking-wide mb-3">
                  AI matched your needs to
                </p>
                <div className="space-y-2">
                  {targets.map((t, i) => (
                    <div key={i} className="flex items-start gap-2">
                      <span className="flex-shrink-0 w-5 h-5 rounded-full bg-neutral-950 text-white
                                       text-xs flex items-center justify-center mt-0.5 font-medium">
                        {i + 1}
                      </span>
                      <div>
                        <span className="text-sm font-medium text-neutral-900">
                          {t.make} {t.model} {t.trim || ""}
                        </span>
                        {t.rationale && (
                          <p className="text-xs text-neutral-500 mt-0.5">{t.rationale}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-medium text-neutral-900">
                {listings.length} listings found
              </h2>
              <button
                onClick={handleClear}
                className="text-xs text-neutral-400 hover:text-neutral-700 transition-colors"
              >
                New search
              </button>
            </div>

            <div className="space-y-3">
              {listings.map((listing, idx) => (
                <div key={listing.listing_url || idx}>
                  {/* AI rationale badge if present */}
                  {listing.ai_rationale && (
                    <div className="flex items-center gap-1.5 mb-1.5 px-1">
                      <Sparkles className="w-3 h-3 text-yellow-500" />
                      <span className="text-xs text-neutral-500">{listing.ai_rationale}</span>
                    </div>
                  )}
                  <CarResultCard listing={listing} />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Empty State ────────────────────────────────────────────── */}
        {!loading && !error && listings.length === 0 && stage === "complete" && (
          <div className="text-center py-16 text-neutral-400">
            <Car className="w-10 h-10 mx-auto mb-3 opacity-30" />
            <p className="text-sm">No listings matched your requirements.</p>
            <p className="text-xs mt-1">Try broadening your budget or removing specific feature constraints.</p>
          </div>
        )}

      </div>
    </div>
  );
}
