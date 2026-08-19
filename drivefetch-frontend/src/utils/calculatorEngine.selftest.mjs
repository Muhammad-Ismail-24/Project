/**
 * calculatorEngine.selftest.mjs
 *
 * Node smoke test for the updated VehicleTaxAgent.
 */
import { calculateFuelCost, calculateVehicleCharges } from './calculatorEngine.js';

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

console.log('\n[1] Fuel cost');
const cc = 1000;
const r = calculateFuelCost({ cc, dailyKm: 40 });
check(`cc=${cc} produces a positive monthly cost`,
  Number.isFinite(r.monthlyCost) && r.monthlyCost > 0);

console.log('\n[2] Vehicle Tax and Transfer');
const t0 = calculateVehicleCharges({ province: 'Punjab', engineCc: 1300, isFiler: true, vehicleAge: 0, isTransfer: true });
const t5 = calculateVehicleCharges({ province: 'Punjab', engineCc: 1300, isFiler: true, vehicleAge: 5, isTransfer: true });
const t10 = calculateVehicleCharges({ province: 'Punjab', engineCc: 1300, isFiler: true, vehicleAge: 10, isTransfer: true });

check('year 0 pays the full 231B advance tax', t0.fbrSection231b > 0, `Rs. ${t0.fbrSection231b}`);
check('year 5 pays zero 231B', t5.fbrSection231b === 0, `Rs. ${t5.fbrSection231b}`);
check('year 10 pays zero 234', t10.fbrSection234 === 0, `Rs. ${t10.fbrSection234}`);

console.log(`\n${'='.repeat(62)}`);
console.log(`  ${passed} passed, ${failed} failed`);
console.log(`${'='.repeat(62)}\n`);
process.exit(failed ? 1 : 0);
