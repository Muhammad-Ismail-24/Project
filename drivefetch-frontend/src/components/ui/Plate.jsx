/**
 * Plate — the number-plate graphic used across the C design.
 * White plate, black border, with an outer ring in the page's ink colour
 * (black in light theme, white in dark theme) so it reads on both.
 */
const SIZES = {
  xs: { box: 'border-2 px-1.5 pt-[1px] pb-[3px]', top: 'text-[6px] tracking-[0.16em]', main: 'text-[14px]' },
  sm: { box: 'border-[3px] px-2 pt-[2px] pb-1', top: 'text-[7px] tracking-[0.18em]', main: 'text-[18px]' },
  md: { box: 'border-[3px] px-2.5 pt-1 pb-1.5', top: 'text-[8px] tracking-[0.18em]', main: 'text-[24px]' },
  lg: { box: 'border-[5px] px-5 pt-1.5 pb-2.5', top: 'text-[11px] tracking-[0.22em]', main: 'text-[44px]' },
  xl: { box: 'border-[8px] px-10 pt-2.5 pb-4', top: 'text-[16px] tracking-[0.3em]', main: 'text-[length:clamp(96px,14vw,200px)]' },
};

export default function Plate({ top, main, size = 'md', className = '', ring = true }) {
  const s = SIZES[size] || SIZES.md;
  return (
    <span
      className={`inline-flex flex-col items-center bg-white text-black border-black ${s.box} ${ring ? 'ring-2 ring-black dark:ring-white' : ''} ${className}`}
    >
      {top ? <span className={`font-extrabold leading-none ${s.top}`}>{top}</span> : null}
      <span className={`font-black leading-none whitespace-nowrap [font-stretch:70%] tracking-[0.04em] ${s.main}`}>{main}</span>
    </span>
  );
}
