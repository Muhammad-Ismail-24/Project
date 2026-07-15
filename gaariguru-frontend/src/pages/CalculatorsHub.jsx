import React, { useState, useEffect } from 'react';
import { Fuel, FileText, Landmark } from 'lucide-react';
import { calculateFuel, calculateTransfer, calculateToken } from '../utils/api';

const CC_OPTIONS = [
  { value: 800, label: "800cc (Alto, WagonR)" },
  { value: 1000, label: "1000cc (Cultus, Swift)" },
  { value: 1300, label: "1300cc (Yaris, City)" },
  { value: 1500, label: "1500cc (Civic, BR-V)" },
  { value: 1800, label: "1800cc (Grande, Sportage)" },
  { value: 2500, label: "2500cc+ (Fortuner, Prado)" },
];

export default function CalculatorsHub() {
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
    <div className="relative z-10 pt-24 md:pt-32 px-4 md:px-6 pb-16 md:pb-24 min-h-screen font-sans text-black">
      {/* ── Background ── */}
      <div className="fixed inset-0 z-[-1] pointer-events-none overflow-hidden flex items-center justify-center bg-[#a3a3a3]">
        <div className="absolute inset-0 opacity-[0.05]" style={{ backgroundImage: 'radial-gradient(#000000 1px, transparent 1px)', backgroundSize: '32px 32px' }} />
        <div className="absolute w-[80vw] h-[80vw] max-w-[1000px] max-h-[1000px] bg-white rounded-full blur-[140px] top-[0%] left-[-10%] opacity-40" />
      </div>

      <div className="max-w-7xl mx-auto">
        <div className="text-center mb-10 md:mb-16">
          <h1 className="text-4xl md:text-5xl font-black tracking-tighter mb-3 md:mb-4 text-black">
            Financial Tools
          </h1>
          <p className="text-lg md:text-xl text-black font-bold">
            Calculate exact running costs, taxes, and transfer fees before you buy.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 md:gap-8">
          
          {/* Card 1: Fuel Calculator */}
          <div className="bg-white/60 backdrop-blur-md border border-black/15 rounded-2xl md:rounded-3xl p-6 md:p-8 shadow-xl">
            <div className="flex items-center mb-5 md:mb-6">
              <div className="p-2.5 md:p-3 bg-black rounded-xl text-white mr-3 md:mr-4 shadow-md"><Fuel className="w-5 h-5 md:w-6 md:h-6" /></div>
              <h2 className="text-xl md:text-2xl font-black tracking-tight">Fuel Cost</h2>
            </div>
            <div className="space-y-5 md:space-y-6">
              <div>
                <label className="block text-xs md:text-sm font-black uppercase tracking-wider mb-2">Engine Capacity</label>
                <select 
                  value={fuelCc}
                  onChange={(e) => setFuelCc(Number(e.target.value))}
                  className="w-full p-3 md:p-4 bg-white/50 border border-black/15 rounded-xl outline-none focus:border-black font-bold transition-colors cursor-pointer shadow-sm text-sm md:text-base"
                >
                  {CC_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <div className="flex justify-between items-center mb-2">
                  <label className="text-xs md:text-sm font-black uppercase tracking-wider">Daily Commute</label>
                  <span className="text-sm font-bold text-black">{fuelKm} km</span>
                </div>
                <input 
                  type="range" 
                  min="5" 
                  max="150" 
                  value={fuelKm}
                  onChange={(e) => setFuelKm(Number(e.target.value))}
                  className="w-full accent-black cursor-pointer" 
                />
              </div>
              <div className="pt-4 mt-4 border-t border-black/15">
                <p className="text-[10px] md:text-xs text-black font-black uppercase tracking-widest mb-1">Est. Monthly Cost</p>
                <p className="text-3xl md:text-4xl font-black">
                  {fuelLoading ? "..." : formatPKR(fuelCost)}
                </p>
              </div>
            </div>
          </div>

          {/* Card 2: Transfer Fee */}
          <div className="bg-white/60 backdrop-blur-md border border-black/15 rounded-2xl md:rounded-3xl p-6 md:p-8 shadow-xl">
            <div className="flex items-center mb-5 md:mb-6">
              <div className="p-2.5 md:p-3 bg-black rounded-xl text-white mr-3 md:mr-4 shadow-md"><FileText className="w-5 h-5 md:w-6 md:h-6" /></div>
              <h2 className="text-xl md:text-2xl font-black tracking-tight">Transfer Fee</h2>
            </div>
            <div className="space-y-5 md:space-y-6">
              <div>
                <label className="block text-xs md:text-sm font-black uppercase tracking-wider mb-2">Filer Status</label>
                <div className="flex space-x-4 md:space-x-6">
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input 
                      type="radio" 
                      name="transferFiler" 
                      checked={transferFiler === true} 
                      onChange={() => setTransferFiler(true)}
                      className="accent-black w-4 h-4" 
                    />
                    <span className="font-bold text-sm">Active Filer</span>
                  </label>
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input 
                      type="radio" 
                      name="transferFiler" 
                      checked={transferFiler === false}
                      onChange={() => setTransferFiler(false)}
                      className="accent-black w-4 h-4" 
                    />
                    <span className="font-bold text-sm">Non-Filer</span>
                  </label>
                </div>
              </div>
              <div>
                <label className="block text-xs md:text-sm font-black uppercase tracking-wider mb-2">Engine Capacity</label>
                <select 
                  value={transferCc}
                  onChange={(e) => setTransferCc(Number(e.target.value))}
                  className="w-full p-3 md:p-4 bg-white/50 border border-black/15 rounded-xl outline-none focus:border-black font-bold transition-colors cursor-pointer shadow-sm text-sm md:text-base"
                >
                  {CC_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
              <div className="pt-4 mt-4 border-t border-black/15">
                <p className="text-[10px] md:text-xs text-black font-black uppercase tracking-widest mb-1">Total Fee</p>
                <p className="text-3xl md:text-4xl font-black">
                  {transferLoading ? "..." : formatPKR(transferCost)}
                </p>
              </div>
            </div>
          </div>

          {/* Card 3: Token Tax */}
          <div className="bg-white/60 backdrop-blur-md border border-black/15 rounded-2xl md:rounded-3xl p-6 md:p-8 shadow-xl">
            <div className="flex items-center mb-5 md:mb-6">
              <div className="p-2.5 md:p-3 bg-black rounded-xl text-white mr-3 md:mr-4 shadow-md"><Landmark className="w-5 h-5 md:w-6 md:h-6" /></div>
              <h2 className="text-xl md:text-2xl font-black tracking-tight">Token Tax</h2>
            </div>
            <div className="space-y-5 md:space-y-6">
              <div>
                <label className="block text-xs md:text-sm font-black uppercase tracking-wider mb-2">Province</label>
                <select 
                  value={tokenProvince}
                  onChange={(e) => setTokenProvince(e.target.value)}
                  className="w-full p-3 md:p-4 bg-white/50 border border-black/15 rounded-xl outline-none focus:border-black font-bold transition-colors cursor-pointer shadow-sm text-sm md:text-base"
                >
                  <option value="Punjab">Punjab</option>
                  <option value="Sindh">Sindh</option>
                  <option value="KPK">KPK</option>
                  <option value="Islamabad">Islamabad</option>
                </select>
              </div>
              <div>
                <label className="block text-xs md:text-sm font-black uppercase tracking-wider mb-2">Engine Capacity</label>
                <select 
                  value={tokenCc}
                  onChange={(e) => setTokenCc(Number(e.target.value))}
                  className="w-full p-3 md:p-4 bg-white/50 border border-black/15 rounded-xl outline-none focus:border-black font-bold transition-colors cursor-pointer shadow-sm text-sm md:text-base"
                >
                  {CC_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs md:text-sm font-black uppercase tracking-wider mb-2">Filer Status</label>
                <div className="flex space-x-4 md:space-x-6">
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input 
                      type="radio" 
                      name="tokenFiler" 
                      checked={tokenFiler === true} 
                      onChange={() => setTokenFiler(true)}
                      className="accent-black w-4 h-4" 
                    />
                    <span className="font-bold text-sm">Active Filer</span>
                  </label>
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input 
                      type="radio" 
                      name="tokenFiler" 
                      checked={tokenFiler === false}
                      onChange={() => setTokenFiler(false)}
                      className="accent-black w-4 h-4" 
                    />
                    <span className="font-bold text-sm">Non-Filer</span>
                  </label>
                </div>
              </div>
              <div className="pt-4 mt-4 border-t border-black/15">
                <p className="text-[10px] md:text-xs text-black font-black uppercase tracking-widest mb-1">Annual Tax</p>
                <p className="text-3xl md:text-4xl font-black">
                  {tokenLoading ? "..." : formatPKR(tokenCost)}
                </p>
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}