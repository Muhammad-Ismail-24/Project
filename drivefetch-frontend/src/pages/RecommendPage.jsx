import React, { useState, useRef, useEffect } from "react";
import { Helmet } from "react-helmet-async";
import { Sparkles, Search, X, ChevronRight, Car, Loader2, AlertCircle, Plus, CheckCircle2 } from "lucide-react";
import CarResultCard from "../components/CarResultCard";

const API_BASE = import.meta.env.VITE_API_URL || "";

// Example prompts
const EXAMPLE_PROMPTS = [
  "Family SUV under 80 Lacs in Lahore",
  "Fuel efficient hybrid for daily commute",
  "Japanese import hatchback under 35 Lacs",
  "AWD crossover with sunroof in Islamabad",
  "Sports feel under 40 lacs, no CNG",
  "Cheapest automatic car for new driver"
];

export default function RecommendPage() {
  const [prompt, setPrompt]       = useState("");
  const [status, setStatus]       = useState("");   
  const [stage, setStage]         = useState("");   
  const [targets, setTargets]     = useState([]);   
  const [listings, setListings]   = useState([]);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState("");
  const [extLoading, setExtLoading]     = useState(false);
  const [extTargets, setExtTargets]     = useState([]);
  const [extListings, setExtListings]   = useState([]);
  const [extDone, setExtDone]           = useState(false);
  const [strategyBrief, setStrategyBrief] = useState(null);
  const [showPrompts, setShowPrompts]     = useState(false);
  
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
    setExtTargets([]);
    setExtListings([]);
    setExtDone(false);
    setExtLoading(false);
    setStrategyBrief(null);
    setStatus("Connecting to AI Engine...");
    setShowPrompts(false);

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

            if (eventType === "strategy") {
              setStrategyBrief({
                summary: data.summary || "",
                disclaimers: data.disclaimers || [],
                targets: data.targets || [],
              });
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

  const handleClear = () => {
    setPrompt("");
    setListings([]);
    setTargets([]);
    setError("");
    setStatus("");
    setStage("");
    setExtTargets([]);
    setExtListings([]);
    setExtDone(false);
    setExtLoading(false);
    setStrategyBrief(null);
    setShowPrompts(false);
    inputRef.current?.focus();
  };

  const handleShowMore = async () => {
    if (extLoading || extDone) return;
    setExtLoading(true);

    const excludeModels = targets.map(t =>
      `${t.make || ""} ${t.model || ""}`.trim()
    ).filter(Boolean);

    try {
      const response = await fetch(`${API_BASE}/api/recommend/extend`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          prompt: prompt.trim(),
          exclude_models: excludeModels,
          city: "",
          max_budget: null,
        }),
      });

      if (!response.ok) throw new Error(`Server error: ${response.status}`);

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

            if (eventType === "extension_results") {
              setExtTargets(data.targets || []);
              setExtListings(data.listings || []);
            }

            if (eventType === "status" && data.stage === "complete") {
              setExtDone(true);
              setExtLoading(false);
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

      setExtLoading(false);
      setExtDone(true);
    } catch (err) {
      console.error("Extension error:", err);
      setExtLoading(false);
      setExtDone(true);
    }
  };

  const stageLabel = {
    mapping:     "[ AI MAPPING REQUIREMENTS TO TARGET MODELS... ]",
    scraping:    "[ SEARCHING PLATFORMS IN PARALLEL... ]",
    aggregating: "[ SCORING & DEDUPLICATING MARKET MATCHES... ]",
    complete:    "",
  }[stage] || "";

  return (
    <main className="relative w-full flex-grow flex flex-col font-body bg-white text-df-black selection:bg-df-black selection:text-df-white overflow-x-hidden">
      <Helmet>
        <title>AI Matchmaker | DriveFetch</title>
        <meta name="description" content="Let DriveFetch AI Matchmaker find the right used car for you. Give our AI your budget and requirements to search across all of Pakistan's top platforms." />
        <link rel="canonical" href="https://carfinderproject.vercel.app/recommend" />
      </Helmet>

      {/* Drafting Grid Background */}
      <div 
        className="absolute inset-0 z-0 bg-white"
        style={{
          backgroundImage: `
            linear-gradient(to right, #E5E5E5 1px, transparent 1px),
            linear-gradient(to bottom, #E5E5E5 1px, transparent 1px)
          `,
          backgroundSize: '40px 40px'
        }}
      />

      <div className="relative z-10 flex-1 w-full max-w-5xl mx-auto px-5 pt-16 pb-32 flex flex-col">
        {/* Header */}
        <div className="text-center mb-12 sm:mb-16 mt-8 sm:mt-12">
          <h1 className="inline-block text-3xl sm:text-5xl md:text-6xl font-extrabold tracking-tighter text-df-black uppercase">
            TELL US WHAT YOU NEED.<br />WE'LL FETCH THE REST.
          </h1>
        </div>

        {/* Input Console (Medium Sized Notepad) */}
        <div className="w-full max-w-3xl mx-auto relative z-10">
          <div className="relative bg-df-white border-2 border-df-black shadow-[8px_8px_0px_#000000] flex flex-col transition-all focus-within:border-[#E5202E] focus-within:ring-2 focus-within:ring-[#E5202E] focus-within:shadow-[12px_12px_0px_#000000]">
            {/* Notebook Lines Background via CSS */}
            <textarea
              ref={inputRef}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
              placeholder="E.g. A fuel efficient hybrid for my daily commute..."
              className="w-full min-h-[160px] p-5 sm:p-6 pb-20 bg-transparent font-mono text-base sm:text-lg text-df-black placeholder-df-black/30 resize-none focus:ring-0 focus:outline-none"
              style={{
                lineHeight: '32px',
                backgroundImage: 'linear-gradient(transparent, transparent 31px, rgba(0,0,0,0.08) 31px, rgba(0,0,0,0.08) 32px)',
                backgroundSize: '100% 32px',
                backgroundAttachment: 'local'
              }}
            />
            
            {/* Initiate Button pinned bottom right */}
            <div className="absolute bottom-4 right-4 flex items-center gap-2">
              {prompt && !loading && (
                <button
                  onClick={handleClear}
                  className="p-2 sm:p-2.5 bg-df-white border-2 border-df-black shadow-[2px_2px_0px_#000000] hover:bg-df-black hover:text-df-white transition-none active:translate-x-[2px] active:translate-y-[2px] active:shadow-none focus:outline-none"
                  aria-label="Clear input"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
              <button 
                onClick={handleSearch}
                disabled={!prompt.trim() || loading}
                className="bg-[#E5202E] text-white opacity-100 font-mono text-xs sm:text-sm font-bold tracking-[0.08em] px-5 sm:px-6 py-2.5 sm:py-3 border-2 border-df-black hover:bg-[#C41A25] transition-none focus:outline-none focus:ring-0 active:translate-y-[2px] active:translate-x-[2px] disabled:cursor-not-allowed shadow-[4px_4px_0px_#000000] active:shadow-none"
              >
                {loading ? '[ MATCHING... ]' : '[ INITIATE ]'}
              </button>
            </div>
          </div>

          {/* Suggestions Pop-Down */}
          {!loading && listings.length === 0 && !error && (
            <div className="mt-8 flex flex-col items-center">
              <button 
                onClick={() => setShowPrompts(!showPrompts)}
                className="font-mono text-[10px] sm:text-xs font-bold tracking-widest text-df-black uppercase bg-df-white border-2 border-df-black px-4 sm:px-5 py-2 hover:bg-df-black hover:text-df-white transition-none focus:outline-none shadow-[4px_4px_0px_#000000] active:translate-x-[2px] active:translate-y-[2px] active:shadow-none"
              >
                Show Example Prompts {showPrompts ? '▲' : '▼'}
              </button>
              
              {showPrompts && (
                <div className="mt-4 w-full max-w-lg bg-df-white border-2 border-df-black shadow-[6px_6px_0px_#000000] flex flex-col">
                  {EXAMPLE_PROMPTS.slice(0, 4).map((ex, idx) => (
                    <button
                      key={idx}
                      onClick={() => {
                        setPrompt(ex);
                        setShowPrompts(false);
                      }}
                      className="text-left font-mono text-xs sm:text-sm font-semibold tracking-wide text-df-black px-4 sm:px-6 py-3 sm:py-4 border-b-2 border-df-black last:border-b-0 hover:bg-df-black hover:text-df-white transition-none focus:outline-none"
                    >
                      {ex}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Loading State ── */}
        {loading && (
          <div className="w-full max-w-3xl mx-auto mt-10">
            <div className="bg-df-white border-2 border-df-black shadow-[6px_6px_0px_#000000] p-6 sm:p-8">
              <div className="flex items-center gap-4 mb-6">
                <Loader2 className="w-6 h-6 text-df-red animate-spin" />
                <span className="font-mono text-sm sm:text-base font-bold tracking-[0.06em] uppercase">
                  {status || "[ PROCESSING REQUEST... ]"}
                </span>
              </div>
              
              {/* Progress Bar Brutalist */}
              <div className="h-3 bg-df-grey border-2 border-df-black mb-3">
                <div 
                  className="h-full bg-df-red transition-all duration-700 border-r-2 border-df-black"
                  style={{
                    width: stage === "mapping" ? "25%" :
                           stage === "scraping" ? "65%" :
                           stage === "aggregating" ? "88%" : "100%"
                  }}
                />
              </div>
              {stageLabel && (
                <p className="font-mono text-[10px] sm:text-xs font-bold text-df-black/50 uppercase tracking-[0.05em]">
                  {stageLabel}
                </p>
              )}

              {/* Targets */}
              {targets.length > 0 && (
                <div className="mt-8 pt-6 border-t-2 border-df-black border-dashed">
                  <p className="font-mono text-[10px] font-bold text-df-black/50 mb-3 uppercase tracking-widest">
                    [ TARGET MODELS IDENTIFIED ]
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {targets.map((t, i) => (
                      <span key={i} className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-df-black text-df-white font-mono text-[10px] sm:text-xs font-bold uppercase shadow-[2px_2px_0px_#E5202E]">
                        <Car className="w-3.5 h-3.5 text-df-red" />
                        {typeof t === "string" ? t : t.label ? t.label : `${t.make ?? ''} ${t.model ?? ''}`.trim()}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Error State ── */}
        {error && (
          <div className="w-full max-w-3xl mx-auto mt-10">
            <div className="bg-df-white border-2 border-df-black shadow-[6px_6px_0px_#E5202E] p-5 flex items-center gap-3 text-df-black">
              <AlertCircle className="w-6 h-6 text-df-red shrink-0" />
              <p className="font-mono text-sm font-bold tracking-wide uppercase">{error}</p>
            </div>
          </div>
        )}

        {/* ── Strategy Brief Card ── */}
        {strategyBrief && !loading && listings.length === 0 && (
          <div className="w-full max-w-3xl mx-auto mt-10" style={{ animation: 'fadeSlideUp 0.3s ease-out both' }}>
             <div className="bg-df-white border-2 border-df-black shadow-[8px_8px_0px_#000000] p-6 sm:p-8">
                <div className="flex items-center gap-3 mb-4 pb-4 border-b-2 border-df-black">
                  <span className="w-8 h-8 bg-df-black text-df-white font-mono flex items-center justify-center font-bold text-sm">
                    SYS
                  </span>
                  <h3 className="font-mono text-sm sm:text-base font-bold tracking-[0.08em] uppercase">
                    [ MATCHMAKER STRATEGY ]
                  </h3>
                </div>
                
                {strategyBrief.summary && (
                  <p className="font-body text-sm sm:text-base font-medium leading-relaxed mb-6">
                    {strategyBrief.summary}
                  </p>
                )}
                
                {strategyBrief.disclaimers && strategyBrief.disclaimers.length > 0 && (
                  <div className="space-y-3">
                    {strategyBrief.disclaimers.map((warning, idx) => (
                      <div key={idx} className="bg-yellow-300 border-2 border-df-black p-3 sm:p-4 text-xs sm:text-sm font-bold uppercase flex items-start gap-3">
                        <AlertCircle className="w-5 h-5 shrink-0" />
                        <span className="mt-0.5">{warning}</span>
                      </div>
                    ))}
                  </div>
                )}
             </div>
          </div>
        )}

        {/* ── Results ── */}
        {listings.length > 0 && !loading && (
          <div className="w-full max-w-4xl mx-auto mt-12 space-y-12">
            
            {/* AI Target Breakdown Panel */}
            {targets.length > 0 && (
              <div className="bg-df-white border-2 border-df-black shadow-[8px_8px_0px_#000000] p-6 sm:p-8">
                <p className="font-mono text-xs sm:text-sm font-bold text-df-black uppercase tracking-widest mb-6 flex items-center gap-3">
                  <Sparkles className="w-5 h-5 text-df-red" />
                  [ RATIONALE & RECOMMENDATIONS ]
                </p>
                <div className="space-y-4">
                  {targets.map((t, i) => (
                    <div key={i} className="flex flex-col sm:flex-row items-start gap-4 p-4 sm:p-5 border-2 border-df-black bg-df-grey">
                      <span className="w-8 h-8 bg-df-black text-df-white font-mono flex items-center justify-center font-bold shrink-0">
                        {String(i + 1).padStart(2, '0')}
                      </span>
                      <div>
                        <span className="font-mono text-sm sm:text-base font-bold text-df-black uppercase tracking-wide block mb-1.5">
                          {t.label ? t.label : `${t.make ?? ''} ${t.model ?? ''} ${t.trim ?? ''}`.trim()}
                        </span>
                        {t.rationale && (
                          <p className="font-body text-xs sm:text-sm font-medium text-df-black/70 leading-relaxed">{t.rationale}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Show More Options Button */}
                {!extDone && (
                  <div className="mt-8">
                    <button
                      onClick={handleShowMore}
                      disabled={extLoading}
                      className="w-full flex items-center justify-center gap-3 px-6 py-4 bg-df-black text-df-white font-mono text-sm font-bold uppercase border-2 border-df-black hover:bg-df-white hover:text-df-black transition-none focus:outline-none shadow-[4px_4px_0px_#E5202E] hover:shadow-none active:translate-y-[2px] active:translate-x-[2px] disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {extLoading ? (
                        <>
                          <Loader2 className="w-5 h-5 animate-spin" />
                          [ FINDING MORE... ]
                        </>
                      ) : (
                        <>
                          <Plus className="w-5 h-5 text-df-red" />
                          [ EXPLORE ADDITIONAL OPTIONS ]
                        </>
                      )}
                    </button>
                  </div>
                )}
                
                {/* Extension Rationale Cards */}
                {extTargets.length > 0 && (
                  <div className="mt-8 pt-8 border-t-2 border-df-black">
                     <p className="font-mono text-xs sm:text-sm font-bold text-df-black uppercase tracking-widest mb-6 flex items-center gap-3">
                       <Plus className="w-5 h-5 text-df-red" />
                       [ SECONDARY RECOMMENDATIONS ]
                     </p>
                     <div className="space-y-4">
                       {extTargets.map((t, i) => (
                         <div key={`ext-${i}`} className="flex flex-col sm:flex-row items-start gap-4 p-4 sm:p-5 border-2 border-df-black border-dashed bg-df-grey/50">
                           <span className="w-8 h-8 bg-df-white text-df-black border-2 border-df-black font-mono flex items-center justify-center font-bold shrink-0">
                             {String(targets.length + i + 1).padStart(2, '0')}
                           </span>
                           <div>
                             <span className="font-mono text-sm sm:text-base font-bold text-df-black uppercase tracking-wide block mb-1.5">
                               {t.label ? t.label : `${t.make ?? ''} ${t.model ?? ''} ${t.trim ?? ''}`.trim()}
                             </span>
                             {t.rationale && (
                               <p className="font-body text-xs sm:text-sm font-medium text-df-black/70 leading-relaxed">{t.rationale}</p>
                             )}
                           </div>
                         </div>
                       ))}
                     </div>
                  </div>
                )}
              </div>
            )}

            {/* Results Header */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b-4 border-df-black pb-4 gap-4">
              <h2 className="font-mono text-xl sm:text-3xl font-black text-df-black tracking-tight uppercase">
                [ {listings.length} LISTINGS RETRIEVED ]
              </h2>
              <button
                onClick={handleClear}
                className="font-mono text-xs font-bold uppercase tracking-widest text-df-black hover:bg-df-black hover:text-df-white px-4 py-2 border-2 border-transparent hover:border-df-black transition-none"
              >
                [ NEW QUERY ]
              </button>
            </div>

            {/* Cards List */}
            <div className="space-y-8 sm:space-y-10">
              {listings.map((listing, idx) => (
                <div key={listing.listing_url || idx} className="space-y-3">
                  {listing.ai_rationale && (
                    <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-df-white border-2 border-df-black shadow-[3px_3px_0px_#000000] font-mono text-[10px] sm:text-xs font-bold uppercase">
                      <Sparkles className="w-3.5 h-3.5 text-df-red" />
                      {listing.ai_rationale}
                    </div>
                  )}
                  <div className="bg-df-white border-2 border-df-black shadow-[8px_8px_0px_#000000]">
                    <CarResultCard car={listing} listing={listing} userQuery={prompt} />
                  </div>
                </div>
              ))}
            </div>

            {/* Extension Listings */}
            {extListings.length > 0 && (
              <div className="mt-16 space-y-10">
                <div className="flex items-center gap-4">
                  <div className="h-1 flex-1 bg-df-black" />
                  <span className="font-mono text-base font-black text-df-black uppercase tracking-widest">
                    [ EXTENDED MATCHES ]
                  </span>
                  <div className="h-1 flex-1 bg-df-black" />
                </div>
                {extListings.map((listing, idx) => (
                  <div key={`ext-list-${listing.listing_url || idx}`} className="space-y-3">
                    {listing.ai_rationale && (
                      <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-df-white border-2 border-df-black border-dashed font-mono text-[10px] sm:text-xs font-bold uppercase">
                        <Plus className="w-3.5 h-3.5 text-df-red" />
                        {listing.ai_rationale}
                      </div>
                    )}
                    <div className="bg-df-white border-2 border-df-black border-dashed shadow-[6px_6px_0px_#000000]">
                      <CarResultCard car={listing} listing={listing} userQuery={prompt} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Empty State ── */}
        {!loading && !error && listings.length === 0 && stage === "complete" && (
          <div className="w-full max-w-3xl mx-auto mt-10">
             <div className="bg-df-white border-2 border-df-black shadow-[8px_8px_0px_#000000] p-10 text-center">
               <Car className="w-12 h-12 mx-auto mb-4 text-df-black/30" />
               <p className="font-mono text-lg font-bold text-df-black uppercase tracking-wide mb-2">
                 [ ZERO MATCHES FOUND ]
               </p>
               <p className="font-body text-sm font-medium text-df-black/60">
                 Try broadening your budget or removing specific feature constraints.
               </p>
             </div>
          </div>
        )}

      </div>
    </main>
  );
}