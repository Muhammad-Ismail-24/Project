import { useTheme } from '../../contexts/ThemeContext';

/**
 * Light/dark switch. The icon turns as it swaps. `onDark` styles it for a
 * dark or red background (used while the menu is open).
 */
export default function ThemeToggle({ className = '', onDark = false }) {
  const { theme, toggleTheme } = useTheme();
  const dark = theme === 'dark';
  const tone = onDark
    ? 'border-white/60 text-white hover:bg-white hover:text-black'
    : 'border-neutral-300 text-black hover:border-black hover:bg-black hover:text-white dark:border-zinc-700 dark:text-zinc-50 dark:hover:border-zinc-50 dark:hover:bg-zinc-50 dark:hover:text-black';
  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}
      title={dark ? 'Light theme' : 'Dark theme'}
      className={`w-11 h-11 flex items-center justify-center border transition-colors duration-300 ${tone} ${className}`}
    >
      <span key={theme} className="flex animate-df-spin-in">
        {dark ? (
          <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
          </svg>
        ) : (
          <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round">
            <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" />
          </svg>
        )}
      </span>
    </button>
  );
}
