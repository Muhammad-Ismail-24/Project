import React from 'react';
import FuelCostCalculator from '../components/calculators/FuelCostCalculator';
import TokenTaxCalculator from '../components/calculators/TokenTaxCalculator';
import TransferFeeCalculator from '../components/calculators/TransferFeeCalculator';

const Calculators = () => {
  return (
    <div className="max-w-7xl mx-auto p-4 sm:p-6 lg:p-8">
      <div className="mb-12 border-b-4 border-black dark:border-white pb-6">
        <h1 className="text-4xl sm:text-5xl font-black uppercase tracking-tighter text-black dark:text-white">
          Automotive <span className="text-red-600">Calculators</span>
        </h1>
        <p className="text-lg font-bold text-zinc-500 mt-2 uppercase tracking-wide">
          FY 2026-2027 Statutory Rates & Analysis
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <FuelCostCalculator />
        <TokenTaxCalculator />
        <TransferFeeCalculator />
      </div>
    </div>
  );
};

export default Calculators;
