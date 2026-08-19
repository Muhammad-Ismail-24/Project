export const PROVINCES = {
  PUNJAB: 'PUNJAB',
  ISLAMABAD: 'ISLAMABAD',
  SINDH: 'SINDH',
};

export class VehicleTaxAgent {
  static calculate({
    province = 'ISLAMABAD',
    engineCc = 1300,
    invoiceVal = 4000000,
    vehicleAge = 0,
    isFiler = true,
    isEv = false,
    isTransfer = false,
    sellerRetainingNumber = false,
    needsNewPlates = false,
    isInterProvincial = false,
    paymentDate = new Date(),
  }) {
    const age = Math.max(0, parseInt(vehicleAge, 10) || 0);
    const cc = parseInt(engineCc, 10) || 0;
    const val = parseFloat(invoiceVal) || 0;
    const normProvince = (province || '').toUpperCase();

    // 1. PROVINCIAL TOKEN TAX
    let provincialToken = 0;
    let isLifetime = false;

    if (isEv) {
      if (normProvince === PROVINCES.ISLAMABAD) provincialToken = 0;
      else if (normProvince === PROVINCES.PUNJAB) provincialToken = val * 0.003 * 0.05;
      else if (normProvince === PROVINCES.SINDH) provincialToken = 1000 * 0.25;
    } else {
      if (cc <= 1000) {
        isLifetime = true;
        provincialToken = age === 0 ? 20000 : 0;
      } else {
        if (normProvince === PROVINCES.ISLAMABAD) {
          provincialToken = cc <= 2000 ? val * 0.0025 : val * 0.0035;
        } else if (normProvince === PROVINCES.PUNJAB) {
          if (cc <= 2000) provincialToken = val * (val <= 2000000 ? 0.002 : 0.003);
          else provincialToken = val * 0.004;
        } else if (normProvince === PROVINCES.SINDH) {
          if (cc <= 1300) provincialToken = 2500;
          else if (cc <= 1500) provincialToken = 4500;
          else if (cc <= 2000) provincialToken = 6000;
          else if (cc <= 2500) provincialToken = 12000;
          else provincialToken = 15000;
        }
      }
    }

    // 2. REBATES & SURCHARGES
    let tokenRebate = 0, tokenSurcharge = 0;
    if (!isLifetime && provincialToken > 0) {
      const payMonth = paymentDate.getMonth() + 1;
      if (payMonth === 7 || payMonth === 8) tokenRebate = provincialToken * 0.1;
      else if (payMonth >= 10 && payMonth <= 12) tokenSurcharge = provincialToken * 0.2;
      else if (payMonth >= 1 && payMonth <= 3) tokenSurcharge = provincialToken * 0.5;
      else if (payMonth >= 4 && payMonth <= 6) tokenSurcharge = provincialToken * 1.0;
    }
    const netProvincialToken = Math.max(0, provincialToken - tokenRebate + tokenSurcharge);

    // 3. FBR SECTION 234
    let fbrSec234 = 0;
    if (!isEv && age < 10 && !isLifetime) {
      const sec234Bands = [
        { limit: 1000, rate: 800 }, { limit: 1199, rate: 1500 }, { limit: 1299, rate: 1750 },
        { limit: 1499, rate: 2500 }, { limit: 1599, rate: 3750 }, { limit: 1999, rate: 4500 },
        { limit: Infinity, rate: 10000 },
      ];
      const baseRate = sec234Bands.find((b) => cc <= b.limit)?.rate || 0;
      fbrSec234 = isFiler ? baseRate : baseRate * 2;
    }

    // 4. FBR SECTION 231B
    let fbrSec231b = 0;
    if (isTransfer) {
      if (age < 5) {
        let baseWht = 0;
        if (isEv) baseWht = val >= 5000000 ? 20000 : 0;
        else {
          const sec231bBands = [
            { limit: 850, rate: 0 }, { limit: 1000, rate: 5000 }, { limit: 1300, rate: 7500 },
            { limit: 1600, rate: 12500 }, { limit: 1800, rate: 18750 }, { limit: 2000, rate: 25000 },
            { limit: 2500, rate: 37500 }, { limit: 3000, rate: 50000 }, { limit: Infinity, rate: 62500 },
          ];
          baseWht = sec231bBands.find((b) => cc <= b.limit)?.rate || 0;
        }
        const whtRate = isFiler ? baseWht : baseWht * 3;
        fbrSec231b = Math.max(0, whtRate * (1 - (0.1 * age)));
      } else fbrSec231b = 0;
    }

    // 5. MRA FEES & ADDITIONAL TRANSFER POLICIES
    let mraTransferFee = 0, smartCardFee = 0, biometricFee = isTransfer ? 300 : 0;
    let numberPlateFee = 0, additionalRegMarkFee = 0;

    if (isTransfer) {
      // A. Smart Card Fee
      if (normProvince === PROVINCES.PUNJAB) smartCardFee = 1300;
      else if (normProvince === PROVINCES.ISLAMABAD) smartCardFee = 1500;
      else smartCardFee = 1000;

      // Base MRA Transfer Fee
      if (normProvince === PROVINCES.PUNJAB) {
        mraTransferFee = cc <= 1000 ? 2750 : cc <= 1800 ? 3850 : 5500;
      } else if (normProvince === PROVINCES.ISLAMABAD) {
        mraTransferFee = cc <= 1000 ? 1500 : cc <= 1800 ? 2500 : 3500;
      } else {
        mraTransferFee = cc <= 1000 ? 1000 : cc <= 1800 ? 1500 : 2500;
      }

      // B. Security-Featured Number Plate Fee
      const registrationYear = paymentDate.getFullYear() - age;
      const requiresPlates = (registrationYear < 2020) || sellerRetainingNumber || needsNewPlates;
      
      if (requiresPlates) {
        if (normProvince === PROVINCES.PUNJAB) {
          numberPlateFee = 1800;
        } else if (normProvince === PROVINCES.ISLAMABAD) {
          if (cc <= 1000) numberPlateFee = 1200;
          else if (cc <= 1800) numberPlateFee = 2000;
          else numberPlateFee = 3000;
        } else {
          numberPlateFee = 1200;
        }
      }

      // C. Additional Registration Mark Fee
      if (sellerRetainingNumber || isInterProvincial) {
        if (normProvince === PROVINCES.PUNJAB) {
          additionalRegMarkFee = 4000;
        }
        // Islamabad/Sindh is 0
      }
    }

    const totalAnnualToken = netProvincialToken + fbrSec234;
    const totalTransferCost = mraTransferFee + fbrSec231b + smartCardFee + biometricFee + numberPlateFee + additionalRegMarkFee;

    return {
      provincialTokenBase: Math.round(provincialToken),
      netProvincialToken: Math.round(netProvincialToken),
      fbrSection234: Math.round(fbrSec234),
      fbrSection231b: Math.round(fbrSec231b),
      mraTransferFee: Math.round(mraTransferFee),
      smartCardFee: Math.round(smartCardFee),
      biometricFee: Math.round(biometricFee),
      numberPlateFee: Math.round(numberPlateFee),
      additionalRegMarkFee: Math.round(additionalRegMarkFee),
      totalAnnualToken: Math.round(totalAnnualToken),
      totalTransferCost: Math.round(totalTransferCost),
      totalPayable: Math.round(isTransfer ? totalAnnualToken + totalTransferCost : totalAnnualToken),
      isLifetimeToken: isLifetime,
      vehicleAge: age,
    };
  }
}
