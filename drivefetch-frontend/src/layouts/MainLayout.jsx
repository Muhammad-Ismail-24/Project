import React, { useState, useEffect } from 'react';
import { Outlet, Link, NavLink, useLocation } from 'react-router-dom';
import { Menu, X } from 'lucide-react';

const NAV_LINKS = [
  { to: '/', label: 'DISCOVER' },
  { to: '/recommend', label: 'MATCHMAKER' },
  { to: '/chat', label: 'CHAT' },
  { to: '/calculators', label: 'CALCULATORS' },
  { to: '/about', label: 'ABOUT' },
];

export default function MainLayout() {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const location = useLocation();

  // Close mobile menu on route change
  useEffect(() => {
    setIsMobileMenuOpen(false);
  }, [location]);

  // Auth check
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
          headers: { 'Content-Type': 'application/json' },
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
                onClick={() => window.location.href = '/saved'}
                className="flex items-center gap-2 px-3 py-1.5 border-brutal bg-df-black text-df-white font-mono text-xs font-bold tracking-wide"
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

      {/* ═══ MAIN CONTENT ═══ */}
      <main className="relative z-10 pt-16 sm:pt-[72px] flex-grow flex flex-col">
        <Outlet />
      </main>

      {/* ═══ FOOTER ═══ */}
      <BrutalistFooter />
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