import React, { useState } from 'react';
import { Sparkles, ShieldAlert, ShieldCheck, ScanLine } from 'lucide-react';

// ─────────────────────────────────────────────────────────────────────────────
// RiskScanDemo — an interactive proof-of-product.
//
// A real-looking Pakistani listing description. Hit "Run AI scan" and DriveFetch's
// eye lights up the loaded phrases (danger/warning) and the genuine signals
// (good), with a reason for each. Hovering a phrase or a legend row links the
// pair. This is the pitch, made playable — not a static paragraph.
// ─────────────────────────────────────────────────────────────────────────────

// tone: 'danger' | 'warn' | 'good' | null (plain text)
const SEGMENTS = [
  { t: '2019 Honda Civic Oriel, first owner, ' },
  { t: 'genuine bumper-to-bumper', tone: 'good', why: 'Original paint — no accident repair claimed' },
  { t: '. Recently ' },
  { t: 'showered for fresh look', tone: 'danger', why: 'A quick respray often hides panel damage or rust' },
  { t: ' and ' },
  { t: 'minor touch-ups', tone: 'warn', why: 'Localised paint — inspect for prior dents' },
  { t: ' on the rear door. Papers are ' },
  { t: 'duplicate file', tone: 'danger', why: 'Lost original book — verify it is not stolen/on lien' },
  { t: '. ' },
  { t: 'Urgent sale', tone: 'warn', why: 'Pressure tactic — price is negotiable, don’t rush' },
  { t: ' due to migration. Engine ' },
  { t: 'total genuine', tone: 'good', why: 'Seller claims untouched drivetrain — confirm on inspection' },
  { t: '.' },
];

const toneClass = { danger: 'risk-danger', warn: 'risk-warn', good: 'risk-good' };

export default function RiskScanDemo() {
  const [scanned, setScanned] = useState(false);
  const [hover, setHover] = useState(-1);

  const flagged = SEGMENTS.map((s, i) => ({ ...s, i })).filter((s) => s.tone);
  const dangerCount = flagged.filter((s) => s.tone === 'danger').length;
  const warnCount = flagged.filter((s) => s.tone === 'warn').length;
  const goodCount = flagged.filter((s) => s.tone === 'good').length;

  return (
    <div className="glass p-6 md:p-8 w-full">
      {/* Header + toggle */}
      <div className="flex items-start justify-between gap-4 mb-5">
        <div>
          <div className="inline-flex items-center gap-2 text-[10px] font-bold tracking-[0.16em] uppercase text-text-dim mb-2">
            <span className="live-dot" />
            Live listing · PakWheels
          </div>
          <h3 className="font-display text-xl md:text-2xl font-black tracking-tight text-text">
            Watch the AI read between the lines
          </h3>
        </div>
        <button
          onClick={() => setScanned((v) => !v)}
          className={`tile-press shrink-0 inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition-all ${
            scanned
              ? 'bg-accent text-white shadow-[0_10px_30px_-8px_var(--df-accent-glow)]'
              : 'btn-primary'
          }`}
        >
          {scanned ? <ScanLine className="w-4 h-4" /> : <Sparkles className="w-4 h-4" />}
          {scanned ? 'Reset' : 'Run AI scan'}
        </button>
      </div>

      {/* The listing copy */}
      <p className="text-[15px] md:text-base leading-8 text-text-dim font-medium">
        {SEGMENTS.map((seg, i) =>
          seg.tone ? (
            <span
              key={i}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(-1)}
              className={`risk-seg ${scanned ? toneClass[seg.tone] : ''} ${
                scanned && hover === i ? 'is-active' : ''
              }`}
            >
              {seg.t}
            </span>
          ) : (
            <span key={i}>{seg.t}</span>
          )
        )}
      </p>

      {/* Verdict + legend — appears after scan */}
      <div
        className="grid transition-all duration-500 ease-out"
        style={{ gridTemplateRows: scanned ? '1fr' : '0fr', opacity: scanned ? 1 : 0 }}
      >
        <div className="overflow-hidden">
          <div className="mt-6 pt-5" style={{ borderTop: '1px solid var(--df-glass-border)' }}>
            {/* Verdict chips */}
            <div className="flex flex-wrap items-center gap-2.5 mb-4">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-danger/30 bg-danger/10 px-3 py-1 text-xs font-bold text-danger">
                <ShieldAlert className="w-3.5 h-3.5" /> {dangerCount} red flags
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-warn/30 bg-warn/10 px-3 py-1 text-xs font-bold text-warn">
                {warnCount} cautions
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-good/30 bg-good/10 px-3 py-1 text-xs font-bold text-good">
                <ShieldCheck className="w-3.5 h-3.5" /> {goodCount} green signals
              </span>
            </div>

            {/* Reasons */}
            <ul className="space-y-2">
              {flagged.map((seg) => (
                <li
                  key={seg.i}
                  onMouseEnter={() => setHover(seg.i)}
                  onMouseLeave={() => setHover(-1)}
                  className={`flex items-start gap-3 rounded-xl px-3 py-2 transition-colors ${
                    hover === seg.i ? 'bg-white/5' : ''
                  }`}
                >
                  <span
                    className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                      seg.tone === 'danger' ? 'bg-danger' : seg.tone === 'warn' ? 'bg-warn' : 'bg-good'
                    }`}
                  />
                  <span className="text-sm text-text-dim font-medium leading-relaxed">
                    <span className="text-text font-semibold">“{seg.t.trim()}”</span> — {seg.why}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      {!scanned && (
        <p className="mt-5 text-xs font-medium text-text-faint">
          Every listing DriveFetch surfaces is scanned like this — before you waste a call.
        </p>
      )}
    </div>
  );
}
