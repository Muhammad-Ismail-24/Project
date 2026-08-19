import { FuelCostAgent } from '../agents/calculators/FuelCostAgent';
import { VehicleTaxAgent } from '../agents/calculators/VehicleTaxAgent';

export const calculateFuelCost = (params) => FuelCostAgent.calculate(params);
export const calculateVehicleCharges = (params) => VehicleTaxAgent.calculate(params);

export const formatPKR = (amount) => {
  return new Intl.NumberFormat('en-PK', {
    style: 'currency',
    currency: 'PKR',
    maximumFractionDigits: 0
  }).format(amount);
};
