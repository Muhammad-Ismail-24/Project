import React, { useState, useEffect } from 'react';
import { Outlet, Link, NavLink, useLocation } from 'react-router-dom';
import { Menu, X, Bookmark, Settings, LogOut } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const NAV_LINKS = [
  { to: '/', label: 'DISCOVER' },
  { to: '/recommend', label: 'MATCHMAKER' },
  { to: '/chat', label: 'CHAT' },
  { to: '/calculators', label: 'CALCULATORS' },
  { to: '/about', label: 'ABOUT' },
];

export default function MainLayout() {
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
            try {
              const prefRes = await fetch('/api/user/preferences', {
                method: 'GET',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
              });
              if (prefRes.ok) {
                const prefData = await prefRes.json();
                if (prefData.bot_name) {
                  setAssistantName(prefData.bot_name);
                  setUser(prev => ({ ...prev, bot_name: prefData.bot_name }));
                }
              }
            } catch (prefError) {
              console.error("Preferences check failed:", prefError);
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
    <div className="relative min-h-screen flex flex-col bg-df-white text-df-black font-body selection:bg-df-black selection:text-df-white">

      {/* ═══ HEADER ═══ */}
      <header className="fixed top-0 left-0 right-0 z-50 bg-df-white border-b-[3px] border-df-black">
        <div className="w-full px-5 sm:px-8 lg:px-12 h-16 sm:h-[72px] flex items-center justify-between">

          {/* Logo */}
          <Link
            to="/"
            className="font-mono text-lg sm:text-xl font-bold tracking-tight text-df-black hover:text-df-red transition-none select-none whitespace-nowrap"
          >
            [ DRIVEFETCH ]
          </Link>

          {/* Desktop Nav */}
          <nav className="hidden md:flex items-center gap-0">
            {NAV_LINKS.map((link, i) => (
              <React.Fragment key={link.to}>
                {i > 0 && (
                  <span className="text-df-black/25 font-light select-none mx-1">|</span>
                )}
                <NavLink
                  to={link.to}
                  end={link.to === '/'}
                  className={({ isActive }) =>
                    `px-3 py-1.5 font-mono text-xs font-bold tracking-[0.08em] transition-none ` +
                    (isActive
                      ? 'bg-df-black text-df-white'
                      : 'text-df-black hover:bg-df-black hover:text-df-white')
                  }
                >
                  {link.label}
                </NavLink>
              </React.Fragment>
            ))}
          </nav>

          {/* Right side: Auth + Mobile toggle */}
          <div className="flex items-center gap-3">
            {/* Auth Button */}
            {isLoading ? (
              <div className="w-7 h-7 border-2 border-df-black/30 border-t-df-black animate-spin" />
            ) : !isAuthenticated || !user ? (
              <button
                onClick={() => window.location.href = '/auth/login'}
                className="hidden sm:flex items-center px-4 py-2 border-brutal text-df-black bg-df-white font-mono text-xs font-bold tracking-wide shadow-brutal-sm hover:bg-df-black hover:text-df-white hover:shadow-none transition-none whitespace-nowrap"
              >
                Google Sign-In
              </button>
            ) : (
              <button
                onClick={() => setIsPreferencesOpen(true)}
                className="flex items-center gap-2 px-3 py-1.5 border-brutal bg-df-black text-df-white font-mono text-xs font-bold tracking-wide hover:shadow-[3px_3px_0px_#E5202E] transition-none"
              >
                {user.picture ? (
                  <img src={user.picture} alt={user.name} className="w-6 h-6 object-cover border border-df-white/30" />
                ) : (
                  <span className="w-6 h-6 bg-df-white text-df-black flex items-center justify-center text-[10px] font-bold">
                    {user.name?.charAt(0) || 'U'}
                  </span>
                )}
                <span className="hidden sm:block uppercase">{user.name?.split(' ')[0]}</span>
              </button>
            )}

            {/* Mobile Hamburger */}
            <button
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              className="md:hidden p-2 border-brutal-thin hover:bg-df-black hover:text-df-white transition-none"
              aria-label="Toggle menu"
            >
              {isMobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>

        {/* ── Mobile Menu Dropdown ── */}
        {isMobileMenuOpen && (
          <div className="md:hidden bg-df-white border-t-2 border-df-black">
            {NAV_LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.to === '/'}
                className={({ isActive }) =>
                  `block px-6 py-4 font-mono text-sm font-bold tracking-[0.08em] border-b border-df-black/10 transition-none ` +
                  (isActive
                    ? 'bg-df-black text-df-white'
                    : 'text-df-black hover:bg-df-black hover:text-df-white')
                }
              >
                {link.label}
              </NavLink>
            ))}
            {/* Mobile Sign-In */}
            {!isAuthenticated && (
              <button
                onClick={() => window.location.href = '/auth/login'}
                className="w-full px-6 py-4 text-left font-mono text-sm font-bold tracking-wide text-df-black border-b border-df-black/10 hover:bg-df-black hover:text-df-white transition-none"
              >
                GOOGLE SIGN-IN →
              </button>
            )}
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
              className="fixed inset-0 z-[60] bg-df-black/20 backdrop-blur-sm"
            />
            {/* Slide-over Panel */}
            <motion.div
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 25, stiffness: 200 }}
              className="fixed top-0 right-0 bottom-0 z-[70] w-full max-w-sm bg-df-white bg-[linear-gradient(to_right,#e5e7eb_1px,transparent_1px),linear-gradient(to_bottom,#e5e7eb_1px,transparent_1px)] bg-[size:20px_20px] border-l-4 border-df-black shadow-[-10px_0_0_rgba(0,0,0,0.1)] flex flex-col"
            >
              <div className="flex items-center justify-between p-6 border-b-4 border-df-black flex-shrink-0">
                <h2 className="text-4xl md:text-5xl font-black uppercase tracking-tighter text-df-black mt-1">ACCOUNT</h2>
                <button
                  onClick={() => setIsPreferencesOpen(false)}
                  className="p-2 border-2 border-df-black hover:bg-df-black hover:text-df-white transition-none"
                >
                  <X className="w-6 h-6" strokeWidth={2.5} />
                </button>
              </div>

              <div className="p-6 flex-1 flex flex-col gap-6 overflow-y-auto">
                {user && (
                  <div className="border-b-2 border-df-black/10 pb-6">
                    <p className="font-mono text-[10px] font-bold text-df-black/40 tracking-[0.14em] uppercase mb-1">
                      ACTIVE USER
                    </p>
                    <p className="font-body text-lg font-bold text-df-black">{user.name}</p>
                    <p className="font-mono text-xs text-df-black/60">{user.email}</p>
                  </div>
                )}

                <Link
                  to="/saved"
                  onClick={() => setIsPreferencesOpen(false)}
                  className="flex items-center gap-3 p-4 bg-df-black text-df-white border-2 border-df-black shadow-[4px_4px_0px_#E5202E] hover:-translate-y-1 hover:-translate-x-1 hover:shadow-[4px_4px_0px_0px_rgba(220,38,38,1)] transition-all font-mono font-bold tracking-wide uppercase"
                >
                  <Bookmark className="w-5 h-5" strokeWidth={2} />
                  Saved Vehicles
                </Link>
                
                {/* ── Chatbot Name Setting ── */}
                <div className="flex flex-col gap-2 mt-2">
                  <label className="font-mono text-[10px] font-bold text-df-black/40 tracking-[0.14em] uppercase">
                    [ AI ASSISTANT NAME ]
                  </label>
                  <div className="flex">
                    <input 
                      type="text" 
                      placeholder="e.g. JARVIS"
                      value={assistantName}
                      onChange={(e) => setAssistantName(e.target.value)}
                      className="flex-1 bg-df-white border-2 border-df-black px-3 py-2 font-mono text-xs font-bold text-df-black focus:outline-none focus:ring-2 focus:ring-df-red"
                    />
                    <button 
                      onClick={async () => {
                        try {
                          await fetch('/api/user/preferences', { 
                            method: 'PATCH', 
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ bot_name: assistantName }) 
                          });
                        } catch(e) { console.error("Failed to save bot name"); }
                      }}
                      className="bg-df-red text-df-white border-2 border-l-0 border-df-black px-4 font-mono text-xs font-bold hover:bg-df-black transition-colors"
                    >
                      [ SAVE ]
                    </button>
                  </div>
                </div>

                {/* ── Theme Toggler ── */}
                <div className="flex flex-col gap-2 mt-2">
                  <label className="font-mono text-[10px] font-bold text-df-black/40 tracking-[0.14em] uppercase">
                    [ INTERFACE THEME ]
                  </label>
                  <div className="flex border-2 border-df-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
                    <button className="flex-1 bg-df-black text-df-white py-2 font-mono text-xs font-bold transition-none">
                      [ LIGHT ]
                    </button>
                    <button className="flex-1 bg-df-white text-df-black py-2 font-mono text-xs font-bold border-l-2 border-df-black hover:bg-df-grey transition-none">
                      [ DARK ]
                    </button>
                  </div>
                </div>

              </div>

              <div className="p-6 border-t-2 border-df-black mt-auto bg-df-grey flex-shrink-0">
                <button
                  onClick={handleLogout}
                  className="w-full flex items-center justify-center gap-2 p-4 bg-df-white text-df-black border-2 border-df-black hover:bg-df-red hover:text-df-white transition-none font-mono font-bold tracking-wide uppercase"
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
      <main className="relative z-10 pt-16 sm:pt-[72px] flex-grow flex flex-col">
        <Outlet context={{ user, isAuthenticated, isLoading, assistantName, setAssistantName }} />
      </main>

      {/* ═══ FOOTER ═══ */}
      {location.pathname !== '/chat' && <BrutalistFooter />}
    </div>
  );
}

function BrutalistFooter() {
  return (
    <footer className="relative z-[50] border-t-2 border-df-black bg-df-white mt-auto">
      <div className="w-full max-w-[1400px] mx-auto px-5 sm:px-8 lg:px-12 py-6 sm:py-8">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-5 md:gap-4">
          <div className="font-mono text-[10px] sm:text-xs font-bold tracking-[0.06em] text-df-black/50">
            [ DRIVEFETCH // ALL RIGHTS RESERVED ]
          </div>
          <nav className="flex flex-wrap items-center gap-x-1 gap-y-2">
            {[
              { label: 'PRIVACY POLICY', href: '#' },
              { label: 'TERMS', href: '#' },
              { label: 'GITHUB', href: 'https://github.com' },
              { label: 'CONTACT', href: '#' },
            ].map((link, i, arr) => (
              <span key={link.label} className="flex items-center">
                <a
                  href={link.href}
                  target={link.href.startsWith('http') ? '_blank' : undefined}
                  rel={link.href.startsWith('http') ? 'noopener noreferrer' : undefined}
                  className="font-mono text-[10px] sm:text-xs font-bold tracking-[0.06em] text-df-black bg-transparent hover:bg-df-black hover:text-df-white px-2 py-1 transition-none"
                >
                  {link.label}
                </a>
                {i < arr.length - 1 && (
                  <span className="text-df-black/15 font-light mx-0.5 select-none">|</span>
                )}
              </span>
            ))}
          </nav>
          <div className="font-mono text-[10px] sm:text-xs tracking-[0.06em] text-df-black/25">
            BUILD_VER: 2.0.4_BRUTALIST
          </div>
        </div>
      </div>
    </footer>
  );
}