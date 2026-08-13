import React, { useState } from 'react';
import { Helmet } from 'react-helmet-async';
import { motion } from 'framer-motion';
import DynamicBackground from '../components/DynamicBackground';

/* ═══════════════════════════════════════════════════════
   DATA CONSTANTS
   ═══════════════════════════════════════════════════════ */

const CC_OPTIONS = [
  { value: 800,  label: '800cc (e.g., Suzuki Alto)' },
  { value: 1000, label: '1000cc (e.g., Suzuki Cultus)' },
  { value: 1300, label: '1300cc (e.g., Toyota Yaris)' },
  { value: 1500, label: '1500cc (e.g., Honda Civic)' },
  { value: 1800, label: '1800cc (e.g., Toyota Grande)' },
  { value: 2500, label: '2500cc+ (e.g., Toyota Fortuner)' },
];

const PROVINCE_OPTIONS = [
  { value: 'Islamabad', label: 'Islamabad Capital Territory' },
  { value: 'Punjab',    label: 'Punjab' },
  { value: 'Sindh',     label: 'Sindh' },
  { value: 'KPK',       label: 'Khyber Pakhtunkhwa' },
  { value: 'Balochistan', label: 'Balochistan' },
];

/* ═══════════════════════════════════════════════════════
   SHARED ANIMATION — "Card Float" (scroll-linked lift)
   ═══════════════════════════════════════════════════════ */

const cardFloat = {
  rest: { y: 0, boxShadow: '8px 8px 0px 0px var(--brutal-shadow, #000000)' },
  float: { y: -14, boxShadow: '12px 14px 0px 0px var(--brutal-shadow, #000000)' },
};

const cardTransition = { type: 'spring', stiffness: 120, damping: 20, mass: 0.8 };

/* ═══════════════════════════════════════════════════════
   BRUTALIST UI PRIMITIVES
   ═══════════════════════════════════════════════════════ */

/** Brutalist Select Dropdown */
function BrutalSelect({ id, label, value, onChange, options }) {
  return (
    <div>
      <label htmlFor={id} className="block font-mono text-[10px] md:text-xs font-bold uppercase tracking-[0.14em] text-df-black/50 dark:text-zinc-50/50 mb-2">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={onChange}
        className="brutal-select w-full p-3 md:p-4 bg-df-white dark:bg-black border-2 border-df-black dark:border-white rounded-none outline-none font-mono text-sm md:text-base font-medium cursor-pointer appearance-none focus:ring-2 focus:ring-df-red focus:border-df-red transition-none text-df-black dark:text-zinc-50"
        style={{
          backgroundRepeat: 'no-repeat',
          backgroundPosition: 'right 16px center',
        }}
      >
        {options.map(opt => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>
    </div>
  );
}

/** Brutalist Square Radio Group */
function BrutalRadioGroup({ name, label, value, onChange, options }) {
  return (
    <div>
      <span className="block font-mono text-[10px] md:text-xs font-bold uppercase tracking-[0.14em] text-df-black/50 dark:text-zinc-50/50 mb-3">
        {label}
      </span>
      <div className="flex flex-wrap gap-3 md:gap-4">
        {options.map(opt => {
          const isSelected = value === opt.value;
          return (
            <label
              key={opt.value}
              className={`
                flex items-center gap-2.5 cursor-pointer px-4 py-3 border-2 border-df-black dark:border-white font-mono text-xs md:text-sm font-bold tracking-wide select-none transition-none
                ${isSelected ? 'bg-df-black dark:bg-white text-df-white dark:text-black' : 'bg-df-white dark:bg-black text-df-black dark:text-zinc-50 hover:bg-df-grey dark:hover:bg-zinc-800'}
              `}
            >
              <span className="inline-flex items-center justify-center w-5 h-5 border-2 border-current flex-shrink-0">
                {isSelected && (
                  <span className="block w-2.5 h-2.5 bg-current" />
                )}
              </span>
              <input
                type="radio"
                name={name}
                value={opt.value}
                checked={isSelected}
                onChange={() => onChange(opt.value)}
                className="sr-only"
              />
              {opt.label}
            </label>
          );
        })}
      </div>
    </div>
  );
}

/** Brutalist Range Slider */
function BrutalSlider({ id, label, value, onChange, min, max, unit }) {
  const pct = ((value - min) / (max - min)) * 100;

  return (
    <div>
      <div className="flex justify-between items-baseline mb-3">
        <label htmlFor={id} className="font-mono text-[10px] md:text-xs font-bold uppercase tracking-[0.14em] text-df-black/50 dark:text-zinc-50/50">
          {label}
        </label>
        <span className="font-mono text-sm md:text-base font-bold text-df-black dark:text-zinc-50 tabular-nums">
          {value} {unit}
        </span>
      </div>
      <div className="relative h-10 flex items-center">
        {/* Track background */}
        <div className="absolute inset-x-0 h-[3px] bg-df-black/15 dark:bg-zinc-50/15" />
        {/* Filled track */}
        <div
          className="absolute left-0 h-[3px] bg-df-black dark:bg-zinc-50"
          style={{ width: `${pct}%` }}
        />
        <input
          id={id}
          type="range"
          min={min}
          max={max}
          value={value}
          onChange={onChange}
          className="brutal-slider relative z-10 w-full cursor-pointer"
        />
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   MAIN COMPONENT
   ═══════════════════════════════════════════════════════ */

export default function CalculatorsHub() {
  // ── Section 1: Fuel Cost Estimator State ──
  const [fuelCc, setFuelCc] = useState(1000);
  const [fuelKm, setFuelKm] = useState(40);

  // ── Section 2: Token Tax Calculator State ──
  const [tokenProvince, setTokenProvince] = useState('Islamabad');
  const [tokenFiler, setTokenFiler] = useState(true);
  const [tokenCc, setTokenCc] = useState(1300);

  // ── Section 3: Transfer Fee Calculator State ──
  const [transferCc, setTransferCc] = useState(1300);
  const [buyerFiler, setBuyerFiler] = useState(true);
  const [sellerFiler, setSellerFiler] = useState(true);

  return (
    <>
      <Helmet>
        <title>Car Tax & Fuel Cost Calculators Pakistan | DriveFetch</title>
        <meta name="description" content="Calculate your vehicle's fuel cost, transfer fees, and token taxes accurately in Pakistan. Neo-Brutalist financial tools by DriveFetch." />
        <link rel="canonical" href="https://carfinderproject.vercel.app/calculators" />
      </Helmet>

      {/* ── Dynamic Background (scroll-linked, fixed behind content) ── */}
      <DynamicBackground />

      {/* ── Page Shell — transparent to show DynamicBackground ── */}
      <div className="relative z-10 min-h-screen">

        {/* ── Page Header ── */}
        <header className="pt-12 md:pt-20 pb-10 md:pb-14 px-4 md:px-6">
          <div className="max-w-3xl mx-auto">
            <p className="font-mono text-[10px] md:text-xs font-bold tracking-[0.14em] text-df-black/30 dark:text-zinc-50/30 mb-4 uppercase">
              [ SYS // FINANCIAL_TOOLS ]
            </p>
            <h1 className="text-display-lg text-df-black dark:text-zinc-50 mb-4">
              Calculators
            </h1>
            <p className="font-body text-base md:text-lg text-df-black/55 dark:text-zinc-50/55 font-medium max-w-xl leading-relaxed">
              Calculate <span className="text-[#E5202E] font-bold">exact</span> running costs, taxes, and transfer fees before you buy. All figures based on latest FBR & Excise data.
            </p>
          </div>
        </header>

        {/* ── Calculator Sections — Vertical Stack ── */}
        <div className="px-4 md:px-6 pb-16 md:pb-24 space-y-16 md:space-y-24">

          {/* ═══════════════════════════════════════════
             SECTION 1: FUEL COST ESTIMATOR
             ═══════════════════════════════════════════ */}
          <motion.section
            variants={cardFloat}
            initial="rest"
            whileInView="float"
            viewport={{ once: false, amount: 0.3 }}
            transition={cardTransition}
            className="group max-w-3xl mx-auto bg-white dark:bg-black border-2 border-df-black dark:border-white transition-all duration-200 hover:border-[#E5202E] hover:ring-2 hover:ring-[#E5202E] focus-within:border-[#E5202E] focus-within:ring-2 focus-within:ring-[#E5202E]"
          >
              {/* Header Strip */}
              <div className="px-6 md:px-8 py-4 md:py-5 border-b-2 border-df-black dark:border-white transition-all duration-200 group-hover:border-b-[#E5202E] group-hover:border-b-4 group-focus-within:border-b-[#E5202E] group-focus-within:border-b-4 flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-1">
                <span className="font-mono text-[10px] md:text-xs font-bold tracking-[0.1em] text-df-black/35 dark:text-zinc-50/35">
                  [ TOOL // 01 ]
                </span>
                <h2 className="font-display text-2xl md:text-3xl tracking-wide text-df-black dark:text-zinc-50 uppercase">
                  Fuel Cost Estimator
                </h2>
              </div>

              {/* Body */}
              <div className="px-6 md:px-8 py-6 md:py-8 space-y-6 md:space-y-8">
                <BrutalSelect
                  id="fuel-cc"
                  label="Engine Capacity"
                  value={fuelCc}
                  onChange={(e) => setFuelCc(Number(e.target.value))}
                  options={CC_OPTIONS}
                />

                <BrutalSlider
                  id="fuel-commute"
                  label="Daily Commute"
                  value={fuelKm}
                  onChange={(e) => setFuelKm(Number(e.target.value))}
                  min={5}
                  max={200}
                  unit="km"
                />
              </div>

              {/* Output Box */}
              <div className="bg-df-black px-6 md:px-8 py-5 md:py-6">
                <p className="font-mono text-[10px] md:text-xs font-bold tracking-[0.14em] text-white/40 uppercase mb-1.5">
                  Est. Monthly Cost
                </p>
                <p className="font-mono text-2xl md:text-3xl font-bold text-white tracking-tight">
                  EST. MONTHLY COST: -- PKR
                </p>
              </div>
          </motion.section>

          {/* ═══════════════════════════════════════════
             SECTION 2: TOKEN TAX CALCULATOR
             ═══════════════════════════════════════════ */}
          <motion.section
            variants={cardFloat}
            initial="rest"
            whileInView="float"
            viewport={{ once: false, amount: 0.3 }}
            transition={cardTransition}
            className="group max-w-3xl mx-auto bg-white dark:bg-black border-2 border-df-black dark:border-white transition-all duration-200 hover:border-[#E5202E] hover:ring-2 hover:ring-[#E5202E] focus-within:border-[#E5202E] focus-within:ring-2 focus-within:ring-[#E5202E]"
          >
              {/* Header Strip */}
              <div className="px-6 md:px-8 py-4 md:py-5 border-b-2 border-df-black dark:border-white transition-all duration-200 group-hover:border-b-[#E5202E] group-hover:border-b-4 group-focus-within:border-b-[#E5202E] group-focus-within:border-b-4 flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-1">
                <span className="font-mono text-[10px] md:text-xs font-bold tracking-[0.1em] text-df-black/35 dark:text-zinc-50/35">
                  [ TOOL // 02 ]
                </span>
                <h2 className="font-display text-2xl md:text-3xl tracking-wide text-df-black dark:text-zinc-50 uppercase">
                  Token Tax Calculator
                </h2>
              </div>

              {/* Body */}
              <div className="px-6 md:px-8 py-6 md:py-8 space-y-6 md:space-y-8">
                <BrutalSelect
                  id="token-province"
                  label="Region / Province"
                  value={tokenProvince}
                  onChange={(e) => setTokenProvince(e.target.value)}
                  options={PROVINCE_OPTIONS}
                />

                <BrutalRadioGroup
                  name="tokenFiler"
                  label="Filer Status"
                  value={tokenFiler}
                  onChange={(val) => setTokenFiler(val)}
                  options={[
                    { value: true,  label: 'Active Filer' },
                    { value: false, label: 'Non-Filer' },
                  ]}
                />

                <BrutalSelect
                  id="token-cc"
                  label="Engine Capacity"
                  value={tokenCc}
                  onChange={(e) => setTokenCc(Number(e.target.value))}
                  options={CC_OPTIONS}
                />
              </div>

              {/* Output Box */}
              <div className="bg-df-black px-6 md:px-8 py-5 md:py-6">
                <p className="font-mono text-[10px] md:text-xs font-bold tracking-[0.14em] text-white/40 uppercase mb-1.5">
                  Annual Token Tax
                </p>
                <p className="font-mono text-2xl md:text-3xl font-bold text-white tracking-tight">
                  ANNUAL TAX: -- PKR
                </p>
              </div>
          </motion.section>

          {/* ═══════════════════════════════════════════
             SECTION 3: TRANSFER FEE CALCULATOR
             ═══════════════════════════════════════════ */}
          <motion.section
            variants={cardFloat}
            initial="rest"
            whileInView="float"
            viewport={{ once: false, amount: 0.3 }}
            transition={cardTransition}
            className="group max-w-3xl mx-auto bg-white dark:bg-black border-2 border-df-black dark:border-white transition-all duration-200 hover:border-[#E5202E] hover:ring-2 hover:ring-[#E5202E] focus-within:border-[#E5202E] focus-within:ring-2 focus-within:ring-[#E5202E]"
          >
              {/* Header Strip */}
              <div className="px-6 md:px-8 py-4 md:py-5 border-b-2 border-df-black dark:border-white transition-all duration-200 group-hover:border-b-[#E5202E] group-hover:border-b-4 group-focus-within:border-b-[#E5202E] group-focus-within:border-b-4 flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-1">
                <span className="font-mono text-[10px] md:text-xs font-bold tracking-[0.1em] text-df-black/35 dark:text-zinc-50/35">
                  [ TOOL // 03 ]
                </span>
                <h2 className="font-display text-2xl md:text-3xl tracking-wide text-df-black dark:text-zinc-50 uppercase">
                  Transfer Fee Calculator
                </h2>
              </div>

              {/* Body */}
              <div className="px-6 md:px-8 py-6 md:py-8 space-y-6 md:space-y-8">
                <BrutalSelect
                  id="transfer-cc"
                  label="Vehicle Type / Capacity"
                  value={transferCc}
                  onChange={(e) => setTransferCc(Number(e.target.value))}
                  options={CC_OPTIONS}
                />

                <BrutalRadioGroup
                  name="buyerFiler"
                  label="Buyer Filer Status"
                  value={buyerFiler}
                  onChange={(val) => setBuyerFiler(val)}
                  options={[
                    { value: true,  label: 'Active Filer' },
                    { value: false, label: 'Non-Filer' },
                  ]}
                />

                <BrutalRadioGroup
                  name="sellerFiler"
                  label="Seller Filer Status"
                  value={sellerFiler}
                  onChange={(val) => setSellerFiler(val)}
                  options={[
                    { value: true,  label: 'Active Filer' },
                    { value: false, label: 'Non-Filer' },
                  ]}
                />
              </div>

              {/* Output Box — Monospace Receipt Layout */}
              <div className="bg-df-black px-6 md:px-8 py-5 md:py-6">
                <p className="font-mono text-[10px] md:text-xs font-bold tracking-[0.14em] text-white/40 uppercase mb-3">
                  Transfer Fee Breakdown
                </p>
                <div className="font-mono text-sm md:text-base text-white/80 space-y-1.5 leading-relaxed">
                  <p>&gt; EXCISE FEE: <span className="text-white font-bold">-- PKR</span></p>
                  <p>&gt; WITHHOLDING TAX: <span className="text-white font-bold">-- PKR</span></p>
                  <p>&gt; STAMP DUTY: <span className="text-white font-bold">-- PKR</span></p>
                  <div className="border-t border-white/20 my-2 pt-2">
                    <p className="text-white font-bold text-lg md:text-xl">&gt; TOTAL: -- PKR</p>
                  </div>
                </div>
              </div>
          </motion.section>

        </div>
      </div>

      {/* ── Custom Slider Styles ── */}
      <style>{`
        :root {
          --brutal-shadow: #000000;
        }
        .dark {
          --brutal-shadow: #ffffff;
        }
        
        .brutal-select {
          background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M2 4l4 4 4-4' fill='none' stroke='%23000' stroke-width='2'/%3E%3C/svg%3E");
        }
        .dark .brutal-select {
          background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M2 4l4 4 4-4' fill='none' stroke='%23fff' stroke-width='2'/%3E%3C/svg%3E");
        }

        /* Reset native slider appearance */
        .brutal-slider {
          -webkit-appearance: none;
          appearance: none;
          background: transparent;
          height: 40px;
          margin: 0;
        }

        /* Webkit Track (invisible — we draw custom track above) */
        .brutal-slider::-webkit-slider-runnable-track {
          height: 3px;
          background: transparent;
          border: none;
        }

        /* Webkit Thumb — Heavy red square */
        .brutal-slider::-webkit-slider-thumb {
          -webkit-appearance: none;
          appearance: none;
          width: 20px;
          height: 20px;
          background: #E5202E;
          border: 2px solid var(--brutal-shadow);
          border-radius: 0;
          cursor: pointer;
          margin-top: -9px;
          box-shadow: 2px 2px 0px 0px var(--brutal-shadow);
          transition: box-shadow 0.1s;
        }
        .brutal-slider::-webkit-slider-thumb:hover {
          box-shadow: 3px 3px 0px 0px var(--brutal-shadow);
        }
        .brutal-slider::-webkit-slider-thumb:active {
          box-shadow: 1px 1px 0px 0px var(--brutal-shadow);
          transform: translate(1px, 1px);
        }

        /* Firefox Track */
        .brutal-slider::-moz-range-track {
          height: 3px;
          background: transparent;
          border: none;
        }

        /* Firefox Thumb */
        .brutal-slider::-moz-range-thumb {
          width: 20px;
          height: 20px;
          background: #E5202E;
          border: 2px solid var(--brutal-shadow);
          border-radius: 0;
          cursor: pointer;
          box-shadow: 2px 2px 0px 0px var(--brutal-shadow);
        }
        .brutal-slider::-moz-range-thumb:hover {
          box-shadow: 3px 3px 0px 0px var(--brutal-shadow);
        }

        /* Focus Ring */
        .brutal-slider:focus {
          outline: none;
        }
        .brutal-slider:focus-visible::-webkit-slider-thumb {
          outline: 2px solid #E5202E;
          outline-offset: 2px;
        }
        .brutal-slider:focus-visible::-moz-range-thumb {
          outline: 2px solid #E5202E;
          outline-offset: 2px;
        }
      `}</style>
    </>
  );
}