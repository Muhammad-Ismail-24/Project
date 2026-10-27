import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { useTheme } from '../../contexts/ThemeContext';
import useDialog from './useDialog';

const LINKS = [
  { to: '/', label: 'Discover', end: true, desc: 'Search seven sites at once, with every ad read for you.' },
  { to: '/recommend', label: 'Matchmaker', desc: 'Describe your life. Get three models that fit, with live ads.' },
  { to: '/chat', label: 'Chat', desc: 'Fuel averages, auction sheets, transfer rules. Just ask.' },
  { to: '/calculators', label: 'Calculators', desc: 'Token tax, transfer fees and fuel, in one receipt.' },
  { to: '/saved', label: 'Saved cars', desc: 'Your garage: notes, stages and side-by-side compare.' },
  { to: '/about', label: 'About', desc: 'Why DriveFetch exists and how it reads an ad.' },
];

const LEAVE_MS = 1000;

/**
 * Full-screen menu. Opening drops two layers (black, then red) from the top,
 * then each link rises out of its own mask, 60ms apart. Closing runs it
 * backwards: links slide up and out, then the layers lift.
 * Inspired by the menu on asiaxp.co.
 */
export default function SiteMenu({ open, onClose, isAuthenticated, user, onOpenSignIn, onOpenAccount }) {
  const { theme, chooseTheme } = useTheme();
  const { pathname } = useLocation();
  const ref = useDialog(open, onClose);
  const [leaving, setLeaving] = useState(false);
  const [hovered, setHovered] = useState(null);
  const wasOpen = useRef(false);

  useEffect(() => {
    const root = document.documentElement;
    if (open) {
      root.classList.add('df-menu-open');
      setLeaving(false);
      wasOpen.current = true;
      return undefined;
    }
    root.classList.remove('df-menu-open');
    if (!wasOpen.current) return undefined;
    wasOpen.current = false;
    setLeaving(true);
    setHovered(null);
    const t = setTimeout(() => setLeaving(false), LEAVE_MS);
    return () => clearTimeout(t);
  }, [open]);

  const active = LINKS.find((l) => (l.end ? pathname === l.to : pathname.startsWith(l.to)));
  const shown = hovered ?? active ?? LINKS[0];
  const state = open ? 'is-open' : leaving ? 'is-leaving' : '';

  return (
    <div
      id="df-menu"
      ref={ref}
      role="dialog"
      aria-modal="true"
      aria-label="Menu"
      aria-hidden={!open}
      data-lenis-prevent
      className={`df-menu fixed inset-0 z-[80] text-white ${state}`}
    >
      <div className="df-menu-layer l0 bg-black" />
      <div className="df-menu-layer l1 bg-df-red" />

      <div className="relative h-full flex flex-col pt-16 sm:pt-[68px] overflow-y-auto">
        <button
          type="button"
          onClick={onClose}
          tabIndex={open ? 0 : -1}
          data-autofocus
          className="sr-only focus-visible:not-sr-only focus-visible:absolute focus-visible:top-20 focus-visible:right-4 focus-visible:px-4 focus-visible:py-2 focus-visible:bg-black focus-visible:text-white focus-visible:font-bold"
        >
          Close menu
        </button>
        <div className="flex-1 grid lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] gap-x-16 px-4 sm:px-6 lg:px-10 pt-6 sm:pt-10">
          <nav aria-label="Main">
            <ul className="df-menu-list flex flex-col" onMouseLeave={() => setHovered(null)}>
              {LINKS.map((link, i) => {
                const isCurrent = link === active;
                return (
                  <li key={link.to} className="relative">
                    <span aria-hidden="true" className="df-mline absolute left-0 right-0 bottom-0 h-px bg-white/35" style={{ '--i': i }} />
                    <NavLink
                      to={link.to}
                      end={link.end}
                      tabIndex={open ? 0 : -1}
                      onMouseEnter={() => setHovered(link)}
                      onFocus={() => setHovered(link)}
                      // A different page closes the menu via the route change, so the
                      // menu's exit doubles as the page transition. Same page: close here.
                      onClick={() => { if (isCurrent) onClose(); }}
                      className="df-menu-link group flex items-center gap-4 sm:gap-6 py-2.5 sm:py-3"
                    >
                      <span className="block overflow-hidden w-8 shrink-0">
                        <span className="df-mi font-mono text-[13px] font-semibold" style={{ '--i': i }}>0{i + 1}</span>
                      </span>
                      <span className="block overflow-hidden pb-[.08em] -mb-[.08em]">
                        <span className="df-mi" style={{ '--i': i }}>
                          <span className="df-menu-word inline-flex items-center gap-4 text-[length:clamp(40px,7vw,104px)] font-bold leading-[1.02] tracking-[-0.02em] [font-stretch:78%]">
                            {link.label}
                            {isCurrent ? <span aria-hidden="true" className="w-3 h-3 sm:w-4 sm:h-4 bg-black rounded-full" /> : null}
                          </span>
                        </span>
                      </span>
                      <svg aria-hidden="true" className="df-menu-arrow ml-auto shrink-0 hidden sm:block" width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="square"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
                    </NavLink>
                  </li>
                );
              })}
            </ul>
          </nav>

          <aside className="hidden lg:flex flex-col justify-between py-4 df-mfade">
            <div className="flex flex-col gap-4 max-w-[360px]">
              <span className="font-mono text-[13px] font-semibold tracking-[0.08em] text-white/70">{String(LINKS.indexOf(shown) + 1).padStart(2, '0')} / {String(LINKS.length).padStart(2, '0')}</span>
              <p key={shown.to} className="text-[26px] leading-snug font-semibold animate-df-fade-up">{shown.desc}</p>
            </div>
            <div className="flex flex-col gap-2 text-[15px] font-semibold">
              <Link to="/privacy" tabIndex={open ? 0 : -1} onClick={() => pathname === '/privacy' && onClose()} className="df-link self-start">Privacy</Link>
              <span className="text-white/70 text-sm">Listings belong to their original sites.</span>
            </div>
          </aside>
        </div>

        <div className="df-mfade px-4 sm:px-6 lg:px-10 py-6 sm:py-8 flex flex-wrap items-end justify-between gap-6">
          <Link
            to="/about#contact"
            tabIndex={open ? 0 : -1}
            onClick={() => pathname === '/about' && onClose()}
            className="group flex flex-col gap-1"
          >
            <span className="font-mono text-[13px] font-semibold tracking-[0.08em] text-white/70">FEEDBACK, BUGS, IDEAS</span>
            <span className="df-link text-[length:clamp(26px,3.4vw,44px)] font-bold leading-tight [font-stretch:80%]">Write to us →</span>
          </Link>
          <div className="flex flex-wrap items-center gap-2.5">
            <div role="radiogroup" aria-label="Theme" className="flex">
              {['light', 'dark'].map((t) => (
                <button
                  key={t}
                  type="button"
                  role="radio"
                  tabIndex={open ? 0 : -1}
                  aria-checked={theme === t}
                  onClick={() => chooseTheme(t)}
                  className={`h-12 px-5 border-2 border-white -ml-[2px] first:ml-0 text-sm font-extrabold capitalize transition-colors ${theme === t ? 'bg-white text-black' : 'text-white hover:bg-white/10'}`}
                >
                  {t}
                </button>
              ))}
            </div>
            {isAuthenticated ? (
              <button type="button" tabIndex={open ? 0 : -1} onClick={onOpenAccount} className="h-12 px-5 bg-black text-white text-sm font-extrabold hover:bg-white hover:text-black transition-colors">
                {user?.name ? `Account · ${user.name.split(' ')[0]}` : 'Account'}
              </button>
            ) : (
              <button type="button" tabIndex={open ? 0 : -1} onClick={onOpenSignIn} className="h-12 px-5 bg-black text-white text-sm font-extrabold hover:bg-white hover:text-black transition-colors">
                Sign in with Google
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
