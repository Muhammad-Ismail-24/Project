import { useMemo, useState } from 'react';
import SEO from '../components/SEO';
import { calculatorsSchema } from '../config/seoSchemas';
import { calculateFuelCost, calculateVehicleCharges } from '../utils/calculatorEngine';

const CC_OPTIONS = [
  { value: 660, label: '660cc (Alto, Mira, Dayz)' },
  { value: 800, label: '800cc (Mehran, old Alto)' },
  { value: 1000, label: '1000cc (Cultus, Wagon R, Vitz)' },
  { value: 1200, label: '1200cc (City 1.2, Stonic, Swift)' },
  { value: 1300, label: '1300cc (Yaris 1.3, City 1.3)' },
  { value: 1500, label: '1500cc (Civic 1.5T, BR-V)' },
  { value: 1800, label: '1800cc (Corolla Grande, Civic 1.8)' },
  { value: 1801, label: '1.5–1.8L hybrid (Aqua, Vezel, HEV)' },
  { value: 2500, label: '2.5L+ diesel (Fortuner, Revo)' },
];

const PROVINCES = [
  { value: 'ISLAMABAD', label: 'Islamabad' },
  { value: 'PUNJAB', label: 'Punjab' },
  { value: 'SINDH', label: 'Sindh' },
  { value: 'KPK', label: 'KPK', soon: true },
  { value: 'BALOCHISTAN', label: 'Balochistan', soon: true },
];

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

const pk = (n) => `PKR ${Math.round(n || 0).toLocaleString('en-US')}`;
const lac = (n) => {
  const v = (n || 0) / 100000;
  return `${v >= 100 ? v.toFixed(1) : v.toFixed(2)} lac`;
};

function Slider({ id, label, value, display, min, max, step, onChange }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex justify-between gap-4">
        <label htmlFor={id} className="text-sm font-bold">{label}</label>
        <span className="font-mono text-[15px] font-semibold">{display}</span>
      </div>
      <input id={id} type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} className="w-full h-7 accent-df-red cursor-pointer" />
    </div>
  );
}

function Check({ label, checked, onChange, disabled, note }) {
  return (
    <label className={`flex items-center gap-2.5 min-h-[48px] px-3.5 border border-black dark:border-zinc-700 text-sm font-bold cursor-pointer ${disabled ? 'opacity-60 cursor-not-allowed' : 'hover:bg-df-grey dark:hover:bg-zinc-900'}`}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} className="w-[18px] h-[18px] accent-df-red" />
      <span>{label}{note ? <span className="font-medium df-muted"> {note}</span> : null}</span>
    </label>
  );
}

function Section({ n, title, children }) {
  return (
    <fieldset className="flex flex-col gap-4 border-0 p-0 m-0">
      <legend className="df-display text-[30px] mb-4 float-left w-full">{n} · {title}</legend>
      {children}
    </fieldset>
  );
}

export default function CalculatorsHub() {
  const nowMonth = new Date().getMonth() + 1;
  const [priceLac, setPriceLac] = useState(47.5);
  const [cc, setCc] = useState(1800);
  const [age, setAge] = useState(6);
  const [isEv, setIsEv] = useState(false);
  const [province, setProvince] = useState('PUNJAB');
  const [isFiler, setIsFiler] = useState(true);
  const [month, setMonth] = useState(nowMonth);
  const [includeTransfer, setIncludeTransfer] = useState(true);
  const [sellerKeepsNumber, setSellerKeepsNumber] = useState(false);
  const [newPlates, setNewPlates] = useState(false);
  const [interProvincial, setInterProvincial] = useState(false);
  const [dailyKm, setDailyKm] = useState(40);
  const [cityPct, setCityPct] = useState(80);
  const [copied, setCopied] = useState(false);

  const year = new Date().getFullYear();
  const platesForced = includeTransfer && (year - age) < 2020;

  const r = useMemo(() => calculateVehicleCharges({
    province,
    engineCc: cc,
    invoiceVal: priceLac * 100000,
    vehicleAge: age,
    isFiler,
    isEv,
    isTransfer: includeTransfer,
    sellerRetainingNumber: sellerKeepsNumber,
    needsNewPlates: newPlates,
    isInterProvincial: interProvincial,
    paymentDate: new Date(year, month - 1, 15),
  }), [province, cc, priceLac, age, isFiler, isEv, includeTransfer, sellerKeepsNumber, newPlates, interProvincial, month, year]);

  const fuel = useMemo(() => (isEv ? { monthlyCost: 0, totalLiters: '0', label: '' } : calculateFuelCost({ cc, dailyKm, cityRatio: cityPct / 100 })), [cc, dailyKm, cityPct, isEv]);

  const price = priceLac * 100000;
  const fuelYear = (fuel.monthlyCost || 0) * 12;
  // totalTransferCost already includes FBR 231B.
  const transferCost = includeTransfer ? r.totalTransferCost : 0;
  const extra = r.totalAnnualToken + transferCost + fuelYear;
  const total = price + extra;
  const rebate = r.provincialTokenBase - r.netProvincialToken;

  const lines = [];
  const add = (k, v, tone) => lines.push({ k, v, tone });
  add('Car price', pk(price), 'bold');
  if (r.isLifetimeToken) add('Token tax', age === 0 ? `${pk(r.netProvincialToken)} (lifetime, paid once)` : 'Lifetime token, already paid');
  else {
    add(`Provincial token tax (${PROVINCES.find((p) => p.value === province)?.label})`, pk(r.provincialTokenBase));
    if (rebate > 0) add('Early-payment rebate (Jul–Aug)', `− ${pk(rebate)}`);
    if (rebate < 0) add(`Late surcharge (${MONTHS[month - 1]})`, `+ ${pk(-rebate)}`, 'red');
  }
  add(`FBR Sec 234 withholding${isFiler ? '' : ' (non-filer ×2)'}`, pk(r.fbrSection234));
  if (includeTransfer) {
    add('FBR Sec 231B advance tax', age >= 5 ? 'Exempt (5+ years old)' : pk(r.fbrSection231b), !isFiler && age < 5 ? 'red' : undefined);
    add('MRA transfer fee', pk(r.mraTransferFee));
    add('Smart card', pk(r.smartCardFee));
    add('NADRA biometrics', pk(r.biometricFee));
    add(`Security number plates${platesForced ? ' (required, pre-2020)' : ''}`, pk(r.numberPlateFee));
    if (r.additionalRegMarkFee > 0) add('Additional registration mark fee', pk(r.additionalRegMarkFee), 'red');
  }
  add(isEv ? 'Fuel (electric, not calculated)' : `Fuel · 12 months (${dailyKm} km/day)`, pk(fuelYear));

  const copyText = () => {
    const text = [`DriveFetch cost breakdown (${MONTHS[month - 1]} ${year})`, ...lines.map((l) => `${l.k}: ${l.v}`), `TOTAL first year: ${pk(total)}`].join('\n');
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    }).catch(() => {});
  };
  const shareUrl = `https://wa.me/?text=${encodeURIComponent(`First-year cost on DriveFetch: ${pk(total)} (car ${pk(price)} + ${pk(extra)} running and paperwork)`)}`;

  return (
    <div className="w-full">
      <SEO
        title="Car Tax, Transfer Fee & Fuel Cost Calculators Pakistan"
        description="Token tax (ICT, Punjab, Sindh), FBR 231B and 234, transfer fees and monthly fuel cost in one calculator, with this year's rates."
        path="/calculators"
        keywords={['token tax calculator Pakistan', 'vehicle transfer fee calculator FBR 231B', 'car fuel cost calculator Pakistan', 'Section 234 withholding tax vehicle']}
        schema={calculatorsSchema}
      />

      <section className="px-5 sm:px-10 pt-12 sm:pt-14 pb-8 flex flex-wrap justify-between items-end gap-5">
        <h1 className="df-display text-[length:clamp(60px,9vw,136px)]">What it <span className="text-df-red">really</span> costs.</h1>
        <p className="max-w-[380px] text-[17px] leading-relaxed df-muted">Fuel, token tax, FBR withholding and transfer fees in one form, using the current fiscal year’s Excise and FBR rates.</p>
      </section>

      <div className="flex flex-wrap border-t-2 border-black dark:border-zinc-50">
        <form onSubmit={(e) => e.preventDefault()} className="flex-[999_1_560px] min-w-0 px-5 sm:px-10 py-8 sm:py-10 flex flex-col gap-10">
          <Section n="1" title="The car">
            <Slider id="ca-price" label="Price / invoice value" value={priceLac} display={`${priceLac} lac`} min={5} max={250} step={0.5} onChange={setPriceLac} />
            <div className="flex flex-col gap-2">
              <label htmlFor="ca-cc" className="text-sm font-bold">Engine</label>
              <select id="ca-cc" value={cc} onChange={(e) => setCc(Number(e.target.value))} className="df-select">
                {CC_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
            <Slider id="ca-age" label="Vehicle age" value={age} display={age === 0 ? 'New' : `${age} yr${age === 1 ? '' : 's'} (reg. ${year - age})`} min={0} max={20} step={1} onChange={setAge} />
            <div className="flex flex-wrap gap-2.5">
              <Check label="Electric vehicle" checked={isEv} onChange={setIsEv} />
            </div>
          </Section>

          <Section n="2" title="You">
            <span className="text-sm font-bold">Registered in</span>
            <div role="radiogroup" aria-label="Province" className="flex flex-wrap">
              {PROVINCES.map((p) => (
                <button
                  key={p.value}
                  type="button"
                  role="radio"
                  aria-checked={province === p.value}
                  disabled={p.soon}
                  onClick={() => setProvince(p.value)}
                  className={`min-h-[52px] px-4 -mr-px -mb-px border border-black dark:border-zinc-700 text-sm font-bold flex flex-col justify-center items-start ${
                    province === p.value ? 'bg-black text-white dark:bg-zinc-50 dark:text-black' : ''
                  } ${p.soon ? 'opacity-50 cursor-not-allowed' : 'hover:bg-df-grey dark:hover:bg-zinc-900'}`}
                >
                  <span>{p.label}</span>
                  {p.soon ? <span className="text-[11px] font-medium">coming soon</span> : null}
                </button>
              ))}
            </div>
            <div className="flex flex-wrap gap-2.5">
              <Check label="Active tax filer" checked={isFiler} onChange={setIsFiler} />
              <label className="flex items-center gap-2.5 min-h-[48px] px-3.5 border border-black dark:border-zinc-700 text-sm font-bold">
                Paying token in
                <select value={month} onChange={(e) => setMonth(Number(e.target.value))} aria-label="Payment month" className="h-9 bg-transparent font-bold outline-none cursor-pointer dark:bg-df-night">
                  {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
                </select>
              </label>
            </div>
          </Section>

          <Section n="3" title="Transfer">
            <label className="flex items-center justify-between min-h-[52px] px-4 bg-df-grey dark:bg-zinc-900 text-[15px] font-bold cursor-pointer">
              Include transfer into my name
              <input type="checkbox" checked={includeTransfer} onChange={(e) => setIncludeTransfer(e.target.checked)} className="w-5 h-5 accent-df-red" />
            </label>
            {includeTransfer && (
              <div className="flex flex-wrap gap-2.5 animate-df-fade-up">
                <Check label="Seller keeps the number" note="(CNIC-linked)" checked={sellerKeepsNumber} onChange={setSellerKeepsNumber} />
                <Check label="New security plates" note={platesForced ? '(required before 2020)' : ''} checked={newPlates || platesForced} disabled={platesForced} onChange={setNewPlates} />
                <Check label="Coming from another province" checked={interProvincial} onChange={setInterProvincial} />
              </div>
            )}
          </Section>

          <Section n="4" title="Driving">
            <Slider id="ca-km" label="Daily distance" value={dailyKm} display={`${dailyKm} km`} min={0} max={200} step={5} onChange={setDailyKm} />
            <Slider id="ca-city" label="Share in city traffic" value={cityPct} display={`${cityPct}%`} min={0} max={100} step={10} onChange={setCityPct} />
            {!isEv && fuel.label ? <p className="text-sm df-muted">Using averages for {fuel.label}.</p> : null}
          </Section>
        </form>

        <aside aria-live="polite" className="flex-[1_1_420px] min-w-0 bg-df-red text-white px-5 sm:px-9 py-8 sm:py-10 flex flex-col gap-5">
          <span className="text-[15px] font-extrabold">First year, all in</span>
          <span className="df-display text-[length:clamp(64px,7vw,104px)]">{lac(total)}</span>
          <span className="text-[17px] font-bold text-black">{lac(extra)} on top of the price</span>

          <div className="bg-white text-black px-5 py-5 flex flex-col font-mono text-[13.5px]">
            <span className="font-sans text-[13px] font-extrabold tracking-[0.08em] pb-2.5 border-b-2 border-dashed border-black">ITEMISED</span>
            {lines.map((l) => (
              <div key={l.k} className={`flex justify-between gap-3 py-2 border-b border-neutral-200 ${l.tone === 'bold' ? 'font-bold' : ''} ${l.tone === 'red' ? 'text-df-red-dark' : ''}`}>
                <span>{l.k}</span><span className="whitespace-nowrap text-right">{l.v}</span>
              </div>
            ))}
            <div className="flex justify-between pt-3 text-[15px] font-bold"><span>TOTAL</span><span>{pk(total)}</span></div>
          </div>

          <div className="flex flex-col gap-1.5 text-[15px]">
            <span><strong>{pk((fuel.monthlyCost || 0) + r.totalAnnualToken / 12)}</strong> a month to run (fuel + token)</span>
            {!isEv ? <span>{fuel.totalLiters} L of fuel a month</span> : null}
          </div>

          <div className="flex flex-wrap gap-2 mt-auto">
            <button type="button" onClick={copyText} className="h-12 px-4 bg-black text-white text-sm font-extrabold hover:bg-white hover:text-black">
              {copied ? 'Copied ✓' : 'Copy breakdown'}
            </button>
            <a href={shareUrl} target="_blank" rel="noopener noreferrer" className="h-12 px-4 inline-flex items-center border-2 border-white text-sm font-extrabold hover:bg-white hover:text-df-red">
              Share on WhatsApp
            </a>
          </div>
          <p className="text-[12.5px] leading-relaxed">Estimates from DriveFetch’s calculator. Check with your Excise office before paying.</p>
        </aside>
      </div>
    </div>
  );
}
