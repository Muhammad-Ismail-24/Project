import React, { useState, useEffect } from 'react';
import { Helmet } from 'react-helmet-async';
import { Fuel, FileText, Landmark } from 'lucide-react';
import { calculateFuel, calculateTransfer, calculateToken } from '../utils/api';
import useReveal from '../hooks/useReveal';

const CC_OPTIONS = [
  { value: 800, label: "800cc (Alto, WagonR)" },
  { value: 1000, label: "1000cc (Cultus, Swift)" },
  { value: 1300, label: "1300cc (Yaris, City)" },
  { value: 1500, label: "1500cc (Civic, BR-V)" },
  { value: 1800, label: "1800cc (Grande, Sportage)" },
  { value: 2500, label: "2500cc+ (Fortuner, Prado)" },
];

export default function CalculatorsHub() {
  const headingRef = useReveal();
  const [fuelCc, setFuelCc] = useState(1300);
  const [fuelKm, setFuelKm] = useState(40);
  const [fuelCost, setFuelCost] = useState(null);
  const [fuelLoading, setFuelLoading] = useState(false);

  const [transferCc, setTransferCc] = useState(1300);
  const [transferFiler, setTransferFiler] = useState(true);
  const [transferCost, setTransferCost] = useState(null);
  const [transferLoading, setTransferLoading] = useState(false);

  const [tokenCc, setTokenCc] = useState(1300);
  const [tokenProvince, setTokenProvince] = useState("Punjab");
  const [tokenFiler, setTokenFiler] = useState(true);
  const [tokenCost, setTokenCost] = useState(null);
  const [tokenLoading, setTokenLoading] = useState(false);

  useEffect(() => {
    let active = true;
    const fetchFuel = async () => {
      setFuelLoading(true);
      try {
        const res = await calculateFuel({ car_segment_cc: fuelCc, daily_commute_km: fuelKm });
        if (active) setFuelCost(res.monthly_fuel_cost_pkr);
      } catch (err) { console.error(err); } finally { if (active) setFuelLoading(false); }
    };
    fetchFuel();
    return () => { active = false; };
  }, [fuelCc, fuelKm]);

  useEffect(() => {
    let active = true;
    const fetchTransfer = async () => {
      setTransferLoading(true);
      try {
        const res = await calculateTransfer({ engine_cc: transferCc, is_filer: transferFiler });
        if (active) setTransferCost(res.total_transfer_cost_pkr);
      } catch (err) { console.error(err); } finally { if (active) setTransferLoading(false); }
    };
    fetchTransfer();
    return () => { active = false; };
  }, [transferCc, transferFiler]);

  useEffect(() => {
    let active = true;
    const fetchToken = async () => {
      setTokenLoading(true);
      try {
        const res = await calculateToken({ engine_cc: tokenCc, is_filer: tokenFiler, province: tokenProvince });
        if (active) setTokenCost(res.total_annual_token_tax_pkr);
      } catch (err) { console.error(err); } finally { if (active) setTokenLoading(false); }
    };
    fetchToken();
    return () => { active = false; };
  }, [tokenCc, tokenProvince, tokenFiler]);

  const formatPKR = (amount) => {
    if (amount === null) return "—";
    return `PKR ${amount.toLocaleString()}`;
  };

  return (
    <main className="relative z-10 pt-32 md:pt-40 px-4 md:px-6 pb-16 md:pb-24 min-h-screen font-sans">
      <Helmet>
        <title>Car Tax & Fuel Cost Calculators Pakistan | DriveFetch</title>
        <meta name="description" content="Calculate your vehicle's fuel cost, transfer fees, and token taxes accurately in Pakistan using our latest financial tools." />
        <link rel="canonical" href="https://carfinderproject.vercel.app/calculators" />
      </Helmet>

      <div className="max-w-7xl mx-auto">
        <div ref={headingRef} className="reveal text-center mb-10 md:mb-16">
          <h1 className="font-display text-4xl md:text-5xl font-black tracking-tighter mb-3 md:mb-4 text-text">
            Financial Tools
          </h1>
          <p className="text-base md:text-lg text-text-dim font-medium">
            Calculate exact running costs, taxes, and transfer fees before you buy.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 md:gap-8">

          {/* Card 1: Fuel Calculator */}
          <div className="glass glass-hover p-6 md:p-8">
            <div className="flex items-center mb-5 md:mb-6">
              <div className="p-2 md:p-2.5 bg-surface-2 rounded-xl text-text mr-3 md:mr-4"><Fuel className="w-5 h-5 md:w-6 md:h-6" /></div>
              <h2 className="font-display text-xl md:text-2xl font-black tracking-tight text-text">Fuel Cost</h2>
            </div>
            <div className="space-y-5 md:space-y-6">
              <div>
                <label className="block text-[10px] md:text-xs font-semibold uppercase tracking-[0.14em] text-text-faint mb-2">Engine Capacity</label>
                <select
                  value={fuelCc}
                  onChange={(e) => setFuelCc(Number(e.target.value))}
                  className="field text-sm md:text-base cursor-pointer"
                >
                  {CC_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <div className="flex justify-between items-center mb-2">
                  <label className="text-xs md:text-sm font-black uppercase tracking-wider text-text">Daily Commute</label>
                  <span className="text-sm font-bold text-text">{fuelKm} km</span>
                </div>
                <input
                  type="range"
                  min="5"
                  max="150"
                  value={fuelKm}
                  onChange={(e) => setFuelKm(Number(e.target.value))}
                  className="slider w-full cursor-pointer"
                />
              </div>
              <div className="pt-4 mt-4" style={{ borderTop: '1px solid var(--df-glass-border)' }}>
                <p className="text-[10px] md:text-xs font-semibold uppercase tracking-widest mb-1 text-text-faint">Est. Monthly Cost</p>
                <p className="font-display text-3xl md:text-4xl font-black text-text">
                  {fuelLoading ? "..." : formatPKR(fuelCost)}
                </p>
              </div>
            </div>
          </div>

          {/* Card 2: Transfer Fee */}
          <div className="glass glass-hover p-6 md:p-8">
            <div className="flex items-center mb-5 md:mb-6">
              <div className="p-2 md:p-2.5 bg-surface-2 rounded-xl text-text mr-3 md:mr-4"><FileText className="w-5 h-5 md:w-6 md:h-6" /></div>
              <h2 className="font-display text-xl md:text-2xl font-black tracking-tight text-text">Transfer Fee</h2>
            </div>
            <div className="space-y-5 md:space-y-6">
              <div>
                <label className="block text-[10px] md:text-xs font-semibold uppercase tracking-[0.14em] text-text-faint mb-2">Filer Status</label>
                <div className="flex space-x-4 md:space-x-6">
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="radio"
                      name="transferFiler"
                      checked={transferFiler === true}
                      onChange={() => setTransferFiler(true)}
                      className="accent-accent w-4 h-4"
                    />
                    <span className="font-medium text-sm text-text-dim">Active Filer</span>
                  </label>
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="radio"
                      name="transferFiler"
                      checked={transferFiler === false}
                      onChange={() => setTransferFiler(false)}
                      className="accent-accent w-4 h-4"
                    />
                    <span className="font-medium text-sm text-text-dim">Non-Filer</span>
                  </label>
                </div>
              </div>
              <div>
                <label className="block text-[10px] md:text-xs font-semibold uppercase tracking-[0.14em] text-text-faint mb-2">Engine Capacity</label>
                <select
                  value={transferCc}
                  onChange={(e) => setTransferCc(Number(e.target.value))}
                  className="field text-sm md:text-base cursor-pointer"
                >
                  {CC_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
              <div className="pt-4 mt-4" style={{ borderTop: '1px solid var(--df-glass-border)' }}>
                <p className="text-[10px] md:text-xs font-semibold uppercase tracking-widest mb-1 text-text-faint">Total Fee</p>
                <p className="font-display text-3xl md:text-4xl font-black text-text">
                  {transferLoading ? "..." : formatPKR(transferCost)}
                </p>
              </div>
            </div>
          </div>

          {/* Card 3: Token Tax */}
          <div className="glass glass-hover p-6 md:p-8">
            <div className="flex items-center mb-5 md:mb-6">
              <div className="p-2 md:p-2.5 bg-surface-2 rounded-xl text-text mr-3 md:mr-4"><Landmark className="w-5 h-5 md:w-6 md:h-6" /></div>
              <h2 className="font-display text-xl md:text-2xl font-black tracking-tight text-text">Token Tax</h2>
            </div>
            <div className="space-y-5 md:space-y-6">
              <div>
                <label className="block text-[10px] md:text-xs font-semibold uppercase tracking-[0.14em] text-text-faint mb-2">Province</label>
                <select
                  value={tokenProvince}
                  onChange={(e) => setTokenProvince(e.target.value)}
                  className="field text-sm md:text-base cursor-pointer"
                >
                  <option value="Punjab">Punjab</option>
                  <option value="Sindh">Sindh</option>
                  <option value="KPK">KPK</option>
                  <option value="Islamabad">Islamabad</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] md:text-xs font-semibold uppercase tracking-[0.14em] text-text-faint mb-2">Engine Capacity</label>
                <select
                  value={tokenCc}
                  onChange={(e) => setTokenCc(Number(e.target.value))}
                  className="field text-sm md:text-base cursor-pointer"
                >
                  {CC_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-[10px] md:text-xs font-semibold uppercase tracking-[0.14em] text-text-faint mb-2">Filer Status</label>
                <div className="flex space-x-4 md:space-x-6">
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="radio"
                      name="tokenFiler"
                      checked={tokenFiler === true}
                      onChange={() => setTokenFiler(true)}
                      className="accent-accent w-4 h-4"
                    />
                    <span className="font-medium text-sm text-text-dim">Active Filer</span>
                  </label>
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="radio"
                      name="tokenFiler"
                      checked={tokenFiler === false}
                      onChange={() => setTokenFiler(false)}
                      className="accent-accent w-4 h-4"
                    />
                    <span className="font-medium text-sm text-text-dim">Non-Filer</span>
                  </label>
                </div>
              </div>
              <div className="pt-4 mt-4" style={{ borderTop: '1px solid var(--df-glass-border)' }}>
                <p className="text-[10px] md:text-xs font-semibold uppercase tracking-widest mb-1 text-text-faint">Annual Tax</p>
                <p className="font-display text-3xl md:text-4xl font-black text-text">
                  {tokenLoading ? "..." : formatPKR(tokenCost)}
                </p>
              </div>
            </div>
          </div>

        </div>
      </div>
    </main>
  );
}