import React, { useState, useEffect } from 'react';
import { Outlet, Link, NavLink, useLocation } from 'react-router-dom';
import { Menu, X, User, ChevronDown } from 'lucide-react';

export default function MainLayout() {
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const location = useLocation();

  const [assistantName, setAssistantName] = useState('GaariGuru Expert');

  const handleNameBlur = async (e) => {
    const newName = e.target.value.trim() || 'GaariGuru Expert';
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
      try {
        // PROXY FIX: Now using relative path
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
          setIsAuthenticated(false);
          setUser(null);
        }
      } catch (error) {
        console.error("Auth check failed:", error);
        setIsAuthenticated(false);
      } finally {
        setIsLoading(false);
      }
    };

    checkAuth();
  }, []);

  return (
    <div className="relative min-h-screen font-sans text-black selection:bg-black selection:text-white">
      
      {/* ── Fixed Navbar ── */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white/20 backdrop-blur-md border-b border-black/10 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-20 flex items-center justify-between">
          
          <div className="flex items-center gap-3">
            <button 
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              className="md:hidden p-2 -ml-2 text-black hover:bg-black/10 rounded-full transition-colors"
            >
              {isMobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>

            <Link to="/" className="text-xl sm:text-2xl font-black tracking-tighter uppercase text-black hover:scale-105 transition-transform duration-200 inline-block">
              GaariGuru
            </Link>
          </div>

          <div className="hidden md:flex space-x-8 absolute left-1/2 -translate-x-1/2">
            <NavLink to="/" className={({ isActive }) => `relative flex flex-col items-center font-black transition-all duration-300 ease-in-out after:content-[''] after:absolute after:-bottom-1 after:left-0 after:h-[2px] after:bg-black after:transition-all after:duration-300 ${isActive ? 'text-black after:w-full' : 'text-black/60 hover:text-black after:w-0 hover:after:w-full'}`}>
              {({ isActive }) => (
                <>
                  <span>Discover</span>
                </>
              )}
            </NavLink>
            <NavLink to="/calculators" className={({ isActive }) => `relative flex flex-col items-center font-black transition-all duration-300 ease-in-out after:content-[''] after:absolute after:-bottom-1 after:left-0 after:h-[2px] after:bg-black after:transition-all after:duration-300 ${isActive ? 'text-black after:w-full' : 'text-black/60 hover:text-black after:w-0 hover:after:w-full'}`}>
              {({ isActive }) => (
                <>
                  <span>Calculators</span>
                </>
              )}
            </NavLink>
            <NavLink to="/chat" className={({ isActive }) => `relative flex flex-col items-center font-black transition-all duration-300 ease-in-out after:content-[''] after:absolute after:-bottom-1 after:left-0 after:h-[2px] after:bg-black after:transition-all after:duration-300 ${isActive ? 'text-black after:w-full' : 'text-black/60 hover:text-black after:w-0 hover:after:w-full'}`}>
              {({ isActive }) => (
                <>
                  <span>Assistant</span>
                </>
              )}
            </NavLink>
            <NavLink to="/about" className={({ isActive }) => `relative flex flex-col items-center font-black transition-all duration-300 ease-in-out after:content-[''] after:absolute after:-bottom-1 after:left-0 after:h-[2px] after:bg-black after:transition-all after:duration-300 ${isActive ? 'text-black after:w-full' : 'text-black/60 hover:text-black after:w-0 hover:after:w-full'}`}>
              {({ isActive }) => (
                <>
                  <span>About</span>
                </>
              )}
            </NavLink>
          </div>

          <div className="flex items-center">
            {isLoading ? (
              <div className="w-8 h-8 rounded-full border-2 border-black/30 border-t-black animate-spin"></div>
            ) : !isAuthenticated || !user ? (
              <button 
                // PROXY FIX: Now using relative path for redirect
                onClick={() => window.location.href = '/auth/login'}
                className="flex items-center px-4 py-2 bg-[#a3a3a3] border border-black rounded-full hover:bg-black hover:text-white transition-colors font-bold text-sm whitespace-nowrap shadow-[2px_2px_0px_rgba(0,0,0,1)] active:translate-y-0.5 active:translate-x-0.5 active:shadow-none"
              >
                <img src="https://www.svgrepo.com/show/475656/google-color.svg" alt="Google" className="w-4 h-4 mr-2 bg-white rounded-full" />
                Sign in
              </button>
            ) : (
              <div 
                onClick={() => setIsDrawerOpen(true)}
                className="flex items-center gap-2 bg-zinc-800/50 border border-zinc-700 px-3 py-1.5 rounded-full hover:bg-zinc-800 transition-colors cursor-pointer shadow-sm"
              >
                {user.picture ? (
                  <img src={user.picture} alt={user.name} className="w-7 h-7 sm:w-8 sm:h-8 rounded-full object-cover" />
                ) : (
                  <div className="w-7 h-7 sm:w-8 sm:h-8 rounded-full bg-black text-white flex items-center justify-center">
                    <User className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                  </div>
                )}
                <span className="font-bold text-sm hidden sm:block text-white">Welcome, {user.name?.split(' ')[0]}</span>
                <ChevronDown className="w-4 h-4 text-zinc-400 hidden sm:block" />
              </div>
            )}
          </div>
        </div>

        {/* ── Mobile Dropdown Menu ── */}
        {isMobileMenuOpen && (
          <div className="md:hidden absolute top-20 left-0 w-full bg-white/60 backdrop-blur-xl border-b border-black/10 shadow-2xl flex flex-col py-4 px-6 space-y-6 z-40">
            <NavLink to="/" className={({ isActive }) => `font-black text-2xl flex items-center gap-3 transition-colors duration-200 ${isActive ? 'text-black' : 'text-black/60'}`}>
              {({ isActive }) => <><span className={`w-2 h-2 rounded-full transition-colors ${isActive ? 'bg-black' : 'bg-transparent'}`}></span> Discover</>}
            </NavLink>
            <NavLink to="/calculators" className={({ isActive }) => `font-black text-2xl flex items-center gap-3 transition-colors duration-200 ${isActive ? 'text-black' : 'text-black/60'}`}>
              {({ isActive }) => <><span className={`w-2 h-2 rounded-full transition-colors ${isActive ? 'bg-black' : 'bg-transparent'}`}></span> Calculators</>}
            </NavLink>
            <NavLink to="/chat" className={({ isActive }) => `font-black text-2xl flex items-center gap-3 transition-colors duration-200 ${isActive ? 'text-black' : 'text-black/60'}`}>
              {({ isActive }) => <><span className={`w-2 h-2 rounded-full transition-colors ${isActive ? 'bg-black' : 'bg-transparent'}`}></span> Assistant</>}
            </NavLink>
            <NavLink to="/about" className={({ isActive }) => `font-black text-2xl flex items-center gap-3 transition-colors duration-200 ${isActive ? 'text-black' : 'text-black/60'}`}>
              {({ isActive }) => <><span className={`w-2 h-2 rounded-full transition-colors ${isActive ? 'bg-black' : 'bg-transparent'}`}></span> About</>}
            </NavLink>
          </div>
        )}
      </nav>

      {/* Main Content Area */}
      <main className="relative z-10 pt-20">
        <Outlet context={{ assistantName, setAssistantName }} />
      </main>

      {/* Preferences Drawer */}
      <div 
        className={`fixed inset-y-0 right-0 z-[60] w-80 sm:w-96 bg-zinc-900/90 backdrop-blur-xl shadow-2xl border-l border-white/10 transform transition-transform duration-300 ease-in-out ${isDrawerOpen ? 'translate-x-0' : 'translate-x-full'}`}
      >
        <div className="p-6">
          <div className="flex justify-between items-center mb-8 border-b border-zinc-700/50 pb-4">
            <h2 className="text-xl font-black tracking-tight text-white">Preferences</h2>
            <button onClick={() => setIsDrawerOpen(false)} className="p-2 hover:bg-white/10 rounded-full text-zinc-400 hover:text-white transition-colors">
              <X className="w-6 h-6" />
            </button>
          </div>
          
          <div className="space-y-6">
            <Link 
              to="/saved" 
              onClick={() => setIsDrawerOpen(false)}
              className="flex items-center justify-between w-full bg-zinc-800/50 border border-zinc-700 rounded-lg p-3 text-sm font-bold hover:bg-zinc-800 transition-colors text-white shadow-sm"
            >
              <span>My Saved Cars</span>
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/></svg>
            </Link>
            <div>
              <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 mb-2 block">Assistant Name</label>
              <input 
                type="text" 
                value={assistantName}
                onChange={(e) => setAssistantName(e.target.value)}
                onBlur={handleNameBlur}
                placeholder="e.g. GaariGuru Expert..."
                className="w-full bg-zinc-800/50 border border-zinc-700 rounded-lg p-2.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all text-white placeholder-zinc-500"
              />
            </div>
            <div>
              <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 mb-2 block">Daily Commute (km)</label>
              <input type="range" min="0" max="100" className="w-full accent-blue-500" />
            </div>
            <div>
              <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 mb-2 block">Tax Status</label>
              <select className="w-full bg-zinc-800/50 border border-zinc-700 rounded-lg p-2.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all text-white">
                <option>Filer</option>
                <option>Non-Filer</option>
              </select>
            </div>
            <button 
              onClick={() => setIsAuthenticated(false)}
              className="w-full border border-red-500/20 text-red-400 hover:bg-red-500/10 rounded-lg py-2 mt-4 font-bold transition-colors"
            >
              Sign Out
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}