export class TransferFeeAgent {
  static calculate({ province, cc, isBuyerFiler, invoiceValue = 0, vehicleAge = 0, isEv = false }) {
    const provKey = (province || 'punjab').toUpperCase();

    let fbr_sec_231b = 0.0;
    
    if (vehicleAge < 5) {
      if (isEv) {
        fbr_sec_231b = invoiceValue >= 5000000 ? 20000.0 : 0.0;
        if (!isBuyerFiler) fbr_sec_231b *= 3; // 3x penalty for non-filers
        const depreciation = 0.10 * vehicleAge;
        fbr_sec_231b = fbr_sec_231b * (1.0 - depreciation);
      } else {
        const sec_231b_bands = [
          { limit: 850, rate: 0 },
          { limit: 1000, rate: 5000 },
          { limit: 1300, rate: 7500 },
          { limit: 1600, rate: 12500 },
          { limit: 1800, rate: 18750 },
          { limit: 2000, rate: 25000 },
          { limit: 2500, rate: 37500 },
          { limit: 3000, rate: 50000 },
          { limit: Infinity, rate: 62500 }
        ];
        
        let base_wht = 0;
        for (const band of sec_231b_bands) {
          if (cc <= band.limit) {
            base_wht = band.rate;
            break;
          }
        }
        
        const wht_rate = isBuyerFiler ? base_wht : base_wht * 3;
        const depreciation = 0.10 * vehicleAge;
        fbr_sec_231b = wht_rate * (1.0 - depreciation);
      }
    } else {
      fbr_sec_231b = 0.0; // Exempt after 5 years
    }

    let mra_transfer_fee = 0.0;
    if (cc <= 1000) {
      mra_transfer_fee = provKey === 'PUNJAB' ? 2750 : 1500;
    } else if (cc <= 1800) {
      mra_transfer_fee = provKey === 'PUNJAB' ? 3850 : 2500;
    } else {
      mra_transfer_fee = provKey === 'PUNJAB' ? 5500 : 3500;
    }

    const smart_card_fee = provKey === 'PUNJAB' ? 550 : 1500;
    const biometric_fee = 300;

    const totalTransferCost = fbr_sec_231b + mra_transfer_fee + smart_card_fee + biometric_fee;

    return {
      mraFee: Math.round(mra_transfer_fee),
      advanceTax231b: Math.round(fbr_sec_231b),
      smartCardFee: Math.round(smart_card_fee),
      biometricFee: Math.round(biometric_fee),
      totalTransferCost: Math.round(totalTransferCost)
    };
  }
}
