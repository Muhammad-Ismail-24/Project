import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import ThemeToggle from './ThemeToggle';
import GoogleMark from './GoogleMark';
import { useScrollTo } from '../motion/SmoothScroll';

const logo = '/drivefetch-logo.png';
const logoWhite = '/drivefetch-logo-white.png';

/**
 * Top bar. Left: the menu icon, then the logo.
 * Right: a Discover button (always one click from the search), a Google
 * sign-in button (only when signed out) and the theme toggle.
 * Every page, the account and settings live in the menu.
 *
 * Slides away while scrolling down and returns on any scroll up, with a thin
 * red reading-progress line along its bottom edge. While the menu is open it
 * turns transparent and sits above the menu, so the icon becomes a close (×)
 * in place.
 */
export default function SiteHeader({ isAuthenticated, isLoading, menuOpen, onToggleMenu }) {
  const { pathname } = useLocation();
  const [hidden, setHidden] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const scrollTo = useScrollTo();

  // Already on Discover: take the user back up to the search box instead.
  const onDiscover = (e) => {
    if (pathname !== '/') return;
    e.preventDefault();
    scrollTo(0);
    setTimeout(() => document.getElementById('home-q')?.focus({ preventScroll: true }), 650);
  };

  useEffect(() => {
    let lastY = window.scrollY;
    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        ticking = false;
        const y = window.scrollY;
        const delta = y - lastY;
        if (Math.abs(delta) > 4) {
          setHidden(delta > 0 && y > 160);
          lastY = y;
        }
        setScrolled(y > 8);
      });
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => { setHidden(false); }, [pathname]);

  const isHidden = hidden && !menuOpen;
  const showSignIn = !isLoading && !isAuthenticated;
  const chrome = menuOpen
    ? 'bg-transparent border-transparent text-white'
    : scrolled
      ? 'bg-white/85 dark:bg-df-night/85 backdrop-blur-md border-neutral-200 dark:border-zinc-800'
      : 'bg-white dark:bg-df-night border-neutral-200 dark:border-zinc-800';

  return (
    <header className={`df-header sticky top-0 ${menuOpen ? 'z-[85]' : 'z-50'} border-b ${chrome} ${isHidden ? 'is-hidden' : ''}`}>
      <div className="px-4 sm:px-6 lg:px-10 h-16 sm:h-[72px] flex items-center justify-between gap-4">
        <div className="flex items-center gap-2.5 sm:gap-5">
          <button
            type="button"
            onClick={onToggleMenu}
            aria-expanded={menuOpen}
            aria-controls="df-menu"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            className={`df-menu-btn w-11 h-11 shrink-0 flex items-center justify-center ${
              menuOpen ? 'is-active bg-white text-black' : 'bg-black text-white dark:bg-zinc-50 dark:text-black'
            }`}
          >
            <span className="df-burger relative w-5 h-[10px] flex flex-col justify-between" aria-hidden="true">
              <span className="block h-[2px] w-full bg-current" />
              <span className="block h-[2px] w-full bg-current" />
            </span>
          </button>

          <Link to="/" aria-label="DriveFetch home" className="grid">
            <img
              id="df-header-logo"
              src={logo}
              alt="DriveFetch"
              width="105"
              height="34"
              className={`[grid-area:1/1] h-[28px] sm:h-[34px] w-auto object-contain transition-opacity duration-300 ${menuOpen ? 'opacity-0' : 'opacity-100'}`}
            />
            <img
              src={logoWhite}
              alt=""
              aria-hidden="true"
              width="105"
              height="34"
              className={`[grid-area:1/1] h-[28px] sm:h-[34px] w-auto object-contain transition-opacity duration-300 ${menuOpen ? 'opacity-100' : 'opacity-0'}`}
            />
          </Link>
        </div>

        <div className="flex items-center gap-2 sm:gap-3">
          <Link
            to="/"
            onClick={onDiscover}
            aria-label="Discover: search used cars"
            className={`df-btn-red h-11 w-11 sm:w-auto px-0 sm:px-4 gap-2 transition-opacity duration-300 ${menuOpen ? 'opacity-0 pointer-events-none' : ''}`}
          >
            <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="square"><circle cx="10.5" cy="10.5" r="6.5" /><path d="M15.5 15.5L21 21" /></svg>
            <span className="hidden sm:inline">Discover</span>
          </Link>
          {showSignIn ? (
            <button
              type="button"
              onClick={() => { window.location.href = '/auth/login'; }}
              aria-label="Sign in with Google"
              className={`df-btn-outline h-11 w-11 sm:w-auto px-0 sm:px-4 gap-2.5 transition-opacity duration-300 ${menuOpen ? 'opacity-0 pointer-events-none' : ''}`}
            >
              <span className="w-[22px] h-[22px] bg-white flex items-center justify-center shrink-0"><GoogleMark /></span>
              <span className="hidden sm:inline">Sign in with Google</span>
            </button>
          ) : null}
          <ThemeToggle onDark={menuOpen} />
        </div>
      </div>
      <div aria-hidden="true" className={`absolute left-0 right-0 bottom-[-1px] h-[2px] bg-df-red df-progress transition-opacity ${menuOpen ? 'opacity-0' : ''}`} />
    </header>
  );
}
