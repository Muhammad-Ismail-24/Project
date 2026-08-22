import config from '../../data/calculatorsConfig.json';

export class FuelCostAgent {
  static calculate({ cc, dailyKm, cityRatio = 0.8 }) {
    const safeDailyKm = Math.max(0, parseFloat(dailyKm) || 0);
    const key = String(cc);
    const engineData = config.fuel_calculator.engine_averages_kml[key] || config.fuel_calculator.engine_averages_kml['1000'];
    const fuelPrice = config.fuel_calculator.fuel_prices_pkr[engineData.fuel_type] || 0;
    const monthlyKm = safeDailyKm * 30;

    const cityAvg = Math.max(0.1, parseFloat(engineData.city) || 12);
    const hwyAvg = Math.max(0.1, parseFloat(engineData.highway) || 14);

    const litersCity = (monthlyKm * cityRatio) / cityAvg;
    const litersHwy = (monthlyKm * (1 - cityRatio)) / hwyAvg;
    const totalLiters = litersCity + litersHwy;

    if (!isFinite(totalLiters) || isNaN(totalLiters)) {
        return { monthlyCost: 0, totalLiters: "0.0", fuelPrice: 0, label: engineData.label || "Unknown" };
    }

    return {
      monthlyCost: Math.round(totalLiters * fuelPrice),
      totalLiters: totalLiters.toFixed(1),
      fuelPrice,
      label: engineData.label || "Unknown"
    };
  }
}
