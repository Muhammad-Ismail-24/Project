/**
 * src/pages/RecommendPage.jsx
 *
 * The AI Matchmaker page — feature-based car search.
 * Theme matched with GaariGuru studio design (#b0b0b0 metallic glassmorphism).
 */

import React, { useState, useRef, useEffect } from "react";
import { Sparkles, Search, X, ChevronRight, Car, Loader2, AlertCircle } from "lucide-react";
import CarResultCard from "../components/CarResultCard";

const API_BASE = import.meta.env.VITE_API_URL || "";

// Example prompts
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
  const [status, setStatus]       = useState("");   
  const [stage, setStage]         = useState("");   
  const [targets, setTargets]     = useState([]);   
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

    setListings([]);
    setTargets([]);
    setError("");
    setStage("mapping");
    setLoading(true);
    setStatus("Connecting to AI Engine...");

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
        buffer = parts.pop();

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
    mapping:     "AI mapping requirements to target models...",
    scraping:    "Searching PakWheels, OLX, Gari & WiseWheels in parallel...",
    aggregating: "Scoring & deduplicating market matches...",
    complete:    "",
  }[stage] || "";

  return (
    <div className="relative min-h-screen w-full overflow-x-hidden font-sans text-black">

      {/* ── Background: metallic grey studio, white key light, subtle grid ── */}
      <div className="fixed inset-0 z-[-1] pointer-events-none overflow-hidden bg-[#b0b0b0]">
        <div
          className="absolute inset-0"
          style={{
            backgroundImage:
              'linear-gradient(to right,rgba(0,0,0,0.06) 1px,transparent 1px),' +
              'linear-gradient(to bottom,rgba(0,0,0,0.06) 1px,transparent 1px)',
            backgroundSize: '72px 72px',
          }}
        />
        <div className="absolute w-[75vw] h-[75vw] max-w-[1100px] max-h-[1100px] bg-white rounded-full blur-[160px] opacity-35 top-[-10%] right-[-12%]" />
        <div className="absolute w-[40vw] h-[40vw] max-w-[600px] max-h-[600px] bg-white rounded-full blur-[120px] opacity-15 bottom-[5%] left-[-5%]" />
        <div
          className="absolute inset-0"
          style={{ background: 'radial-gradient(ellipse at 60% 40%, transparent 40%, rgba(0,0,0,0.18) 100%)' }}
        />
      </div>

      <div className="relative z-10 max-w-4xl mx-auto px-6 pt-16 pb-28">

        {/* ── Header ───────────────────────────────────────────────────── */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-black/80 text-white text-[10px] font-semibold tracking-[0.15em] uppercase mb-5">
            <Sparkles className="w-3.5 h-3.5 text-yellow-400" />
            GaariGuru AI Matchmaker
          </div>
          <h1 className="text-4xl md:text-5xl font-black tracking-tight text-black mb-3">
            What kind of car do you need?
          </h1>
          <p className="text-base font-medium text-black/65 max-w-xl mx-auto leading-relaxed">
            Describe features, budget, or lifestyle — not just make and model. Our AI maps your requirements to matching vehicles and harvests live listings.
          </p>
        </div>

        {/* ── Input Glass Card ─────────────────────────────────────────── */}
        <div className="bg-white/55 backdrop-blur-xl border border-white/70 shadow-xl rounded-2xl p-6 md:p-8 mb-8">
          <div className="relative">
            <textarea
              ref={inputRef}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder='e.g. "AWD crossover with panoramic sunroof under 80 lacs in Lahore"'
              rows={3}
              disabled={loading}
              className="w-full px-4 py-3.5 pr-28 bg-white/60 border border-black/10 rounded-xl
                         text-sm font-medium text-black placeholder-black/40 resize-none
                         focus:outline-none focus:border-black/30 focus:bg-white/80 focus:ring-1 focus:ring-black/10
                         transition-all disabled:opacity-50"
            />
            <div className="absolute bottom-3 right-3 flex items-center gap-2">
              {prompt && !loading && (
                <button
                  onClick={handleClear}
                  className="p-2 rounded-xl text-black/40 hover:text-black hover:bg-black/5 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
              <button
                onClick={handleSearch}
                disabled={!prompt.trim() || loading}
                className="flex items-center gap-2 px-5 py-2.5 bg-black text-white
                           text-xs font-semibold rounded-xl disabled:opacity-40
                           hover:bg-neutral-800 active:scale-95 transition-all shadow-md"
              >
                <Search className="w-3.5 h-3.5" />
                Match
              </button>
            </div>
          </div>

          {/* ── Example Prompts Chips ───────────────────────────────────── */}
          {!loading && listings.length === 0 && !error && (
            <div className="mt-6 pt-5 border-t border-black/10">
              <p className="text-[10px] text-black/45 mb-3 uppercase tracking-widest font-semibold">
                Try an example requirement
              </p>
              <div className="flex flex-wrap gap-2">
                {EXAMPLE_PROMPTS.map((ex) => (
                  <button
                    key={ex}
                    onClick={() => handleExampleClick(ex)}
                    className="flex items-center gap-1.5 px-3.5 py-1.5 bg-black/8 hover:bg-black/15
                               text-xs font-medium text-black/80 rounded-full border border-black/10
                               backdrop-blur-sm transition-all text-left"
                  >
                    <ChevronRight className="w-3 h-3 text-black/40 shrink-0" />
                    {ex}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ── Loading State ──────────────────────────────────────────── */}
        {loading && (
          <div className="bg-white/50 backdrop-blur-xl border border-white/60 shadow-lg rounded-2xl p-6 md:p-8 mb-8">
            <div className="flex items-center gap-3 mb-4">
              <Loader2 className="w-5 h-5 text-black/70 animate-spin" />
              <span className="text-sm font-semibold text-black/80">{status}</span>
            </div>

            {/* Stage progress bar */}
            <div className="h-1.5 bg-black/10 rounded-full overflow-hidden">
              <div
                className="h-full bg-black rounded-full transition-all duration-700"
                style={{
                  width: stage === "mapping" ? "25%" :
                         stage === "scraping" ? "65%" :
                         stage === "aggregating" ? "88%" : "100%"
                }}
              />
            </div>
            {stageLabel && (
              <p className="text-xs font-medium text-black/50 mt-2.5">{stageLabel}</p>
            )}

            {/* Target badges as they arrive */}
            {targets.length > 0 && (
              <div className="mt-5 pt-4 border-t border-black/10">
                <p className="text-[10px] text-black/45 mb-2.5 uppercase tracking-widest font-semibold">
                  AI Recommended Target Models
                </p>
                <div className="flex flex-wrap gap-2">
                  {targets.map((t, i) => (
                    <span
                      key={i}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-black text-white
                                 text-xs font-medium rounded-full shadow-sm"
                    >
                      <Car className="w-3.5 h-3.5 text-white/70" />
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
          <div className="mb-8 flex items-center gap-3 bg-white/50 backdrop-blur-md border border-black/10 text-black/80 p-5 rounded-2xl shadow-sm">
            <AlertCircle className="w-5 h-5 shrink-0 text-black/40" />
            <p className="text-sm font-medium">{error}</p>
          </div>
        )}

        {/* ── Results ────────────────────────────────────────────────── */}
        {listings.length > 0 && !loading && (
          <div className="space-y-6">
            
            {/* AI Target Breakdown Panel */}
            {targets.length > 0 && (
              <div className="bg-white/60 backdrop-blur-xl border border-white/70 shadow-md rounded-2xl p-6">
                <p className="text-xs font-bold text-black/60 uppercase tracking-widest mb-4 flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-yellow-500" />
                  AI Market Recommendation Rationale
                </p>
                <div className="space-y-3">
                  {targets.map((t, i) => (
                    <div key={i} className="flex items-start gap-3 bg-white/50 p-3.5 rounded-xl border border-black/5">
                      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-black text-white
                                       text-xs font-bold flex items-center justify-center mt-0.5">
                        {i + 1}
                      </span>
                      <div>
                        <span className="text-sm font-bold text-black">
                          {t.make} {t.model} {t.trim || ""}
                        </span>
                        {t.rationale && (
                          <p className="text-xs font-medium text-black/60 mt-0.5 leading-relaxed">{t.rationale}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Results Counter Header */}
            <div className="flex items-center justify-between pt-2">
              <h2 className="text-lg font-bold text-black tracking-tight">
                {listings.length} Matched Listings
              </h2>
              <button
                onClick={handleClear}
                className="text-xs font-semibold text-black/50 hover:text-black transition-colors underline"
              >
                New AI Match
              </button>
            </div>

            {/* Cards List */}
            <div className="space-y-4">
              {listings.map((listing, idx) => (
                <div key={listing.listing_url || idx} className="space-y-1.5">
                  {/* AI rationale badge */}
                  {listing.ai_rationale && (
                    <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-black/80 text-white text-[11px] font-medium backdrop-blur-sm">
                      <Sparkles className="w-3 h-3 text-yellow-400" />
                      <span>{listing.ai_rationale}</span>
                    </div>
                  )}
                  <div className="rounded-2xl overflow-hidden border border-black/10 shadow-md bg-white/60 backdrop-blur-sm">
                    <CarResultCard car={listing} listing={listing} userQuery={prompt} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Empty State ────────────────────────────────────────────── */}
        {!loading && !error && listings.length === 0 && stage === "complete" && (
          <div className="text-center py-16 bg-white/40 backdrop-blur-md rounded-2xl border border-black/8">
            <Car className="w-10 h-10 mx-auto mb-3 text-black/30" />
            <p className="text-sm font-semibold text-black/70">No listings matched your exact criteria.</p>
            <p className="text-xs font-medium text-black/50 mt-1">Try broadening your budget or removing specific feature constraints.</p>
          </div>
        )}

      </div>
    </div>
  );
}