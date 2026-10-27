/**
 * Maps a listing's city to the region label and short code shown on the
 * number-plate graphic. These are display labels only, not real registration
 * numbers: the plate shows CITY CODE + MODEL YEAR.
 */
const CITIES = {
  lahore: ['PUNJAB', 'LHR'],
  karachi: ['SINDH', 'KHI'],
  islamabad: ['ISLAMABAD', 'ISB'],
  rawalpindi: ['PUNJAB', 'RWP'],
  peshawar: ['KPK', 'PEW'],
  multan: ['PUNJAB', 'MUX'],
  faisalabad: ['PUNJAB', 'FSD'],
  gujranwala: ['PUNJAB', 'GRW'],
  sialkot: ['PUNJAB', 'SKT'],
  hyderabad: ['SINDH', 'HYD'],
  quetta: ['BALOCHISTAN', 'QTA'],
  sargodha: ['PUNJAB', 'SGD'],
  bahawalpur: ['PUNJAB', 'BWP'],
  abbottabad: ['KPK', 'ABT'],
  mardan: ['KPK', 'MRD'],
  sukkur: ['SINDH', 'SKZ'],
  gujrat: ['PUNJAB', 'GRT'],
  wah: ['PUNJAB', 'WAH'],
};

export function cityMeta(city) {
  const key = String(city || '').trim().toLowerCase();
  if (!key) return { region: 'PAKISTAN', code: 'PK' };
  const hit = CITIES[key] || Object.entries(CITIES).find(([name]) => key.includes(name))?.[1];
  if (hit) return { region: hit[0], code: hit[1] };
  return { region: 'PAKISTAN', code: key.replace(/[^a-z]/g, '').slice(0, 3).toUpperCase() || 'PK' };
}

/** Price helpers. Accepts numbers or strings like "PKR 4,750,000". */
export function toRupees(price) {
  if (typeof price === 'number') return price;
  const n = parseInt(String(price || '').replace(/[^\d]/g, ''), 10);
  return Number.isFinite(n) ? n : null;
}

export function formatLac(price) {
  const rs = toRupees(price);
  if (!rs) return typeof price === 'string' && price ? price : 'Price on call';
  if (rs >= 10000000) {
    const crore = rs / 10000000;
    return `${crore % 1 === 0 ? crore : crore.toFixed(2)} crore`;
  }
  const lac = rs / 100000;
  return `${lac % 1 === 0 ? lac : Number(lac.toFixed(2))} lac`;
}

export function formatPKR(n) {
  const rs = toRupees(n);
  return rs ? `PKR ${rs.toLocaleString('en-US')}` : '';
}

export function stripEmoji(text) {
  return String(text || '').replace(/^[\p{Extended_Pictographic}️‍\s]+/u, '').trim();
}
