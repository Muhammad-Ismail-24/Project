import { FuelCostAgent } from '../agents/calculators/FuelCostAgent';
import { TokenTaxAgent } from '../agents/calculators/TokenTaxAgent';
import { TransferFeeAgent } from '../agents/calculators/TransferFeeAgent';

export const calculateFuelCost = (params) => FuelCostAgent.calculate(params);
export const calculateTokenTax = (params) => TokenTaxAgent.calculate(params);
export const calculateTransferCost = (params) => TransferFeeAgent.calculate(params);

export const formatPKR = (amount) => {
  return new Intl.NumberFormat('en-PK', {
    style: 'currency',
    currency: 'PKR',
    maximumFractionDigits: 0
  }).format(amount);
};
