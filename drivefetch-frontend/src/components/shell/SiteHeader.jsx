import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import ThemeToggle from './ThemeToggle';

const logo = '/drivefetch-logo.png';
const logoWhite = '/drivefetch-logo-white.png';

const PAGES = {
  '/': ['01', 'Discover'],
  '/recommend': ['02', 'Matchmaker'],
  '/chat': ['03', 'Chat'],
  '/calculators': ['04', 'Calculators'],
  '/saved': ['05', 'Saved cars'],
  '/about': ['06', 'About'],
  '/privacy': ['—', 'Privacy'],
};

/**
 * Top bar: logo, the current page, theme toggle and the Menu button. Every
 * other destination and setting lives in the menu.
 *
 * Slides away while scrolling down and returns on any scroll up, with a thin
 * red reading-progress line along its bottom edge. While the menu is open it
 * turns transparent and sits above the menu, so Menu becomes Close in place.
 */
export default function SiteHeader({ user, isAuthenticated, menuOpen, onToggleMenu }) {
  const { pathname } = useLocation();
  const [hidden, setHidden] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const page = PAGES[pathname];
  const initial = (user?.name || 'U').trim().charAt(0).toUpperCase();

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
  const chrome = menuOpen
    ? 'bg-transparent border-transparent text-white'
    : scrolled
      ? 'bg-white/85 dark:bg-df-night/85 backdrop-blur-md border-neutral-200 dark:border-zinc-800'
      : 'bg-white dark:bg-df-night border-neutral-200 dark:border-zinc-800';

  return (
    <header className={`df-header sticky top-0 ${menuOpen ? 'z-[85]' : 'z-50'} border-b ${chrome} ${isHidden ? 'is-hidden' : ''}`}>
      <div className="px-4 sm:px-6 lg:px-10 h-16 sm:h-[72px] grid grid-cols-[1fr_auto] md:grid-cols-[1fr_auto_1fr] items-center gap-4">
        <Link to="/" aria-label="DriveFetch home" className="justify-self-start grid">
          <img
            id="df-header-logo"
            src={logo}
            alt="DriveFetch"
            width="105"
            height="34"
            className={`[grid-area:1/1] h-[30px] sm:h-[34px] w-auto object-contain transition-opacity duration-300 ${menuOpen ? 'opacity-0' : 'opacity-100'}`}
          />
          <img
            src={logoWhite}
            alt=""
            aria-hidden="true"
            width="105"
            height="34"
            className={`[grid-area:1/1] h-[30px] sm:h-[34px] w-auto object-contain transition-opacity duration-300 ${menuOpen ? 'opacity-100' : 'opacity-0'}`}
          />
        </Link>

        {/* Where you are. Rolls to the new name on every page change. */}
        <div aria-hidden="true" className={`hidden md:flex items-center gap-3 font-mono text-[13px] font-semibold tracking-[0.1em] uppercase transition-opacity duration-300 ${menuOpen ? 'opacity-0' : ''}`}>
          {page ? (
            <span key={pathname} className="flex items-center gap-3 animate-df-fade-up">
              <span className="text-df-red-dark dark:text-df-red">{page[0]}</span>
              <span className="w-6 h-px bg-current opacity-40" />
              <span>{page[1]}</span>
            </span>
          ) : null}
        </div>

        <div className="justify-self-end flex items-center gap-2 sm:gap-3">
          <ThemeToggle onDark={menuOpen} />
          <button
            type="button"
            onClick={onToggleMenu}
            aria-expanded={menuOpen}
            aria-controls="df-menu"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            className={`df-menu-btn group h-11 flex items-center gap-3 text-[14px] font-extrabold tracking-[0.08em] uppercase ${isAuthenticated && user ? 'pl-1' : 'pl-4'} pr-4 ${
              menuOpen
                ? 'is-active bg-white text-black'
                : 'bg-black text-white dark:bg-zinc-50 dark:text-black'
            }`}
          >
            {isAuthenticated && user ? (
              user.picture ? (
                <img src={user.picture} alt="" className="w-9 h-9 object-cover" referrerPolicy="no-referrer" />
              ) : (
                <span className="w-9 h-9 bg-df-red text-white flex items-center justify-center text-base">{initial}</span>
              )
            ) : null}
            <span className="df-roll hidden sm:inline-grid" aria-hidden="true"><span>Menu</span><span>Close</span></span>
            <span className="df-burger relative w-5 h-[10px] flex flex-col justify-between" aria-hidden="true">
              <span className="block h-[2px] w-full bg-current" />
              <span className="block h-[2px] w-full bg-current" />
            </span>
          </button>
        </div>
      </div>
      <div aria-hidden="true" className={`absolute left-0 right-0 bottom-[-1px] h-[2px] bg-df-red df-progress transition-opacity ${menuOpen ? 'opacity-0' : ''}`} />
    </header>
  );
}
