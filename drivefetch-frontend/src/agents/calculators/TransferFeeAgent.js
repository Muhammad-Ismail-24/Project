import config from '../../data/calculatorsConfig.json';

export class TransferFeeAgent {
  static calculate({ province, cc, isBuyerFiler, vehicleAge = 0 }) {
    const provKey = (province || 'punjab').toLowerCase();
    const transConfig = config.transfer_calculator;

    // 1. Provincial MRA Fee
    const mraList = transConfig.provincial_mra_transfer_fees[provKey] || transConfig.provincial_mra_transfer_fees.punjab;
    const mraSlab = mraList.find(s => cc >= s.min_cc && cc <= s.max_cc);
    const mraFee = mraSlab ? mraSlab.fee_pkr : 0;

    // 2. FBR Section 231B Advance Tax (10% Annual Depreciation Rule)
    let advanceTax231b = 0;
    const tax231bSlab = transConfig.fbr_section_231b_advance_tax.slabs.find(s => cc >= s.min_cc && cc <= s.max_cc);
    
    if (tax231bSlab) {
      const base231b = isBuyerFiler ? tax231bSlab.filer_pkr : tax231bSlab.non_filer_pkr;
      const maxYears = transConfig.fbr_section_231b_advance_tax.max_depreciation_years;
      
      // 10+ years old = 100% reduction (Tax becomes 0)
      const discountFactor = vehicleAge >= maxYears ? 1.0 : vehicleAge * transConfig.fbr_section_231b_advance_tax.annual_depreciation_pct;
      advanceTax231b = base231b * (1 - discountFactor);
    }

    // 3. Administrative Fees
    const smartCardFee = transConfig.fixed_administrative_fees.smart_card_pkr[provKey] || 550;
    const biometricAndStampFee = transConfig.fixed_administrative_fees.biometric_and_stamp_pkr;

    return {
      mraFee,
      advanceTax231b: Math.round(advanceTax231b),
      smartCardFee,
      biometricFee: biometricAndStampFee,
      totalTransferCost: Math.round(mraFee + advanceTax231b + smartCardFee + biometricAndStampFee)
    };
  }
}
