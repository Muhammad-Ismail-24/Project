import configData from '../data/calculatorsConfig.json';

const { fuel_calculator, provincial_token_tax, fbr_section_234_wht, transfer_calculator } = configData;

export const formatPKR = (amount) => {
  return new Intl.NumberFormat('en-PK', {
    style: 'currency',
    currency: 'PKR',
    maximumFractionDigits: 0
  }).format(amount);
};

export const calculateFuelCost = (engineType, totalKm, cityPercentage) => {
  const engineData = fuel_calculator.engine_averages_kml[engineType];
  const fuelPrice = fuel_calculator.fuel_prices_pkr[engineData.fuel_type];
  
  const cityDist = totalKm * (cityPercentage / 100);
  const hwyDist = totalKm * ((100 - cityPercentage) / 100);
  
  const litersUsed = (cityDist / engineData.city) + (hwyDist / engineData.highway);
  const totalCost = litersUsed * fuelPrice;
  
  return {
    totalCost,
    litersUsed,
    fuelPrice,
    fuelType: engineData.fuel_type === 'petrol_ron92' ? 'Petrol' : 'Diesel',
    engineData
  };
};

export const calculateTokenTax = ({ province, cc, invoiceValue, regYear, filerStatus, useEpay }) => {
  let baseTax = 0;
  const currentYear = new Date().getFullYear();
  const age = currentYear - regYear;
  
  // Base Tax
  if (province === 'islamabad') {
    if (cc <= 1000) baseTax = 0; // Lifetime paid
    else if (cc <= 2000) baseTax = invoiceValue * 0.0025;
    else baseTax = invoiceValue * 0.0035;
  } else if (province === 'punjab') {
    if (cc <= 1000) baseTax = 0; // Lifetime paid
    else if (cc <= 2000) baseTax = invoiceValue * 0.0020;
    else baseTax = invoiceValue * 0.0030;
    
    if (useEpay) {
      baseTax = baseTax * 0.95; // 5% ePay discount
    }
  } else if (province === 'sindh' || province === 'kpk') {
    const slabData = provincial_token_tax[province].slabs.find(s => cc >= s.min_cc && cc <= s.max_cc);
    if (slabData) {
      baseTax = slabData.annual_base_mvt_pkr;
      if (slabData.lifetime_pkr && baseTax === 1000) {
         // Simplify: assuming lifetime might be already paid if old, but we'll show annual if applicable.
         baseTax = slabData.annual_base_mvt_pkr; 
      }
    }
  }
  
  // WHT Section 234
  let wht = 0;
  if (age < fbr_section_234_wht.exemption_age_years) {
    const whtSlab = fbr_section_234_wht.slabs.find(s => cc >= s.min_cc && cc <= s.max_cc);
    if (whtSlab) {
      wht = filerStatus === 'filer' ? whtSlab.filer_pkr : whtSlab.non_filer_pkr;
    }
  }
  
  return {
    baseTax,
    wht,
    total: baseTax + wht,
    age
  };
};

export const calculateTransferCost = ({ province, cc, regYear, filerStatus, isSpeculative, includePlates }) => {
  const currentYear = new Date().getFullYear();
  const age = Math.max(0, currentYear - regYear);
  
  // 1. Advance Tax Sec 231B
  let advanceTax = 0;
  const whtSlab = transfer_calculator.fbr_section_231b_advance_tax.slabs.find(s => cc >= s.min_cc && cc <= s.max_cc);
  if (whtSlab) {
    let baseAdvTax = filerStatus === 'filer' ? whtSlab.filer_pkr : whtSlab.non_filer_pkr;
    
    // Depreciation
    const depreciationPct = Math.min(50, 10 * age) / 100;
    advanceTax = baseAdvTax * (1 - depreciationPct);
    
    if (isSpeculative) {
       advanceTax += baseAdvTax; 
    }
  }
  
  // 2. MRA Fee
  let mraFee = 0;
  const provSlabs = transfer_calculator.provincial_mra_transfer_fees[province];
  const mraSlab = provSlabs.find(s => cc >= s.min_cc && cc <= s.max_cc);
  if (mraSlab) mraFee = mraSlab.fee_pkr;
  
  // 3. Admin Fees
  const smartCardFee = transfer_calculator.fixed_administrative_fees.smart_card_issuance_pkr[province];
  const bioFee = transfer_calculator.fixed_administrative_fees.biometric_verification_pkr.default_total_both_parties_pkr;
  let platesFee = includePlates ? transfer_calculator.fixed_administrative_fees.number_plates_if_applicable_pkr[province] : 0;
  
  return {
    advanceTax,
    mraFee,
    smartCardFee,
    bioFee,
    platesFee,
    total: advanceTax + mraFee + smartCardFee + bioFee + platesFee,
    age
  };
};
