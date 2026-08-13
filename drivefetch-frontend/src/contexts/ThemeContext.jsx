import { createContext, useContext, useState, useEffect, useCallback } from 'react';

const ThemeContext = createContext({
  theme: 'light',
  toggleTheme: () => {},
});

export function useTheme() {
  return useContext(ThemeContext);
}

/**
 * Determines the initial theme:
 * 1. Check localStorage
 * 2. Fall back to system preference
 * 3. Default to 'light'
 */
function getInitialTheme() {
  if (typeof window === 'undefined') return 'light';
  const stored = localStorage.getItem('df-theme');
  if (stored === 'dark' || stored === 'light') return stored;
  if (window.matchMedia?.('(prefers-color-scheme: dark)').matches) return 'dark';
  return 'light';
}

/**
 * ThemeProvider — manages dark/light mode across the app.
 *
 * - Toggles the `dark` class on `<html>`
 * - Persists to localStorage
 * - Syncs to DB when a user is authenticated (via PATCH /user/preferences)
 * - Hydrates from the user's DB-stored preference on login
 */
export function ThemeProvider({ children, user }) {
  const [theme, setTheme] = useState(getInitialTheme);

  // ── Apply the `dark` class to <html> whenever theme changes ──
  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
    localStorage.setItem('df-theme', theme);
  }, [theme]);

  // ── Hydrate from user's DB preference on login ──
  useEffect(() => {
    if (user?.theme && (user.theme === 'dark' || user.theme === 'light')) {
      setTheme(user.theme);
      localStorage.setItem('df-theme', user.theme);
    }
  }, [user?.theme]);

  // ── Sync to DB when theme changes (only if authenticated) ──
  const syncThemeToDB = useCallback(async (newTheme) => {
    if (!user) return;
    try {
      await fetch('/user/preferences', {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme: newTheme }),
      });
    } catch (err) {
      console.error('[ThemeContext] Failed to sync theme to DB:', err);
    }
  }, [user]);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next = prev === 'dark' ? 'light' : 'dark';
      syncThemeToDB(next);
      return next;
    });
  }, [syncThemeToDB]);

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export default ThemeContext;
