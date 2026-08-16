/**
 * calculatorEngine.selftest.mjs
 *
 * Node smoke test for the three calculator agents behind CalculatorsHub.jsx.
 * Focuses on the two statutory age rules that the UI had no control for until
 * the Vehicle Age sliders were wired in:
 *
 *   - FBR Section 234  : token-tax WHT stops once the car turns 10
 *   - FBR Section 231B : transfer advance tax depreciates 10%/yr to zero at 10
 *
 * Bundled through Vite before running, because the agents import
 * calculatorsConfig.json with a bare specifier that plain Node will not resolve.
 *
 * Run:  npx vite build --ssr src/utils/calculatorEngine.selftest.mjs --outDir .selftest \
 *         && node .selftest/calculatorEngine.selftest.mjs
 */
import {
  calculateFuelCost,
  calculateTokenTax,
  calculateTransferCost,
} from './calculatorEngine.js';

let passed = 0;
let failed = 0;

function check(label, condition, detail = '') {
  if (condition) {
    passed++;
    console.log(`  PASS  ${label}${detail ? ` - ${detail}` : ''}`);
  } else {
    failed++;
    console.log(`  FAIL  ${label}${detail ? ` - ${detail}` : ''}`);
  }
}

console.log('\n[1] Fuel cost — every CC_OPTIONS value resolves to real data');
const CC_VALUES = [660, 800, 1000, 1200, 1300, 1500, 1800, 1801, 2500];
for (const cc of CC_VALUES) {
  const r = calculateFuelCost({ cc, dailyKm: 40 });
  check(`cc=${cc} produces a positive monthly cost`,
    Number.isFinite(r.monthlyCost) && r.monthlyCost > 0,
    `Rs. ${r.monthlyCost.toLocaleString()} (${r.label.slice(0, 34)})`);
}
// The 1801 hybrid sentinel must be cheaper to run than 1800cc petrol.
const petrol1800 = calculateFuelCost({ cc: 1800, dailyKm: 40 }).monthlyCost;
const hybrid1801 = calculateFuelCost({ cc: 1801, dailyKm: 40 }).monthlyCost;
check('1801 hybrid is cheaper than 1800cc petrol',
  hybrid1801 < petrol1800, `${hybrid1801} < ${petrol1800}`);
// 2500 must use diesel pricing, not petrol.
check('2500 uses high-speed diesel price',
  calculateFuelCost({ cc: 2500, dailyKm: 40 }).fuelPrice === 383.95,
  String(calculateFuelCost({ cc: 2500, dailyKm: 40 }).fuelPrice));
check('cost scales with distance',
  calculateFuelCost({ cc: 1300, dailyKm: 80 }).monthlyCost >
  calculateFuelCost({ cc: 1300, dailyKm: 40 }).monthlyCost);

console.log('\n[2] Token tax — Section 234 ten-year exemption (needs the age slider)');
const young = calculateTokenTax({ province: 'Islamabad', cc: 1300, isFiler: true, invoiceValue: 4000000, vehicleAge: 0 });
const old = calculateTokenTax({ province: 'Islamabad', cc: 1300, isFiler: true, invoiceValue: 4000000, vehicleAge: 10 });
check('WHT is charged on a 0-year-old car', young.wht > 0, `Rs. ${young.wht}`);
check('WHT is zero once the car turns 10', old.wht === 0, `Rs. ${old.wht}`);
check('total drops by exactly the WHT at year 10',
  young.totalAnnualTax - old.totalAnnualTax === young.wht,
  `${young.totalAnnualTax} -> ${old.totalAnnualTax}`);
check('age 9 still pays WHT (boundary)',
  calculateTokenTax({ province: 'Islamabad', cc: 1300, isFiler: true, invoiceValue: 4000000, vehicleAge: 9 }).wht > 0);
check('non-filer WHT is double the filer rate',
  calculateTokenTax({ province: 'Islamabad', cc: 1300, isFiler: false, invoiceValue: 4000000, vehicleAge: 0 }).wht ===
  young.wht * 2);

console.log('\n[3] Token tax — lifetime-paid slab and invoice-based slabs');
const lifetime = calculateTokenTax({ province: 'Islamabad', cc: 1000, isFiler: true, vehicleAge: 0 });
check('<=1000cc ICT is flagged lifetime-paid', lifetime.isLifetimePaid === true);
check('lifetime-paid still owes Section 234 WHT while under 10 yrs',
  lifetime.totalAnnualTax > 0, `Rs. ${lifetime.totalAnnualTax}`);
const lifetimeOld = calculateTokenTax({ province: 'Islamabad', cc: 1000, isFiler: true, vehicleAge: 12 });
check('lifetime-paid AND over 10 yrs owes nothing at all',
  lifetimeOld.isLifetimePaid && lifetimeOld.totalAnnualTax === 0,
  `Rs. ${lifetimeOld.totalAnnualTax} -> UI shows "LIFETIME PAID (PKR 0/yr)"`);
check('invoice value drives the >1000cc ICT slab',
  calculateTokenTax({ province: 'Islamabad', cc: 1300, isFiler: true, invoiceValue: 8000000, vehicleAge: 0 }).baseTax >
  young.baseTax);
check('Punjab e-pay discount undercuts Islamabad at the same invoice',
  calculateTokenTax({ province: 'Punjab', cc: 1300, isFiler: true, invoiceValue: 4000000, vehicleAge: 0, useEPay: true }).baseTax <
  young.baseTax);
check('Sindh uses flat slabs, not invoice value',
  calculateTokenTax({ province: 'Sindh', cc: 1300, isFiler: true, invoiceValue: 4000000, vehicleAge: 0 }).baseTax ===
  calculateTokenTax({ province: 'Sindh', cc: 1300, isFiler: true, invoiceValue: 9000000, vehicleAge: 0 }).baseTax);

console.log('\n[4] Transfer fee — Section 231B depreciation (needs the age slider)');
const t0 = calculateTransferCost({ province: 'Punjab', cc: 1300, isBuyerFiler: true, vehicleAge: 0 });
const t5 = calculateTransferCost({ province: 'Punjab', cc: 1300, isBuyerFiler: true, vehicleAge: 5 });
const t10 = calculateTransferCost({ province: 'Punjab', cc: 1300, isBuyerFiler: true, vehicleAge: 10 });
check('year 0 pays the full 231B advance tax', t0.advanceTax231b > 0, `Rs. ${t0.advanceTax231b}`);
check('year 5 pays exactly 50%',
  t5.advanceTax231b === Math.round(t0.advanceTax231b * 0.5),
  `${t0.advanceTax231b} -> ${t5.advanceTax231b}`);
check('year 10 pays zero 231B', t10.advanceTax231b === 0, `Rs. ${t10.advanceTax231b}`);
check('total still includes MRA + admin fees at year 10',
  t10.totalTransferCost === t10.mraFee + t10.smartCardFee + t10.biometricFee,
  `Rs. ${t10.totalTransferCost}`);
check('breakdown sums to the total',
  t0.totalTransferCost === t0.mraFee + t0.advanceTax231b + t0.smartCardFee + t0.biometricFee);
check('non-filer buyer pays more',
  calculateTransferCost({ province: 'Punjab', cc: 1300, isBuyerFiler: false, vehicleAge: 0 }).advanceTax231b >
  t0.advanceTax231b);
check('Islamabad smart-card fee differs from Punjab',
  calculateTransferCost({ province: 'Islamabad', cc: 1300, isBuyerFiler: true, vehicleAge: 0 }).smartCardFee !==
  t0.smartCardFee);

console.log('\n[5] Province coverage (config has islamabad/punjab/sindh/kpk only)');
for (const p of ['Islamabad', 'Punjab', 'Sindh', 'KPK']) {
  const tok = calculateTokenTax({ province: p, cc: 1300, isFiler: true, invoiceValue: 4000000, vehicleAge: 0 });
  const tr = calculateTransferCost({ province: p, cc: 1300, isBuyerFiler: true, vehicleAge: 0 });
  check(`${p} resolves both calculators`,
    Number.isFinite(tok.totalAnnualTax) && Number.isFinite(tr.totalTransferCost),
    `token Rs.${tok.totalAnnualTax} / transfer Rs.${tr.totalTransferCost}`);
}
const baloch = calculateTransferCost({ province: 'Balochistan', cc: 1300, isBuyerFiler: true, vehicleAge: 0 });
const punjabRef = calculateTransferCost({ province: 'Punjab', cc: 1300, isBuyerFiler: true, vehicleAge: 0 });
console.log(`  NOTE  Balochistan has no entry in calculatorsConfig.json; the agent`);
console.log(`        silently falls back to Punjab (transfer) / Islamabad (token).`);
console.log(`        Balochistan total = Rs.${baloch.totalTransferCost}, Punjab = Rs.${punjabRef.totalTransferCost}`);

console.log(`\n${'='.repeat(62)}`);
console.log(`  ${passed} passed, ${failed} failed`);
console.log(`${'='.repeat(62)}\n`);
process.exit(failed ? 1 : 0);
