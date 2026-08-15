import config from '../../data/calculatorsConfig.json';

export class FuelCostAgent {
  static calculate({ cc, dailyKm, cityRatio = 0.8 }) {
    const key = String(cc);
    const engineData = config.fuel_calculator.engine_averages_kml[key] || config.fuel_calculator.engine_averages_kml['1000'];
    const fuelPrice = config.fuel_calculator.fuel_prices_pkr[engineData.fuel_type];
    const monthlyKm = dailyKm * 30;

    const litersCity = (monthlyKm * cityRatio) / engineData.city;
    const litersHwy = (monthlyKm * (1 - cityRatio)) / engineData.highway;
    const totalLiters = litersCity + litersHwy;

    return {
      monthlyCost: Math.round(totalLiters * fuelPrice),
      totalLiters: totalLiters.toFixed(1),
      fuelPrice,
      label: engineData.label
    };
  }
}
