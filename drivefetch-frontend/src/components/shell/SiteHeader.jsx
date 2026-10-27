import { Link, NavLink } from 'react-router-dom';
const logo = '/drivefetch-logo.png';
import ThemeToggle from './ThemeToggle';
import { NAV_LINKS } from './navLinks';
import { Spinner } from '../ui/Loaders';

export default function SiteHeader({ user, isAuthenticated, isLoading, onOpenMenu, onOpenAccount, onOpenSignIn }) {
  const firstName = user?.name?.split(' ')[0] || 'Account';
  const initial = (user?.name || 'U').trim().charAt(0).toUpperCase();

  return (
    <header className="sticky top-0 z-50 bg-df-grey/95 dark:bg-black/95 backdrop-blur border-b border-neutral-200 dark:border-zinc-800">
      <div className="px-4 sm:px-6 lg:px-10 h-16 sm:h-[68px] flex items-center justify-between gap-4">
        <div className="flex items-center gap-6 lg:gap-11 min-w-0">
          <Link to="/" aria-label="DriveFetch home" className="shrink-0 flex">
            <img src={logo} alt="DriveFetch" className="h-[30px] sm:h-[34px] w-auto object-contain" width="105" height="34" />
          </Link>
          <nav aria-label="Main" className="hidden md:flex items-center gap-6 lg:gap-7 text-[15px] font-semibold">
            {NAV_LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                className={({ isActive }) =>
                  `py-2 border-b-2 transition-colors ${
                    isActive
                      ? 'border-df-red text-black dark:text-zinc-50'
                      : 'border-transparent text-neutral-600 hover:text-black dark:text-zinc-400 dark:hover:text-zinc-50'
                  }`
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="flex items-center gap-2 sm:gap-2.5">
          <ThemeToggle className="hidden sm:flex" />
          {isLoading ? (
            <span className="w-11 h-11 flex items-center justify-center" aria-label="Checking sign-in"><Spinner className="w-5 h-5" /></span>
          ) : isAuthenticated && user ? (
            <>
              <NavLink
                to="/saved"
                className={({ isActive }) =>
                  `hidden sm:flex items-center gap-2 h-11 px-3 text-sm font-bold border transition-colors ${
                    isActive ? 'border-df-red text-df-red-dark dark:text-zinc-50' : 'border-transparent hover:border-black dark:hover:border-zinc-700'
                  }`
                }
              >
                <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"><path d="M6 3h12v18l-6-4-6 4z" /></svg>
                Saved
              </NavLink>
              <button
                type="button"
                onClick={onOpenAccount}
                aria-haspopup="dialog"
                className="h-11 flex items-center gap-2 pl-1 pr-3 bg-black text-white dark:bg-zinc-50 dark:text-black text-[13px] font-extrabold tracking-wide hover:bg-df-red hover:text-white transition-colors"
              >
                {user.picture ? (
                  <img src={user.picture} alt="" className="w-9 h-9 object-cover" referrerPolicy="no-referrer" />
                ) : (
                  <span className="w-9 h-9 bg-df-red text-white flex items-center justify-center text-base">{initial}</span>
                )}
                <span className="hidden sm:block uppercase">{firstName}</span>
              </button>
            </>
          ) : (
            <button type="button" onClick={onOpenSignIn} className="hidden sm:inline-flex df-btn-ink">
              Sign in with Google
            </button>
          )}
          <button
            type="button"
            onClick={onOpenMenu}
            aria-label="Open menu"
            aria-haspopup="dialog"
            className="md:hidden w-11 h-11 flex items-center justify-center text-black dark:text-zinc-50"
          >
            <svg aria-hidden="true" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="square"><path d="M3 6h18M3 12h18M3 18h12" /></svg>
          </button>
        </div>
      </div>
    </header>
  );
}
