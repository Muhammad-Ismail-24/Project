import React, { useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import DynamicBackground from '../components/DynamicBackground';
import SEO from '../components/SEO';
import { calculatorsSchema } from '../config/seoSchemas';
import { calculateFuelCost, calculateTokenTax, calculateTransferCost } from '../utils/calculatorEngine';

/* ═══════════════════════════════════════════════════════
   DATA CONSTANTS
   ═══════════════════════════════════════════════════════ */

// Values are the lookup keys into calculatorsConfig.json — 1801 is the sentinel
// for strong hybrids (they share a displacement band with 1500-1800cc petrol
// cars but have their own economy figures), and 2500 covers 2.5L+ diesel.
const CC_OPTIONS = [
  { value: 660,  label: '660cc (e.g., Alto, Mira, Dayz)' },
  { value: 800,  label: '800cc (e.g., Mehran, Old Alto)' },
  { value: 1000, label: '1000cc (e.g., Cultus, WagonR, Vitz)' },
  { value: 1200, label: '1200cc (e.g., City 1.2, Stonic, Swift)' },
  { value: 1300, label: '1300cc (e.g., Yaris 1.3, City 1.3)' },
  { value: 1500, label: '1500cc (e.g., Civic 1.5T, BR-V)' },
  { value: 1800, label: '1800cc (e.g., Corolla Grande, Civic 1.8)' },
  { value: 1801, label: '1.5L-1.8L Hybrids (e.g., Aqua, Vezel, HEV)' },
  { value: 2500, label: '2.5L+ Diesel (e.g., Fortuner, Revo)' },
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

  const fuelCostResult = useMemo(() => {
    return calculateFuelCost({ cc: fuelCc, dailyKm: fuelKm });
  }, [fuelCc, fuelKm]);

  // ── Section 2: Token Tax Calculator State ──
  const [tokenProvince, setTokenProvince] = useState('Islamabad');
  const [tokenFiler, setTokenFiler] = useState(true);
  const [tokenCc, setTokenCc] = useState(1300);
  const [tokenInvoiceValue, setTokenInvoiceValue] = useState(4000000);
  const [tokenAge, setTokenAge] = useState(0);

  const tokenTaxResult = useMemo(() => {
    return calculateTokenTax({
      province: tokenProvince,
      cc: tokenCc,
      isFiler: tokenFiler,
      invoiceValue: tokenInvoiceValue,
      vehicleAge: tokenAge,
      useEPay: true
    });
  }, [tokenProvince, tokenFiler, tokenCc, tokenInvoiceValue, tokenAge]);

  // ── Section 3: Transfer Fee Calculator State ──
  const [transferProvince, setTransferProvince] = useState('Punjab');
  const [transferCc, setTransferCc] = useState(1300);
  const [buyerFiler, setBuyerFiler] = useState(true);
  const [sellerFiler, setSellerFiler] = useState(true);
  const [transferAge, setTransferAge] = useState(0);

  const transferCostResult = useMemo(() => {
    return calculateTransferCost({
      province: transferProvince,
      cc: transferCc,
      isBuyerFiler: buyerFiler,
      vehicleAge: transferAge
    });
  }, [transferProvince, transferCc, buyerFiler, transferAge]);

  return (
    <>
      <SEO
        title="Car Tax, Transfer Fee & Fuel Cost Calculators Pakistan (FY 2026-27)"
        description="Calculate exact annual token tax (ICT, Punjab, Sindh, KPK), FBR 231B vehicle transfer fees, and monthly fuel costs with latest 2026-2027 statutory rates."
        path="/calculators"
        keywords={[
          'token tax calculator Pakistan 2026',
          'vehicle transfer fee calculator FBR 231B',
          'car fuel cost calculator Pakistan',
          'Section 234 withholding tax vehicle',
        ]}
        schema={calculatorsSchema}
      />

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
                  Rs. {fuelCostResult.monthlyCost.toLocaleString()}
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

                {(tokenProvince === 'Punjab' || tokenProvince === 'Islamabad') && tokenCc > 1000 && (
                  <div>
                    <label className="block font-mono text-[10px] md:text-xs font-bold uppercase tracking-[0.14em] text-df-black/50 dark:text-zinc-50/50 mb-2">
                      Vehicle Invoice Value (PKR)
                    </label>
                    <input
                      type="number"
                      value={tokenInvoiceValue}
                      onChange={(e) => setTokenInvoiceValue(Number(e.target.value))}
                      className="w-full p-3 md:p-4 bg-df-white dark:bg-black border-2 border-df-black dark:border-white rounded-none outline-none font-mono text-sm md:text-base font-medium focus:ring-2 focus:ring-df-red focus:border-df-red text-df-black dark:text-zinc-50"
                      min="0"
                      step="100000"
                    />
                  </div>
                )}

                {/* Drives the FBR Section 234 exemption: WHT stops at 10 years. */}
                <BrutalSlider
                  id="token-age"
                  label="Vehicle Age"
                  value={tokenAge}
                  onChange={(e) => setTokenAge(Number(e.target.value))}
                  min={0}
                  max={15}
                  unit="yrs"
                />
              </div>

              {/* Output Box — Monospace Receipt Layout */}
              <div className="bg-df-black px-6 md:px-8 py-5 md:py-6">
                <p className="font-mono text-[10px] md:text-xs font-bold tracking-[0.14em] text-white/40 uppercase mb-3">
                  Token Tax Breakdown
                </p>
                <div className="font-mono text-sm md:text-base text-white/80 space-y-1.5 leading-relaxed">
                  <p>&gt; PROVINCIAL TOKEN TAX: <span className="text-white font-bold">Rs. {tokenTaxResult.provincialTokenBase.toLocaleString()} {tokenTaxResult.isLifetimePaid ? '(LIFETIME)' : ''}</span></p>
                  {(tokenTaxResult.tokenRebate > 0 || tokenTaxResult.tokenSurcharge > 0) && (
                    <p>&gt; REBATE / SURCHARGE: <span className="text-white font-bold">Rs. {(tokenTaxResult.tokenSurcharge - tokenTaxResult.tokenRebate).toLocaleString()}</span></p>
                  )}
                  <p>&gt; FBR SEC 234 WHT: <span className="text-[#E5202E] font-bold">Rs. {tokenTaxResult.fbrSec234.toLocaleString()}</span></p>
                  <div className="border-t border-white/20 my-2 pt-2">
                    <p className="text-white font-bold text-lg md:text-xl">&gt; TOTAL ANNUAL TAX: Rs. {tokenTaxResult.totalAnnualTax.toLocaleString()}</p>
                  </div>
                </div>
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
                  id="transfer-province"
                  label="Region / Province"
                  value={transferProvince}
                  onChange={(e) => setTransferProvince(e.target.value)}
                  options={PROVINCE_OPTIONS}
                />

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

                {/* Drives the FBR Section 231B discount: the advance tax drops
                    10% per year of age and reaches zero at 10 years. */}
                <BrutalSlider
                  id="transfer-age"
                  label="Vehicle Age"
                  value={transferAge}
                  onChange={(e) => setTransferAge(Number(e.target.value))}
                  min={0}
                  max={10}
                  unit="yrs"
                />
              </div>

              {/* Output Box — Monospace Receipt Layout */}
              <div className="bg-df-black px-6 md:px-8 py-5 md:py-6">
                <p className="font-mono text-[10px] md:text-xs font-bold tracking-[0.14em] text-white/40 uppercase mb-3">
                  Transfer Fee Breakdown
                </p>
                <div className="font-mono text-sm md:text-base text-white/80 space-y-1.5 leading-relaxed">
                  <p>&gt; PROVINCIAL MRA FEE: <span className="text-white font-bold">Rs. {transferCostResult.mraFee.toLocaleString()}</span></p>
                  <p>&gt; FBR 231B ADVANCE TAX: <span className="text-[#E5202E] font-bold">Rs. {transferCostResult.advanceTax231b.toLocaleString()}</span></p>
                  <p>&gt; SMART CARD FEE: <span className="text-white font-bold">Rs. {transferCostResult.smartCardFee.toLocaleString()}</span></p>
                  <p>&gt; BIOMETRIC FEE: <span className="text-white font-bold">Rs. {transferCostResult.biometricFee.toLocaleString()}</span></p>
                  <div className="border-t border-white/20 my-2 pt-2">
                    <p className="text-white font-bold text-lg md:text-xl">&gt; TOTAL: Rs. {transferCostResult.totalTransferCost.toLocaleString()}</p>
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