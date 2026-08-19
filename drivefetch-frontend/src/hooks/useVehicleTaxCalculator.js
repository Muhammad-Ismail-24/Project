import { useState, useMemo } from 'react';
import { calculateVehicleCharges } from '../utils/calculatorEngine';

export function useVehicleTaxCalculator(initialIsTransfer = false) {
  const [province, setProvince] = useState('Islamabad');
  const [engineCc, setEngineCc] = useState(1300);
  const [invoiceVal, setInvoiceVal] = useState(4000000);
  const [vehicleAge, setVehicleAge] = useState(0);
  const [isFiler, setIsFiler] = useState(true);
  const [isTransfer, setIsTransfer] = useState(initialIsTransfer);
  const [sellerRetainingNumber, setSellerRetainingNumber] = useState(false);
  const [needsNewPlates, setNeedsNewPlates] = useState(false);

  const results = useMemo(() => {
    return calculateVehicleCharges({
      province,
      engineCc,
      invoiceVal: engineCc <= 1000 ? 0 : invoiceVal,
      vehicleAge,
      isFiler,
      isEv: false, // Defaulting to false for now, can be expanded later
      isTransfer,
      sellerRetainingNumber,
      needsNewPlates,
      paymentDate: new Date(),
    });
  }, [province, engineCc, invoiceVal, vehicleAge, isFiler, isTransfer, sellerRetainingNumber, needsNewPlates]);

  return {
    state: {
      province,
      engineCc,
      invoiceVal,
      vehicleAge,
      isFiler,
      isTransfer,
      sellerRetainingNumber,
      needsNewPlates,
    },
    setters: {
      setProvince,
      setEngineCc,
      setInvoiceVal,
      setVehicleAge,
      setIsFiler,
      setIsTransfer,
      setSellerRetainingNumber,
      setNeedsNewPlates,
    },
    results,
  };
}
