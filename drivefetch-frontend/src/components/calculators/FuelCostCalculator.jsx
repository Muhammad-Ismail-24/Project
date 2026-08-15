import React, { useState } from 'react';
import { calculateFuelCost, formatPKR } from '../../utils/calculatorEngine';
import configData from '../../data/calculatorsConfig.json';

const FuelCostCalculator = () => {
  const [engineType, setEngineType] = useState('1000cc');
  const [totalKm, setTotalKm] = useState(1000);
  const [cityPercentage, setCityPercentage] = useState(70);

  const results = calculateFuelCost(engineType, totalKm, cityPercentage);
  const engineList = configData.fuel_calculator.engine_averages_kml;

  return (
    <div className="border-2 border-black dark:border-white bg-white dark:bg-zinc-950 p-6 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_0px_rgba(255,255,255,1)]">
      <div className="mb-6 border-b-2 border-black dark:border-white pb-4">
        <span className="text-xs font-mono text-zinc-500">[ TOOL // 01 ]</span>
        <h2 className="text-2xl font-black tracking-tight uppercase mt-1">Monthly Fuel Cost</h2>
      </div>
      
      <div className="flex flex-col gap-5 mb-8">
        <div className="flex flex-col gap-2">
          <label className="text-sm font-bold uppercase tracking-tight">Engine & Vehicle Type</label>
          <select 
            value={engineType} 
            onChange={(e) => setEngineType(e.target.value)}
            className="border-2 border-black dark:border-white bg-white dark:bg-black p-3 font-bold text-black dark:text-white focus:outline-none focus:ring-2 focus:ring-red-600 appearance-none"
          >
            {Object.entries(engineList).map(([key, data]) => (
              <option key={key} value={key}>{data.label}</option>
            ))}
          </select>
        </div>
        
        <div className="flex flex-col gap-2">
          <label className="text-sm font-bold uppercase tracking-tight">Monthly Distance (km)</label>
          <input 
            type="number" 
            value={totalKm} 
            onChange={(e) => setTotalKm(Number(e.target.value))}
            min="0"
            className="border-2 border-black dark:border-white bg-white dark:bg-black p-3 font-bold text-black dark:text-white focus:outline-none focus:ring-2 focus:ring-red-600"
          />
        </div>
        
        <div className="flex flex-col gap-2">
          <label className="text-sm font-bold uppercase tracking-tight flex justify-between">
            <span>City Driving ({cityPercentage}%)</span>
            <span className="text-zinc-500">Hwy ({100 - cityPercentage}%)</span>
          </label>
          <input 
            type="range" 
            min="0" 
            max="100" 
            value={cityPercentage} 
            onChange={(e) => setCityPercentage(Number(e.target.value))}
            className="w-full accent-red-600 h-2 bg-zinc-200 rounded-none appearance-none"
          />
        </div>
      </div>
      
      <div className="bg-zinc-100 dark:bg-zinc-900 border-2 border-black dark:border-white p-5">
        <h3 className="text-xs font-bold text-red-600 uppercase tracking-widest mb-1">Estimated Cost</h3>
        <div className="text-4xl font-black tracking-tighter mb-4">{formatPKR(results.totalCost)}</div>
        
        <div className="space-y-2 border-t-2 border-black dark:border-white pt-4 mt-2">
          <div className="flex justify-between items-center text-sm font-bold">
            <span className="text-zinc-500 uppercase">Fuel Type</span>
            <span>{results.fuelType} (Rs. {results.fuelPrice}/L)</span>
          </div>
          <div className="flex justify-between items-center text-sm font-bold">
            <span className="text-zinc-500 uppercase">Consumption</span>
            <span>{results.litersUsed.toFixed(1)} Liters</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default FuelCostCalculator;
