import React, { useState } from 'react';
import { calculateTransferCost, formatPKR } from '../../utils/calculatorEngine';

const TransferFeeCalculator = () => {
  const [province, setProvince] = useState('punjab');
  const [cc, setCc] = useState(1300);
  const [regYear, setRegYear] = useState(new Date().getFullYear());
  const [filerStatus, setFilerStatus] = useState('filer');
  const [isSpeculative, setIsSpeculative] = useState(false);
  const [includePlates, setIncludePlates] = useState(false);

  const res = calculateTransferCost({ province, cc, regYear, filerStatus, isSpeculative, includePlates });

  return (
    <div className="border-2 border-black dark:border-white bg-white dark:bg-zinc-950 p-6 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_0px_rgba(255,255,255,1)]">
      <div className="mb-6 border-b-2 border-black dark:border-white pb-4">
        <span className="text-xs font-mono text-zinc-500">[ TOOL // 03 ]</span>
        <h2 className="text-2xl font-black tracking-tight uppercase mt-1">Transfer Fee</h2>
      </div>
      
      <div className="flex flex-col gap-5 mb-8">
        <div className="flex flex-col gap-2">
          <label className="text-sm font-bold uppercase tracking-tight">Province</label>
          <select 
            value={province} 
            onChange={(e) => setProvince(e.target.value)}
            className="border-2 border-black dark:border-white bg-white dark:bg-black p-3 font-bold text-black dark:text-white focus:outline-none focus:ring-2 focus:ring-red-600 appearance-none"
          >
            <option value="punjab">Punjab</option>
            <option value="islamabad">Islamabad (ICT)</option>
            <option value="sindh">Sindh</option>
            <option value="kpk">Khyber Pakhtunkhwa</option>
          </select>
        </div>
        
        <div className="flex flex-col gap-2">
          <label className="text-sm font-bold uppercase tracking-tight">Engine Capacity (CC)</label>
          <input 
            type="number" 
            value={cc} 
            onChange={(e) => setCc(Number(e.target.value))} 
            min="1"
            className="border-2 border-black dark:border-white bg-white dark:bg-black p-3 font-bold text-black dark:text-white focus:outline-none focus:ring-2 focus:ring-red-600"
          />
        </div>
        
        <div className="flex flex-col gap-2">
          <label className="text-sm font-bold uppercase tracking-tight">Reg. Year</label>
          <select 
            value={regYear} 
            onChange={(e) => setRegYear(Number(e.target.value))}
            className="border-2 border-black dark:border-white bg-white dark:bg-black p-3 font-bold text-black dark:text-white focus:outline-none focus:ring-2 focus:ring-red-600 appearance-none"
          >
            {Array.from({length: 30}, (_, i) => new Date().getFullYear() - i).map(year => (
              <option key={year} value={year}>{year}</option>
            ))}
          </select>
        </div>
        
        <div className="flex flex-col gap-2">
          <label className="text-sm font-bold uppercase tracking-tight">Buyer Filer Status</label>
          <div className="flex gap-2">
            <button 
              onClick={() => setFilerStatus('filer')}
              className={`flex-1 p-2 text-sm uppercase ${filerStatus === 'filer' ? 'bg-black text-white dark:bg-white dark:text-black border-2 border-black dark:border-white font-black' : 'bg-transparent text-zinc-600 dark:text-zinc-400 border-2 border-zinc-300 dark:border-zinc-700 hover:border-black dark:hover:border-white font-bold'}`}
            >
              Filer
            </button>
            <button 
              onClick={() => setFilerStatus('non-filer')}
              className={`flex-1 p-2 text-sm uppercase ${filerStatus === 'non-filer' ? 'bg-black text-white dark:bg-white dark:text-black border-2 border-black dark:border-white font-black' : 'bg-transparent text-zinc-600 dark:text-zinc-400 border-2 border-zinc-300 dark:border-zinc-700 hover:border-black dark:hover:border-white font-bold'}`}
            >
              Non-Filer
            </button>
          </div>
        </div>

        <div className="flex flex-col gap-3 mt-2">
           <label className="flex items-center gap-3 cursor-pointer">
              <input 
                type="checkbox" 
                checked={isSpeculative} 
                onChange={(e) => setIsSpeculative(e.target.checked)} 
                className="w-5 h-5 accent-red-600 border-2 border-black cursor-pointer"
              />
              <span className="text-sm font-bold uppercase tracking-tight">Transfer &lt; 90 Days (Speculative)</span>
           </label>
           <label className="flex items-center gap-3 cursor-pointer">
              <input 
                type="checkbox" 
                checked={includePlates} 
                onChange={(e) => setIncludePlates(e.target.checked)} 
                className="w-5 h-5 accent-red-600 border-2 border-black cursor-pointer"
              />
              <span className="text-sm font-bold uppercase tracking-tight">Include Number Plates</span>
           </label>
        </div>
      </div>
      
      <div className="bg-zinc-100 dark:bg-zinc-900 border-2 border-black dark:border-white p-5">
        <h3 className="text-xs font-bold text-red-600 uppercase tracking-widest mb-1">Total Transfer Cost</h3>
        <div className="text-4xl font-black tracking-tighter mb-4">{formatPKR(res.total)}</div>
        
        <div className="space-y-2 border-t-2 border-black dark:border-white pt-4 mt-2">
          <div className="flex justify-between items-center text-sm font-bold">
            <span className="text-zinc-500 uppercase">MRA Fee</span>
            <span>{formatPKR(res.mraFee)}</span>
          </div>
          <div className="flex justify-between items-center text-sm font-bold">
            <span className="text-zinc-500 uppercase">Sec 231B (-{Math.min(50, 10 * res.age)}%)</span>
            <span>{formatPKR(res.advanceTax)}</span>
          </div>
          <div className="flex justify-between items-center text-sm font-bold">
            <span className="text-zinc-500 uppercase">Admin (Card+Bio)</span>
            <span>{formatPKR(res.smartCardFee + res.bioFee)}</span>
          </div>
          {includePlates && (
             <div className="flex justify-between items-center text-sm font-bold">
              <span className="text-zinc-500 uppercase">Plates</span>
              <span>{formatPKR(res.platesFee)}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default TransferFeeCalculator;
