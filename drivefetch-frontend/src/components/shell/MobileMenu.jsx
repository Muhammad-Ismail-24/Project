import { NavLink } from 'react-router-dom';
import { useTheme } from '../../contexts/ThemeContext';
import { NAV_LINKS } from './navLinks';
import useDialog from './useDialog';

const logoWhite = '/drivefetch-logo-white.png';

const LINKS = [...NAV_LINKS.slice(0, 4), { to: '/saved', label: 'Saved' }, NAV_LINKS[4]];

export default function MobileMenu({ open, onClose, isAuthenticated, user, onOpenSignIn, onOpenAccount }) {
  const { theme, chooseTheme } = useTheme();
  const ref = useDialog(open, onClose);
  if (!open) return null;

  return (
    <div
      ref={ref}
      role="dialog"
      aria-modal="true"
      aria-label="Menu"
      className="md:hidden fixed inset-0 z-[80] bg-df-red text-white flex flex-col animate-df-wipe-down"
    >
      <div className="h-16 flex items-center justify-between pl-4 pr-2 border-b-2 border-black/20">
        <img src={logoWhite} alt="DriveFetch" className="h-7 w-auto" />
        <button type="button" onClick={onClose} aria-label="Close menu" data-autofocus className="w-12 h-12 flex items-center justify-center">
          <svg aria-hidden="true" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="square"><path d="M5 5l14 14M19 5L5 19" /></svg>
        </button>
      </div>
      <nav aria-label="Main" className="flex-1 overflow-y-auto px-4 pt-4 flex flex-col">
        {LINKS.map((link, i) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            onClick={onClose}
            style={{ animationDelay: `${i * 40}ms` }}
            className={({ isActive }) =>
              `flex items-baseline justify-between min-h-[72px] border-b-2 border-black/20 animate-df-fade-up ${isActive ? 'text-black' : 'text-white'}`
            }
          >
            <span className="df-display text-[length:clamp(36px,11vw,54px)] leading-none">{link.label}</span>
            <span className="font-mono text-[13px] font-semibold">0{i + 1}</span>
          </NavLink>
        ))}
      </nav>
      <div className="p-4 flex flex-col gap-2.5">
        <div role="radiogroup" aria-label="Theme" className="grid grid-cols-2">
          {['light', 'dark'].map((t) => (
            <button
              key={t}
              type="button"
              role="radio"
              aria-checked={theme === t}
              onClick={() => chooseTheme(t)}
              className={`h-12 border-2 border-black -ml-[2px] first:ml-0 text-sm font-extrabold capitalize ${theme === t ? 'bg-black text-white' : 'text-white'}`}
            >
              {t}
            </button>
          ))}
        </div>
        {isAuthenticated ? (
          <button type="button" onClick={onOpenAccount} className="h-14 bg-black text-white text-base font-extrabold">
            {user?.name ? `Account · ${user.name.split(' ')[0]}` : 'Account'}
          </button>
        ) : (
          <button type="button" onClick={onOpenSignIn} className="h-14 bg-black text-white text-base font-extrabold">
            Sign in with Google
          </button>
        )}
      </div>
    </div>
  );
}
