import React, { useState, useEffect } from 'react';
import { Outlet, Link, NavLink, useLocation } from 'react-router-dom';
import { Menu, X, Bookmark, Settings, LogOut } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { ThemeProvider, useTheme } from '../contexts/ThemeContext';

const NAV_LINKS = [
  { to: '/', label: 'DISCOVER' },
  { to: '/recommend', label: 'MATCHMAKER' },
  { to: '/chat', label: 'CHAT' },
  { to: '/calculators', label: 'CALCULATORS' },
  { to: '/about', label: 'ABOUT' },
];

export default function MainLayout() {
  return <MainLayoutInner />;
}

function MainLayoutInner() {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isPreferencesOpen, setIsPreferencesOpen] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [assistantName, setAssistantName] = useState('DriveFetch AI');
  const location = useLocation();

  // Close menus on route change
  useEffect(() => {
    setIsMobileMenuOpen(false);
    setIsPreferencesOpen(false);
  }, [location]);

  // Lock body scroll when preferences is open
  useEffect(() => {
    if (isPreferencesOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isPreferencesOpen]);

  // Auth check
  useEffect(() => {
    if (user?.bot_name) {
      setAssistantName(user.bot_name);
    }
  }, [user?.bot_name]);

  useEffect(() => {
    const checkAuth = async () => {
      try {
        const response = await fetch('/auth/me', {
          method: 'GET',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
        });
        if (response.ok) {
          const userData = await response.json();
          setUser(userData);
          setIsAuthenticated(true);
          if (userData.bot_name) {
            setAssistantName(userData.bot_name);
          } else {
            // Fetch from chat sessions history (working logic from ChatPage)
            try {
              const sessRes = await fetch('/api/chat/sessions', {
                method: 'GET',
                credentials: 'include',
              });
              if (sessRes.ok) {
                const sessData = await sessRes.json();
                if (!sessData.is_guest && sessData.sessions && sessData.sessions.length > 0) {
                  const histRes = await fetch(`/api/chat/history/${sessData.sessions[0].session_id}`, {
                    method: 'GET',
                    credentials: 'include',
                  });
                  if (histRes.ok) {
                    const histData = await histRes.json();
                    if (histData.agent_name) {
                      setAssistantName(histData.agent_name);
                      setUser(prev => ({ ...prev, bot_name: histData.agent_name }));
                    }
                  }
                }
              }
            } catch (chatErr) {
              console.error("Chat preferences fetch failed:", chatErr);
            }
          }
        } else {
          setIsAuthenticated(false);
          setUser(null);
        }
      } catch (error) {
        console.error("Auth check failed:", error);
        setIsAuthenticated(false);
        setUser(null);
      } finally {
        setIsLoading(false);
      }
    };
    checkAuth();
  }, [location]);

  const handleLogout = async () => {
    try {
      await fetch('/auth/logout', { method: 'GET', credentials: 'include' });
    } catch (error) {
      console.error("Logout request failed", error);
    } finally {
      localStorage.clear();
      sessionStorage.clear();
      setUser(null);
      setIsAuthenticated(false);
      document.cookie = "has_auth=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
      window.location.replace('/');
    }
  };

  return (
    <ThemeProvider user={user}>
    <div className="relative min-h-screen flex flex-col bg-white text-black dark:bg-zinc-950 dark:text-zinc-50 font-body selection:bg-df-black selection:text-df-white dark:selection:bg-white dark:selection:text-black transition-colors duration-200">

      {/* ═══ HEADER ═══ */}
      <header className="fixed top-0 left-0 right-0 z-50 bg-white dark:bg-black border-b-2 border-black dark:border-white transition-colors duration-200">
        <div className="w-full px-5 sm:px-8 lg:px-12 h-16 sm:h-[72px] flex items-center justify-between">
          
          {/* Left side: Hamburger (Mobile) + Logo */}
          <div className="flex items-center gap-3">
            {/* Mobile Hamburger */}
            <button
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              className="md:hidden p-2 border-brutal-thin hover:bg-df-black hover:text-df-white dark:hover:bg-white dark:hover:text-black transition-none"
              aria-label="Toggle menu"
            >
              {isMobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>

            {/* Logo */}
            <Link
              to="/"
              className="font-mono text-lg sm:text-xl font-bold tracking-tight text-black dark:text-white hover:text-df-red transition-none select-none whitespace-nowrap"
            >
              [ DRIVEFETCH ]
            </Link>
          </div>

          {/* Desktop Nav */}
          <nav className="hidden md:flex items-center gap-0">
            {NAV_LINKS.map((link, i) => (
              <React.Fragment key={link.to}>
                {i > 0 && (
                  <span className="text-df-black/25 dark:text-white/25 font-light select-none mx-1">|</span>
                )}
                <NavLink
                  to={link.to}
                  end={link.to === '/'}
                  className={({ isActive }) =>
                    `px-3 py-1.5 font-mono text-xs font-bold tracking-[0.08em] transition-none ` +
                    (isActive
                      ? 'bg-black text-white dark:bg-white dark:text-black'
                      : 'text-black dark:text-white hover:bg-black hover:text-white dark:hover:bg-white dark:hover:text-black')
                  }
                >
                  {link.label}
                </NavLink>
              </React.Fragment>
            ))}
          </nav>

          {/* Right side: Theme Toggle + Auth */}
          <div className="flex items-center gap-3">
            {/* Theme Toggle (Hidden on mobile) */}
            <ThemeToggleButton className="hidden md:block" />

            {/* Auth Button */}
            {isLoading ? (
              <div className="w-7 h-7 border-2 border-df-black/30 dark:border-white/30 border-t-df-black dark:border-t-white animate-spin" />
            ) : !isAuthenticated || !user ? (
              <button
                onClick={() => window.location.href = '/auth/login'}
                className="hidden sm:flex items-center px-4 py-2 border-brutal text-df-black dark:text-zinc-100 bg-df-white dark:bg-zinc-900 font-mono text-xs font-bold tracking-wide shadow-brutal-sm dark:shadow-[3px_3px_0px_0px_#ffffff] hover:bg-df-black hover:text-df-white dark:hover:bg-white dark:hover:text-black hover:shadow-none transition-none whitespace-nowrap"
              >
                Google Sign-In
              </button>
            ) : (
              <button
                onClick={() => setIsPreferencesOpen(true)}
                className="flex items-center gap-2 px-3 py-1.5 border-brutal bg-df-black dark:bg-white text-df-white dark:text-black font-mono text-xs font-bold tracking-wide hover:shadow-[3px_3px_0px_#E5202E] transition-none"
              >
                {user.picture ? (
                  <img src={user.picture} alt={user.name} className="w-6 h-6 object-cover border border-df-white/30 dark:border-black/30" />
                ) : (
                  <span className="w-6 h-6 bg-df-white dark:bg-black text-df-black dark:text-white flex items-center justify-center text-[10px] font-bold">
                    {user.name?.charAt(0) || 'U'}
                  </span>
                )}
                <span className="hidden sm:block uppercase">{user.name?.split(' ')[0]}</span>
              </button>
            )}
          </div>
        </div>

        {/* ── Mobile Menu Dropdown ── */}
        {isMobileMenuOpen && (
          <div className="md:hidden bg-df-white dark:bg-zinc-900 border-t-2 border-df-black dark:border-white">
            {NAV_LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.to === '/'}
                className={({ isActive }) =>
                  `block px-6 py-4 font-mono text-sm font-bold tracking-[0.08em] border-b border-df-black/10 dark:border-white/10 transition-none ` +
                  (isActive
                    ? 'bg-black text-white dark:bg-white dark:text-black'
                    : 'text-black dark:text-white hover:bg-black hover:text-white dark:hover:bg-white dark:hover:text-black')
                }
              >
                {link.label}
              </NavLink>
            ))}
            {/* Mobile Sign-In */}
            {!isAuthenticated && (
              <button
                onClick={() => window.location.href = '/auth/login'}
                className="w-full px-6 py-4 text-left font-mono text-sm font-bold tracking-wide text-df-black dark:text-zinc-100 border-b border-df-black/10 dark:border-white/10 hover:bg-df-black hover:text-df-white dark:hover:bg-white dark:hover:text-black transition-none"
              >
                GOOGLE SIGN-IN →
              </button>
            )}
            {/* Mobile Theme Toggle */}
            <div className="px-6 py-4 border-b border-df-black/10 dark:border-white/10 flex items-center justify-between">
              <span className="font-mono text-sm font-bold tracking-[0.08em] text-df-black dark:text-zinc-100">THEME</span>
              <ThemeToggleButton />
            </div>
          </div>
        )}
      </header>

      {/* ═══ PREFERENCES SLIDE-OVER ═══ */}
      <AnimatePresence>
        {isPreferencesOpen && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setIsPreferencesOpen(false)}
              className="fixed inset-0 z-[60] bg-df-black/20 dark:bg-black/40 backdrop-blur-sm"
            />
            {/* Slide-over Panel */}
            <motion.div
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 25, stiffness: 200 }}
              className="fixed top-0 right-0 bottom-0 z-[70] w-full max-w-sm bg-df-white dark:bg-zinc-900 bg-[linear-gradient(to_right,#e5e7eb_1px,transparent_1px),linear-gradient(to_bottom,#e5e7eb_1px,transparent_1px)] dark:bg-[linear-gradient(to_right,#3f3f46_1px,transparent_1px),linear-gradient(to_bottom,#3f3f46_1px,transparent_1px)] bg-[size:20px_20px] border-l-4 border-df-black dark:border-white shadow-[-10px_0_0_rgba(0,0,0,0.1)] dark:shadow-[-10px_0_0_rgba(255,255,255,0.05)] flex flex-col"
            >
              <div className="flex items-center justify-between p-6 border-b-4 border-df-black dark:border-white flex-shrink-0">
                <h2 className="text-4xl md:text-5xl font-black uppercase tracking-tighter text-df-black dark:text-zinc-100 mt-1">ACCOUNT</h2>
                <button
                  onClick={() => setIsPreferencesOpen(false)}
                  aria-label="Close preferences panel"
                  className="p-2 border-2 border-df-black dark:border-white hover:bg-df-black hover:text-df-white dark:hover:bg-white dark:hover:text-black transition-none"
                >
                  <X className="w-6 h-6" strokeWidth={2.5} />
                </button>
              </div>

              <div className="p-6 flex-1 flex flex-col gap-6 overflow-y-auto">
                {user && (
                  <div className="border-b-2 border-df-black/10 dark:border-white/10 pb-6">
                    <p className="font-mono text-[10px] font-bold text-df-black/40 dark:text-white/40 tracking-[0.14em] uppercase mb-1">
                      ACTIVE USER
                    </p>
                    <p className="font-body text-lg font-bold text-df-black dark:text-zinc-100">{user.name}</p>
                    <p className="font-mono text-xs text-df-black/60 dark:text-white/60">{user.email}</p>
                  </div>
                )}

                <Link
                  to="/saved"
                  onClick={() => setIsPreferencesOpen(false)}
                  className="bg-white dark:bg-black text-black dark:text-white border-2 border-black dark:border-white font-bold uppercase py-3 px-4 w-full flex items-center justify-center gap-2 transition-all hover:bg-red-600 hover:text-white hover:-translate-y-0.5 hover:-translate-x-0.5 hover:shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:hover:shadow-[4px_4px_0px_0px_rgba(255,255,255,1)]"
                >
                  <Bookmark className="w-5 h-5" strokeWidth={2} />
                  Saved Vehicles
                </Link>
                
                {/* ── Chatbot Name Setting ── */}
                <div className="flex flex-col gap-2 mt-2">
                  <label className="font-mono text-[10px] font-bold text-df-black/40 dark:text-white/40 tracking-[0.14em] uppercase">
                    [ AI ASSISTANT NAME ]
                  </label>
                  <div className="flex">
                    <input 
                      type="text" 
                      placeholder="e.g. JARVIS"
                      value={assistantName}
                      onChange={(e) => setAssistantName(e.target.value)}
                      className="flex-1 bg-df-white dark:bg-black border-2 border-df-black dark:border-white px-3 py-2 font-mono text-xs font-bold text-df-black dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-df-red"
                    />
                    <button 
                      onClick={async () => {
                        try {
                          await fetch('/user/preferences', { 
                            method: 'PATCH', 
                            credentials: 'include',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ bot_name: assistantName }) 
                          });
                        } catch(e) { console.error("Failed to save bot name"); }
                      }}
                      className="bg-df-red text-df-white border-2 border-l-0 border-df-black dark:border-white px-4 font-mono text-xs font-bold hover:bg-df-black dark:hover:bg-white dark:hover:text-black transition-colors"
                    >
                      [ SAVE ]
                    </button>
                  </div>
                </div>

                {/* Theme Toggler removed — now lives in the header via ThemeToggleButton */}

              </div>

              <div className="p-6 border-t-2 border-df-black dark:border-white mt-auto bg-df-grey dark:bg-black flex-shrink-0">
                <button
                  onClick={handleLogout}
                  className="w-full flex items-center justify-center gap-2 p-4 bg-df-white dark:bg-zinc-900 text-df-black dark:text-zinc-100 border-2 border-df-black dark:border-white hover:bg-df-red hover:text-df-white transition-none font-mono font-bold tracking-wide uppercase"
                >
                  <LogOut className="w-4 h-4" strokeWidth={2} />
                  Terminate Session
                </button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* ═══ MAIN CONTENT ═══ */}
      <main className="relative z-10 pt-16 sm:pt-[72px] flex-grow flex flex-col bg-transparent">
        <Outlet context={{ user, isAuthenticated, isLoading, assistantName, setAssistantName }} />
      </main>

      {/* ═══ FOOTER ═══ */}
      {location.pathname !== '/chat' && <BrutalistFooter />}
    </div>
    </ThemeProvider>
  );
}

function BrutalistFooter() {
  return (
    <footer className="relative z-[50] border-t-2 border-df-black dark:border-white bg-df-white dark:bg-zinc-900 mt-auto transition-colors duration-200">
      <div className="w-full max-w-[1400px] mx-auto px-5 sm:px-8 lg:px-12 py-6 sm:py-8">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-5 md:gap-4">
          <div className="font-mono text-[10px] sm:text-xs font-bold tracking-[0.06em] text-df-black/50 dark:text-white/50">
            [ DRIVEFETCH // ALL RIGHTS RESERVED ]
          </div>
          <nav className="flex flex-wrap items-center gap-x-1 gap-y-2">
            {[
              { label: 'PRIVACY POLICY', to: '/privacy' },
              { label: 'TERMS', href: '#' },
              { label: 'GITHUB', href: 'https://github.com' },
              { label: 'CONTACT', href: '#' },
            ].map((link, i, arr) => (
              <span key={link.label} className="flex items-center">
                {link.to ? (
                  <Link
                    to={link.to}
                    className="font-mono text-[10px] sm:text-xs font-bold tracking-[0.06em] text-df-black dark:text-zinc-100 bg-transparent hover:bg-df-black hover:text-df-white dark:hover:bg-white dark:hover:text-black px-2 py-1 transition-none"
                  >
                    {link.label}
                  </Link>
                ) : (
                  <a
                    href={link.href}
                    target={link.href.startsWith('http') ? '_blank' : undefined}
                    rel={link.href.startsWith('http') ? 'noopener noreferrer' : undefined}
                    className="font-mono text-[10px] sm:text-xs font-bold tracking-[0.06em] text-df-black dark:text-zinc-100 bg-transparent hover:bg-df-black hover:text-df-white dark:hover:bg-white dark:hover:text-black px-2 py-1 transition-none"
                  >
                    {link.label}
                  </a>
                )}
                {i < arr.length - 1 && (
                  <span className="text-df-black/15 dark:text-white/15 font-light mx-0.5 select-none">|</span>
                )}
              </span>
            ))}
          </nav>
          <div className="font-mono text-[10px] sm:text-xs tracking-[0.06em] text-df-black/25 dark:text-white/25">
            BUILD_VER: 2.0.4_BRUTALIST
          </div>
        </div>
      </div>
    </footer>
  );
}

/**
 * ThemeToggleButton — Minimalist brutalist toggle for the header.
 * Displays [☾ DARK] or [☀ LIGHT] depending on the current theme.
 */
function ThemeToggleButton({ className = '' }) {
  const { theme, toggleTheme } = useTheme();
  return (
    <button
      onClick={toggleTheme}
      aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
      className={`border-2 border-black dark:border-white px-2 py-1 font-mono text-xs font-bold uppercase tracking-[0.04em] hover:-translate-y-0.5 hover:shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] dark:hover:shadow-[2px_2px_0px_0px_rgba(255,255,255,1)] transition-all ${className}`}
    >
      {theme === 'dark' ? '[ ☀ LIGHT ]' : '[ ☾ DARK ]'}
    </button>
  );
}