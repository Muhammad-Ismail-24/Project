var calculatorsConfig_default = {
	metadata: {
		"version": "2.0.0",
		"fiscal_year": "2026-2027",
		"currency": "PKR"
	},
	fuel_calculator: {
		"fuel_prices_pkr": {
			"petrol_ron92": 325.43,
			"high_speed_diesel": 383.95
		},
		"engine_averages_kml": {
			"660": {
				"label": "660cc (Kei / Hatchbacks: Alto, Mira, Dayz)",
				"city": 17.5,
				"highway": 21.5,
				"fuel_type": "petrol_ron92"
			},
			"800": {
				"label": "800cc (Legacy Budget: Mehran, Old Alto)",
				"city": 12,
				"highway": 16,
				"fuel_type": "petrol_ron92"
			},
			"1000": {
				"label": "1000cc (Compact Hatchbacks: Cultus, WagonR, Vitz 1.0)",
				"city": 14.2,
				"highway": 17.8,
				"fuel_type": "petrol_ron92"
			},
			"1200": {
				"label": "1200cc (Compact: City 1.2, Stonic, Swift 1.2)",
				"city": 13,
				"highway": 17.2,
				"fuel_type": "petrol_ron92"
			},
			"1300": {
				"label": "1300cc (Mid-Size Sedans: Yaris 1.3, City 1.3, Corolla 1.3)",
				"city": 12.2,
				"highway": 16.2,
				"fuel_type": "petrol_ron92"
			},
			"1500": {
				"label": "1500cc (Sedans / CUVs: Civic 1.5T, BR-V, Yaris 1.5)",
				"city": 11.2,
				"highway": 15.2,
				"fuel_type": "petrol_ron92"
			},
			"1800": {
				"label": "1800cc (Executive Sedans: Corolla Grande, Civic 1.8)",
				"city": 10.5,
				"highway": 15.2,
				"fuel_type": "petrol_ron92"
			},
			"1801": {
				"label": "1.5L - 1.8L Strong Hybrids (Aqua, Prius, Vezel, Haval HEV)",
				"city": 21,
				"highway": 18.8,
				"fuel_type": "petrol_ron92"
			},
			"2500": {
				"label": "2.5L+ Diesel (SUVs / Pickups: Fortuner, Revo)",
				"city": 9,
				"highway": 12,
				"fuel_type": "high_speed_diesel"
			}
		}
	},
	token_tax_calculator: {
		"provincial_token_tax": {
			"islamabad": { "slabs": [
				{
					"min_cc": 0,
					"max_cc": 1e3,
					"tax_type": "fixed",
					"amount_pkr": 2e4
				},
				{
					"min_cc": 1001,
					"max_cc": 2e3,
					"tax_type": "invoice_pct",
					"rate": .0025
				},
				{
					"min_cc": 2001,
					"max_cc": 99999,
					"tax_type": "invoice_pct",
					"rate": .0035
				}
			] },
			"punjab": {
				"epay_discount_pct": 5,
				"slabs": [
					{
						"min_cc": 0,
						"max_cc": 1e3,
						"tax_type": "fixed",
						"amount_pkr": 2e4
					},
					{
						"min_cc": 1001,
						"max_cc": 2e3,
						"tax_type": "invoice_pct",
						"rate": .002
					},
					{
						"min_cc": 2001,
						"max_cc": 99999,
						"tax_type": "invoice_pct",
						"rate": .003
					}
				]
			},
			"sindh": { "slabs": [
				{
					"min_cc": 0,
					"max_cc": 1e3,
					"amount_pkr": 1e3
				},
				{
					"min_cc": 1001,
					"max_cc": 1300,
					"amount_pkr": 2e3
				},
				{
					"min_cc": 1301,
					"max_cc": 1500,
					"amount_pkr": 3e3
				},
				{
					"min_cc": 1501,
					"max_cc": 1600,
					"amount_pkr": 4e3
				},
				{
					"min_cc": 1601,
					"max_cc": 2e3,
					"amount_pkr": 4500
				},
				{
					"min_cc": 2001,
					"max_cc": 2500,
					"amount_pkr": 5e3
				},
				{
					"min_cc": 2501,
					"max_cc": 99999,
					"amount_pkr": 7e3
				}
			] },
			"kpk": { "slabs": [
				{
					"min_cc": 0,
					"max_cc": 1e3,
					"amount_pkr": 1e3
				},
				{
					"min_cc": 1001,
					"max_cc": 1300,
					"amount_pkr": 1500
				},
				{
					"min_cc": 1301,
					"max_cc": 1500,
					"amount_pkr": 2500
				},
				{
					"min_cc": 1501,
					"max_cc": 1600,
					"amount_pkr": 3500
				},
				{
					"min_cc": 1601,
					"max_cc": 2e3,
					"amount_pkr": 5e3
				},
				{
					"min_cc": 2001,
					"max_cc": 2500,
					"amount_pkr": 8e3
				},
				{
					"min_cc": 2501,
					"max_cc": 99999,
					"amount_pkr": 1e4
				}
			] }
		},
		"fbr_section_234_wht": {
			"exemption_age_years": 10,
			"slabs": [
				{
					"min_cc": 0,
					"max_cc": 1e3,
					"filer_pkr": 800,
					"non_filer_pkr": 1600
				},
				{
					"min_cc": 1001,
					"max_cc": 1199,
					"filer_pkr": 1500,
					"non_filer_pkr": 3e3
				},
				{
					"min_cc": 1200,
					"max_cc": 1299,
					"filer_pkr": 1750,
					"non_filer_pkr": 3500
				},
				{
					"min_cc": 1300,
					"max_cc": 1499,
					"filer_pkr": 2500,
					"non_filer_pkr": 5e3
				},
				{
					"min_cc": 1500,
					"max_cc": 1599,
					"filer_pkr": 3750,
					"non_filer_pkr": 7500
				},
				{
					"min_cc": 1600,
					"max_cc": 1999,
					"filer_pkr": 4500,
					"non_filer_pkr": 9e3
				},
				{
					"min_cc": 2e3,
					"max_cc": 99999,
					"filer_pkr": 1e4,
					"non_filer_pkr": 2e4
				}
			]
		}
	},
	transfer_calculator: {
		"fbr_section_231b_advance_tax": {
			"annual_depreciation_pct": .1,
			"max_depreciation_years": 10,
			"slabs": [
				{
					"min_cc": 0,
					"max_cc": 850,
					"filer_pkr": 0,
					"non_filer_pkr": 1e4
				},
				{
					"min_cc": 851,
					"max_cc": 1e3,
					"filer_pkr": 5e3,
					"non_filer_pkr": 1e4
				},
				{
					"min_cc": 1001,
					"max_cc": 1300,
					"filer_pkr": 7500,
					"non_filer_pkr": 15e3
				},
				{
					"min_cc": 1301,
					"max_cc": 1600,
					"filer_pkr": 12500,
					"non_filer_pkr": 25e3
				},
				{
					"min_cc": 1601,
					"max_cc": 1800,
					"filer_pkr": 18750,
					"non_filer_pkr": 37500
				},
				{
					"min_cc": 1801,
					"max_cc": 2e3,
					"filer_pkr": 25e3,
					"non_filer_pkr": 5e4
				},
				{
					"min_cc": 2001,
					"max_cc": 2500,
					"filer_pkr": 37500,
					"non_filer_pkr": 75e3
				},
				{
					"min_cc": 2501,
					"max_cc": 3e3,
					"filer_pkr": 5e4,
					"non_filer_pkr": 1e5
				},
				{
					"min_cc": 3001,
					"max_cc": 99999,
					"filer_pkr": 62500,
					"non_filer_pkr": 125e3
				}
			]
		},
		"provincial_mra_transfer_fees": {
			"punjab": [
				{
					"min_cc": 0,
					"max_cc": 1e3,
					"fee_pkr": 1200
				},
				{
					"min_cc": 1001,
					"max_cc": 1300,
					"fee_pkr": 1800
				},
				{
					"min_cc": 1301,
					"max_cc": 1600,
					"fee_pkr": 2500
				},
				{
					"min_cc": 1601,
					"max_cc": 2e3,
					"fee_pkr": 4e3
				},
				{
					"min_cc": 2001,
					"max_cc": 2500,
					"fee_pkr": 5500
				},
				{
					"min_cc": 2501,
					"max_cc": 99999,
					"fee_pkr": 8e3
				}
			],
			"islamabad": [
				{
					"min_cc": 0,
					"max_cc": 1e3,
					"fee_pkr": 1200
				},
				{
					"min_cc": 1001,
					"max_cc": 1300,
					"fee_pkr": 1800
				},
				{
					"min_cc": 1301,
					"max_cc": 1800,
					"fee_pkr": 3e3
				},
				{
					"min_cc": 1801,
					"max_cc": 2500,
					"fee_pkr": 5e3
				},
				{
					"min_cc": 2501,
					"max_cc": 99999,
					"fee_pkr": 7500
				}
			],
			"sindh": [
				{
					"min_cc": 0,
					"max_cc": 1e3,
					"fee_pkr": 1500
				},
				{
					"min_cc": 1001,
					"max_cc": 1300,
					"fee_pkr": 2200
				},
				{
					"min_cc": 1301,
					"max_cc": 1600,
					"fee_pkr": 3500
				},
				{
					"min_cc": 1601,
					"max_cc": 2e3,
					"fee_pkr": 5e3
				},
				{
					"min_cc": 2001,
					"max_cc": 2500,
					"fee_pkr": 6500
				},
				{
					"min_cc": 2501,
					"max_cc": 99999,
					"fee_pkr": 9e3
				}
			],
			"kpk": [
				{
					"min_cc": 0,
					"max_cc": 1e3,
					"fee_pkr": 1e3
				},
				{
					"min_cc": 1001,
					"max_cc": 1300,
					"fee_pkr": 1500
				},
				{
					"min_cc": 1301,
					"max_cc": 1600,
					"fee_pkr": 2500
				},
				{
					"min_cc": 1601,
					"max_cc": 2e3,
					"fee_pkr": 4e3
				},
				{
					"min_cc": 2001,
					"max_cc": 2500,
					"fee_pkr": 6e3
				},
				{
					"min_cc": 2501,
					"max_cc": 99999,
					"fee_pkr": 8e3
				}
			]
		},
		"fixed_administrative_fees": {
			"smart_card_pkr": {
				"punjab": 550,
				"islamabad": 1215,
				"sindh": 550,
				"kpk": 600
			},
			"biometric_and_stamp_pkr": 800
		}
	}
};
//#endregion
//#region src/agents/calculators/FuelCostAgent.js
var FuelCostAgent = class {
	static calculate({ cc, dailyKm, cityRatio = .8 }) {
		const key = String(cc);
		const engineData = calculatorsConfig_default.fuel_calculator.engine_averages_kml[key] || calculatorsConfig_default.fuel_calculator.engine_averages_kml["1000"];
		const fuelPrice = calculatorsConfig_default.fuel_calculator.fuel_prices_pkr[engineData.fuel_type];
		const monthlyKm = dailyKm * 30;
		const totalLiters = monthlyKm * cityRatio / engineData.city + monthlyKm * (1 - cityRatio) / engineData.highway;
		return {
			monthlyCost: Math.round(totalLiters * fuelPrice),
			totalLiters: totalLiters.toFixed(1),
			fuelPrice,
			label: engineData.label
		};
	}
};
//#endregion
//#region src/agents/calculators/VehicleTaxAgent.js
var PROVINCES = {
	PUNJAB: "PUNJAB",
	ISLAMABAD: "ISLAMABAD",
	SINDH: "SINDH"
};
var VehicleTaxAgent = class {
	static calculate({ province = "ISLAMABAD", engineCc = 1300, invoiceVal = 4e6, vehicleAge = 0, isFiler = true, isEv = false, isTransfer = false, paymentDate = /* @__PURE__ */ new Date() }) {
		const age = Math.max(0, parseInt(vehicleAge, 10) || 0);
		const cc = parseInt(engineCc, 10) || 0;
		const val = parseFloat(invoiceVal) || 0;
		const normProvince = (province || "").toUpperCase();
		let provincialToken = 0;
		let isLifetime = false;
		if (isEv) {
			if (normProvince === PROVINCES.ISLAMABAD) provincialToken = 0;
			else if (normProvince === PROVINCES.PUNJAB) provincialToken = val * .003 * .05;
			else if (normProvince === PROVINCES.SINDH) provincialToken = 1e3 * .25;
		} else if (cc <= 1e3) {
			isLifetime = true;
			provincialToken = age === 0 ? 2e4 : 0;
		} else if (normProvince === PROVINCES.ISLAMABAD) provincialToken = cc <= 2e3 ? val * .0025 : val * .0035;
		else if (normProvince === PROVINCES.PUNJAB) if (cc <= 2e3) provincialToken = val * (val <= 2e6 ? .002 : .003);
		else provincialToken = val * .004;
		else if (normProvince === PROVINCES.SINDH) if (cc <= 1300) provincialToken = 2500;
		else if (cc <= 1500) provincialToken = 4500;
		else if (cc <= 2e3) provincialToken = 6e3;
		else if (cc <= 2500) provincialToken = 12e3;
		else provincialToken = 15e3;
		let tokenRebate = 0, tokenSurcharge = 0;
		if (!isLifetime && provincialToken > 0) {
			const payMonth = paymentDate.getMonth() + 1;
			if (payMonth === 7 || payMonth === 8) tokenRebate = provincialToken * .1;
			else if (payMonth >= 10 && payMonth <= 12) tokenSurcharge = provincialToken * .2;
			else if (payMonth >= 1 && payMonth <= 3) tokenSurcharge = provincialToken * .5;
			else if (payMonth >= 4 && payMonth <= 6) tokenSurcharge = provincialToken * 1;
		}
		const netProvincialToken = Math.max(0, provincialToken - tokenRebate + tokenSurcharge);
		let fbrSec234 = 0;
		if (!isEv && age < 10 && !isLifetime) {
			const baseRate = [
				{
					limit: 1e3,
					rate: 800
				},
				{
					limit: 1199,
					rate: 1500
				},
				{
					limit: 1299,
					rate: 1750
				},
				{
					limit: 1499,
					rate: 2500
				},
				{
					limit: 1599,
					rate: 3750
				},
				{
					limit: 1999,
					rate: 4500
				},
				{
					limit: Infinity,
					rate: 1e4
				}
			].find((b) => cc <= b.limit)?.rate || 0;
			fbrSec234 = isFiler ? baseRate : baseRate * 2;
		}
		let fbrSec231b = 0;
		if (isTransfer) if (age < 5) {
			let baseWht = 0;
			if (isEv) baseWht = val >= 5e6 ? 2e4 : 0;
			else baseWht = [
				{
					limit: 850,
					rate: 0
				},
				{
					limit: 1e3,
					rate: 5e3
				},
				{
					limit: 1300,
					rate: 7500
				},
				{
					limit: 1600,
					rate: 12500
				},
				{
					limit: 1800,
					rate: 18750
				},
				{
					limit: 2e3,
					rate: 25e3
				},
				{
					limit: 2500,
					rate: 37500
				},
				{
					limit: 3e3,
					rate: 5e4
				},
				{
					limit: Infinity,
					rate: 62500
				}
			].find((b) => cc <= b.limit)?.rate || 0;
			const whtRate = isFiler ? baseWht : baseWht * 3;
			fbrSec231b = Math.max(0, whtRate * (1 - .1 * age));
		} else fbrSec231b = 0;
		let mraTransferFee = 0, smartCardFee = 0, biometricFee = isTransfer ? 300 : 0;
		if (isTransfer) if (normProvince === PROVINCES.PUNJAB) {
			mraTransferFee = cc <= 1e3 ? 2750 : cc <= 1800 ? 3850 : 5500;
			smartCardFee = 550;
		} else if (normProvince === PROVINCES.ISLAMABAD) {
			mraTransferFee = cc <= 1e3 ? 1500 : cc <= 1800 ? 2500 : 3500;
			smartCardFee = 1500;
		} else {
			mraTransferFee = cc <= 1e3 ? 1e3 : cc <= 1800 ? 1500 : 2500;
			smartCardFee = 1e3;
		}
		const totalAnnualToken = netProvincialToken + fbrSec234;
		const totalTransferCost = mraTransferFee + fbrSec231b + smartCardFee + biometricFee;
		return {
			provincialTokenBase: Math.round(provincialToken),
			netProvincialToken: Math.round(netProvincialToken),
			fbrSection234: Math.round(fbrSec234),
			fbrSection231b: Math.round(fbrSec231b),
			mraTransferFee: Math.round(mraTransferFee),
			smartCardFee: Math.round(smartCardFee),
			biometricFee: Math.round(biometricFee),
			totalAnnualToken: Math.round(totalAnnualToken),
			totalTransferCost: Math.round(totalTransferCost),
			totalPayable: Math.round(isTransfer ? totalAnnualToken + totalTransferCost : totalAnnualToken),
			isLifetimeToken: isLifetime,
			vehicleAge: age
		};
	}
};
//#endregion
//#region src/utils/calculatorEngine.js
var calculateFuelCost = (params) => FuelCostAgent.calculate(params);
var calculateVehicleCharges = (params) => VehicleTaxAgent.calculate(params);
//#endregion
//#region src/utils/calculatorEngine.selftest.mjs
/**
* calculatorEngine.selftest.mjs
*
* Node smoke test for the updated VehicleTaxAgent.
*/
var passed = 0;
var failed = 0;
function check(label, condition, detail = "") {
	if (condition) {
		passed++;
		console.log(`  PASS  ${label}${detail ? ` - ${detail}` : ""}`);
	} else {
		failed++;
		console.log(`  FAIL  ${label}${detail ? ` - ${detail}` : ""}`);
	}
}
console.log("\n[1] Fuel cost");
var cc = 1e3;
var r = calculateFuelCost({
	cc,
	dailyKm: 40
});
check(`cc=${cc} produces a positive monthly cost`, Number.isFinite(r.monthlyCost) && r.monthlyCost > 0);
console.log("\n[2] Vehicle Tax and Transfer");
var t0 = calculateVehicleCharges({
	province: "Punjab",
	engineCc: 1300,
	isFiler: true,
	vehicleAge: 0,
	isTransfer: true
});
var t5 = calculateVehicleCharges({
	province: "Punjab",
	engineCc: 1300,
	isFiler: true,
	vehicleAge: 5,
	isTransfer: true
});
var t10 = calculateVehicleCharges({
	province: "Punjab",
	engineCc: 1300,
	isFiler: true,
	vehicleAge: 10,
	isTransfer: true
});
check("year 0 pays the full 231B advance tax", t0.fbrSection231b > 0, `Rs. ${t0.fbrSection231b}`);
check("year 5 pays zero 231B", t5.fbrSection231b === 0, `Rs. ${t5.fbrSection231b}`);
check("year 10 pays zero 234", t10.fbrSection234 === 0, `Rs. ${t10.fbrSection234}`);
console.log(`\n${"=".repeat(62)}`);
console.log(`  ${passed} passed, ${failed} failed`);
console.log(`${"=".repeat(62)}\n`);
process.exit(failed ? 1 : 0);
//#endregion
export {};
