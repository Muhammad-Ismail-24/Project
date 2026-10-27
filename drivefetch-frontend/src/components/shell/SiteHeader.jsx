import { useEffect, useState } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import ThemeToggle from './ThemeToggle';
import { NAV_LINKS } from './navLinks';
import { Spinner } from '../ui/Loaders';

const logo = '/drivefetch-logo.png';
const logoWhite = '/drivefetch-logo-white.png';

/**
 * Sticky header. Slides away while scrolling down and back on any scroll up,
 * with a thin red reading-progress line along its bottom edge. While the menu
 * is open it turns transparent and sits above the menu, so the Menu button
 * becomes the Close button in the same spot.
 */
export default function SiteHeader({ user, isAuthenticated, isLoading, menuOpen, onToggleMenu, onOpenAccount, onOpenSignIn }) {
  const firstName = user?.name?.split(' ')[0] || 'Account';
  const initial = (user?.name || 'U').trim().charAt(0).toUpperCase();
  const { pathname } = useLocation();
  const [hidden, setHidden] = useState(false);
  const [scrolled, setScrolled] = useState(false);

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
      ? 'bg-df-grey/90 dark:bg-black/90 backdrop-blur-md border-neutral-200 dark:border-zinc-800'
      : 'bg-df-grey dark:bg-black border-neutral-200 dark:border-zinc-800';

  return (
    <header className={`df-header sticky top-0 ${menuOpen ? 'z-[85]' : 'z-50'} border-b ${chrome} ${isHidden ? 'is-hidden' : ''}`}>
      <div className="px-4 sm:px-6 lg:px-10 h-16 sm:h-[68px] flex items-center justify-between gap-4">
        <div className="flex items-center gap-6 lg:gap-11 min-w-0">
          <Link to="/" aria-label="DriveFetch home" className="shrink-0 grid">
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
          <nav aria-label="Main" className={`hidden lg:flex items-center gap-7 text-[15px] font-semibold transition-opacity duration-300 ${menuOpen ? 'opacity-0 pointer-events-none' : ''}`}>
            {NAV_LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                className={({ isActive }) =>
                  `df-link py-1.5 transition-colors ${
                    isActive ? 'text-black dark:text-zinc-50 [background-image:linear-gradient(#E5202E,#E5202E)]' : 'text-neutral-600 hover:text-black dark:text-zinc-400 dark:hover:text-zinc-50'
                  }`
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="flex items-center gap-2 sm:gap-2.5">
          <div className={`flex items-center gap-2 sm:gap-2.5 transition-opacity duration-300 ${menuOpen ? 'opacity-0 pointer-events-none' : ''}`}>
            <ThemeToggle className="hidden sm:flex" />
            {isLoading ? (
              <span className="w-11 h-11 flex items-center justify-center" aria-label="Checking sign-in"><Spinner className="w-5 h-5" /></span>
            ) : isAuthenticated && user ? (
              <button
                type="button"
                onClick={onOpenAccount}
                aria-haspopup="dialog"
                className="df-btn-ink h-11 pl-1 pr-3 text-[13px]"
              >
                {user.picture ? (
                  <img src={user.picture} alt="" className="w-9 h-9 object-cover" referrerPolicy="no-referrer" />
                ) : (
                  <span className="w-9 h-9 bg-df-red text-white flex items-center justify-center text-base">{initial}</span>
                )}
                <span className="hidden sm:block uppercase">{firstName}</span>
              </button>
            ) : (
              <button type="button" onClick={onOpenSignIn} className="hidden sm:inline-flex df-btn-ink">
                Sign in with Google
              </button>
            )}
          </div>
          <button
            type="button"
            onClick={onToggleMenu}
            aria-expanded={menuOpen}
            aria-controls="df-menu"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            className={`h-11 pl-3 pr-3.5 flex items-center gap-3 text-[15px] font-extrabold tracking-wide uppercase ${menuOpen ? 'is-active text-white' : 'text-black dark:text-zinc-50'}`}
          >
            <span className="df-roll hidden sm:inline-grid" aria-hidden="true"><span>Menu</span><span>Close</span></span>
            <span className="df-burger relative w-6 h-[10px] flex flex-col justify-between" aria-hidden="true">
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
