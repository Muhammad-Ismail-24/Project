import React, { useState, useEffect, useRef, Suspense, lazy } from 'react';
import { Outlet, Link, NavLink, useLocation } from 'react-router-dom';
import { Menu, X, User, ChevronDown } from 'lucide-react';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { ScrollDriveProvider } from '../utils/ScrollDriveContext';

const Background3DShell = lazy(() => import('../components/Background3DShell'));

const NAV_LINKS = [
  { to: '/', label: 'Discover' },
  { to: '/recommend', label: 'Matchmaker' },
  { to: '/calculators', label: 'Calculators' },
  { to: '/chat', label: 'Assistant' },
  { to: '/about', label: 'About' },
];

export default function MainLayout() {
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const location = useLocation();
  const navRef = useRef(null);

  const [assistantName, setAssistantName] = useState('DriveFetch Expert');

  const handleNameBlur = async (e) => {
    const newName = e.target.value.trim() || 'DriveFetch Expert';
    setAssistantName(newName);
    try {
      await fetch('/api/chat/agent', {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_name: newName }),
      });
    } catch (error) {
      console.error('Failed to update agent name:', error);
    }
  };

  // Close mobile menu automatically when clicking a link
  useEffect(() => {
    setIsMobileMenuOpen(false);
  }, [location]);

  useEffect(() => {
    const checkAuth = async () => {
      if (!document.cookie.includes('has_auth=1')) {
        setIsAuthenticated(false);
        setUser(null);
        setIsLoading(false);
        return;
      }
      try {
        const response = await fetch('/auth/me', {
          method: 'GET',
          credentials: 'include', 
          headers: {
            'Content-Type': 'application/json',
          }
        });

        if (response.ok) {
          const userData = await response.json();
          setUser(userData);
          setIsAuthenticated(true);
        } else {
          document.cookie = "has_auth=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
          setIsAuthenticated(false);
          setUser(null);
        }
      } catch (error) {
        console.error("Auth check failed:", error);
        document.cookie = "has_auth=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
        setIsAuthenticated(false);
      } finally {
        setIsLoading(false);
      }
    };

    checkAuth();
  }, []);

  // Blur intensifies on scroll via a class toggle, not React state (Sec 8.1).
  useEffect(() => {
    if (!navRef.current) return;
    const trigger = ScrollTrigger.create({
      trigger: document.body,
      start: 'top -40',
      end: 'max',
      toggleClass: { targets: navRef.current, className: 'nav-scrolled' },
    });
    return () => trigger.kill();
  }, []);

  return (
    <ScrollDriveProvider>
    <div className="relative min-h-screen font-sans selection:bg-accent selection:text-white">

      {/* ── Persistent 3D canvas — mounted once, survives route changes ── */}
      <Suspense fallback={<div className="fixed inset-0 z-0 w-full h-full bg-void" />}>
        <Background3DShell />
      </Suspense>

      {/* ── Floating Navbar ── */}
      <nav ref={navRef} className="glass-thin fixed top-4 left-4 right-4 sm:top-5 sm:left-6 sm:right-6 z-50 transition-[background,backdrop-filter] duration-300">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">

          <div className="flex items-center gap-3">
            <button
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              className="md:hidden p-2 -ml-2 text-text-dim hover:text-text hover:bg-white/5 rounded-full transition-colors"
            >
              {isMobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>

            <Link to="/" className="text-lg sm:text-xl font-display font-black tracking-tighter hover:opacity-70 transition-opacity duration-200 inline-block">
              DriveFetch
            </Link>
          </div>

          {/* Desktop Navigation */}
          <div className="hidden md:flex space-x-7 absolute left-1/2 -translate-x-1/2">
            {NAV_LINKS.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `relative flex flex-col items-center text-sm font-medium transition-all duration-200 after:content-[''] after:absolute after:-bottom-1.5 after:left-0 after:h-[1.5px] after:bg-accent after:transition-all after:duration-200 ${
                    isActive ? 'text-text after:w-full' : 'text-text-dim hover:text-text after:w-0 hover:after:w-full'
                  }`
                }
              >
                <span>{label}</span>
              </NavLink>
            ))}
          </div>

          <div className="flex items-center">
            {isLoading ? (
              <div className="w-8 h-8 rounded-full border-2 border-white/15 border-t-text animate-spin"></div>
            ) : !isAuthenticated || !user ? (
              <button
                onClick={() => window.location.href = '/auth/login'}
                className="btn-primary !py-2 !px-4 text-sm"
              >
                <img src="https://www.svgrepo.com/show/475656/google-color.svg" alt="Google" className="w-4 h-4 bg-white rounded-full" />
                Sign in
              </button>
            ) : (
              <div
                onClick={() => setIsDrawerOpen(true)}
                className="glass-thin flex items-center gap-2 px-3 py-1.5 hover:border-white/20 transition-colors cursor-pointer"
              >
                {user.picture ? (
                  <img src={user.picture} alt={user.name} className="w-7 h-7 sm:w-8 sm:h-8 rounded-full object-cover" />
                ) : (
                  <div className="w-7 h-7 sm:w-8 sm:h-8 rounded-full bg-surface-2 text-text flex items-center justify-center">
                    <User className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                  </div>
                )}
                <span className="font-medium text-sm hidden sm:block text-text">Welcome, {user.name?.split(' ')[0]}</span>
                <ChevronDown className="w-4 h-4 text-text-faint hidden sm:block" />
              </div>
            )}
          </div>
        </div>

        {/* ── Mobile Dropdown Menu ── */}
        {isMobileMenuOpen && (
          <div className="md:hidden glass-thin absolute top-[calc(100%+0.5rem)] left-0 w-full flex flex-col py-4 px-6 space-y-5 z-40">
            {NAV_LINKS.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) => `font-semibold text-lg flex items-center gap-3 transition-colors duration-200 ${isActive ? 'text-text' : 'text-text-dim'}`}
              >
                {({ isActive }) => <><span className={`w-2 h-2 rounded-full transition-colors ${isActive ? 'bg-accent' : 'bg-transparent'}`}></span> {label}</>}
              </NavLink>
            ))}
          </div>
        )}
      </nav>

      {/* Main Content Area */}
      <div className="relative z-10">
        <React.Suspense fallback={<div className="flex h-screen items-center justify-center text-text-dim">Loading...</div>}>
          <Outlet context={{ assistantName, setAssistantName }} />
        </React.Suspense>
      </div>

      {/* Preferences Drawer backdrop scrim */}
      <div
        onClick={() => setIsDrawerOpen(false)}
        className={`fixed inset-0 z-[55] bg-black/50 transition-opacity duration-300 ${isDrawerOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'}`}
      />

      {/* Preferences Drawer */}
      <div
        className={`glass fixed inset-y-0 right-0 z-[60] w-80 sm:w-96 rounded-l-df rounded-r-none shadow-df transform transition-transform duration-300 ease-in-out ${isDrawerOpen ? 'translate-x-0' : 'translate-x-full'}`}
      >
        <div className="p-6">
          <div className="flex justify-between items-center mb-8 pb-4" style={{ borderBottom: '1px solid var(--df-glass-border)' }}>
            <h2 className="text-base font-semibold tracking-tight text-text">Preferences</h2>
            <button onClick={() => setIsDrawerOpen(false)} className="p-1.5 hover:bg-white/5 rounded-xl text-text-dim hover:text-text transition-colors">
              <X className="w-6 h-6" />
            </button>
          </div>

          <div className="space-y-6">
            <Link
              to="/saved"
              onClick={() => setIsDrawerOpen(false)}
              className="glass-thin flex items-center justify-between w-full p-3 text-sm font-medium hover:border-white/20 transition-colors text-text"
            >
              <span>My Saved Cars</span>
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/></svg>
            </Link>
            <div>
              <label className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-faint mb-2 block">Assistant Name</label>
              <input
                type="text"
                value={assistantName}
                onChange={(e) => setAssistantName(e.target.value)}
                onBlur={handleNameBlur}
                placeholder="e.g. GaariGuru Expert..."
                className="field text-sm"
              />
            </div>
            <div>
              <label className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-faint mb-2 block">Daily Commute (km)</label>
              <input type="range" min="0" max="100" className="slider w-full" />
            </div>
            <div>
              <label className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-faint mb-2 block">Tax Status</label>
              <select className="field text-sm">
                <option>Filer</option>
                <option>Non-Filer</option>
              </select>
            </div>
            <button
              onClick={() => {
                document.cookie = "has_auth=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
                setIsAuthenticated(false);
              }}
              className="w-full border border-danger/25 text-danger hover:bg-danger/10 rounded-xl py-2 mt-4 font-medium text-sm transition-colors"
            >
              Sign Out
            </button>
          </div>
        </div>
      </div>
    </div>
    </ScrollDriveProvider>
  );
}