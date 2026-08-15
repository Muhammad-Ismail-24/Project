import config from '../../data/calculatorsConfig.json';

export class TokenTaxAgent {
  static calculate({ province, cc, isFiler, invoiceValue = 0, vehicleAge = 0, useEPay = false }) {
    const provKey = (province || 'islamabad').toLowerCase();
    const provData = config.token_tax_calculator.provincial_token_tax[provKey] || config.token_tax_calculator.provincial_token_tax.islamabad;
    
    let baseTax = 0;
    let isLifetimePaid = false;

    // Check if province uses invoice-based rules (Islamabad & Punjab)
    if (provData.slabs[0]?.tax_type) {
      const slab = provData.slabs.find(s => cc >= s.min_cc && cc <= s.max_cc);
      if (slab) {
        if (slab.tax_type === 'fixed') {
          baseTax = 0; // Lifetime token tax assumed paid at registration
          isLifetimePaid = true;
        } else {
          baseTax = invoiceValue * slab.rate;
        }
      }
      if (provKey === 'punjab' && useEPay && provData.epay_discount_pct) {
        baseTax = baseTax * (1 - provData.epay_discount_pct / 100);
      }
    } else {
      const slab = provData.slabs.find(s => cc >= s.min_cc && cc <= s.max_cc);
      baseTax = slab ? slab.amount_pkr : 0;
    }

    // Federal Section 234 WHT (10-Year Age Exemption Rule)
    let wht = 0;
    const whtConfig = config.token_tax_calculator.fbr_section_234_wht;
    if (vehicleAge < whtConfig.exemption_age_years) {
      const whtSlab = whtConfig.slabs.find(s => cc >= s.min_cc && cc <= s.max_cc);
      if (whtSlab) {
        wht = isFiler ? whtSlab.filer_pkr : whtSlab.non_filer_pkr;
      }
    }

    return {
      baseTax: Math.round(baseTax),
      wht: Math.round(wht),
      totalAnnualTax: Math.round(baseTax + wht),
      isLifetimePaid
    };
  }
}
