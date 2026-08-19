export class TokenTaxAgent {
  static calculate({ province, cc, isFiler, invoiceValue = 0, vehicleAge = 0, isEv = false }) {
    const provKey = (province || 'islamabad').toUpperCase();
    
    let provincial_token = 0;
    let is_lifetime = false;

    if (isEv) {
      if (provKey === 'ISLAMABAD') {
        provincial_token = 0.0;
      } else if (provKey === 'PUNJAB') {
        provincial_token = invoiceValue * 0.003 * 0.05; // 95% waiver
      } else if (provKey === 'SINDH') {
        provincial_token = 1000.0 * 0.25; // 75% concession
      }
    } else {
      if (cc <= 1000) {
        if (vehicleAge === 0) {
          provincial_token = 20000.0;
          is_lifetime = true;
        } else {
          provincial_token = 0.0;
          is_lifetime = true;
        }
      } else {
        if (provKey === 'ISLAMABAD') {
          if (cc <= 2000) {
            provincial_token = invoiceValue * 0.0025;
          } else {
            provincial_token = invoiceValue * 0.0035;
          }
        } else if (provKey === 'PUNJAB') {
          if (cc <= 2000) {
            provincial_token = invoiceValue * (invoiceValue <= 2000000 ? 0.0020 : 0.0030);
          } else {
            provincial_token = invoiceValue * 0.0040;
          }
        } else if (provKey === 'SINDH') {
          if (cc <= 1300) {
            provincial_token = 2500.0;
          } else if (cc <= 1500) {
            provincial_token = 4500.0;
          } else if (cc <= 2000) {
            provincial_token = 6000.0;
          } else if (cc <= 2500) {
            provincial_token = 12000.0;
          } else {
            provincial_token = 15000.0;
          }
        }
      }
    }

    let token_rebate = 0.0;
    let token_surcharge = 0.0;

    if (!is_lifetime && provincial_token > 0) {
      const pay_month = new Date().getMonth() + 1;
      if (pay_month === 7 || pay_month === 8) {
        token_rebate = provincial_token * 0.10;
        // The spec mentioned +5% e-Pay in Punjab, but python didn't explicitly implement it in the main rebate variable. 
        // We'll leave it as the python code did.
      } else if (pay_month >= 10 && pay_month <= 12) {
        token_surcharge = provincial_token * 0.20;
      } else if (pay_month >= 1 && pay_month <= 3) {
        token_surcharge = provincial_token * 0.50;
      } else if (pay_month >= 4 && pay_month <= 6) {
        token_surcharge = provincial_token * 1.00;
      }
    }

    const net_token_tax = Math.max(0.0, provincial_token - token_rebate + token_surcharge);

    let fbr_sec_234 = 0.0;
    if (!isEv && vehicleAge < 10 && !is_lifetime) {
      const sec_234_bands = [
        { limit: 1000, rate: 800 },
        { limit: 1199, rate: 1500 },
        { limit: 1299, rate: 1750 },
        { limit: 1499, rate: 2500 },
        { limit: 1599, rate: 3750 },
        { limit: 1999, rate: 4500 },
        { limit: Infinity, rate: 10000 }
      ];
      for (const band of sec_234_bands) {
        if (cc <= band.limit) {
          fbr_sec_234 = isFiler ? band.rate : band.rate * 2;
          break;
        }
      }
    }

    const totalAnnualTax = net_token_tax + fbr_sec_234;

    return {
      provincialTokenBase: Math.round(provincial_token),
      tokenRebate: Math.round(token_rebate),
      tokenSurcharge: Math.round(token_surcharge),
      netProvincialToken: Math.round(net_token_tax),
      fbrSec234: Math.round(fbr_sec_234),
      totalAnnualTax: Math.round(totalAnnualTax),
      isLifetimePaid: is_lifetime
    };
  }
}
