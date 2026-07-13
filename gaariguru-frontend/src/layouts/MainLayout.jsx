import React, { useState, useEffect } from 'react';
import { Outlet, Link } from 'react-router-dom';
import { Menu, X, User } from 'lucide-react';

export default function MainLayout() {
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const checkAuth = async () => {
      try {
        const response = await fetch('https://carfinder-project-backend.onrender.com/auth/me', {
          method: 'GET',
          // CRITICAL: Send secure session cookies to the backend
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
      
      {/* Glassmorphism Top Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white/70 backdrop-blur-xl border-b border-white/40 shadow-sm">
        <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
          
          {/* Logo */}
          <Link to="/" className="text-2xl font-black tracking-tighter uppercase">
            GaariGuru
          </Link>

          {/* Center Links */}
          <div className="hidden md:flex space-x-8">
            <Link to="/" className="font-semibold text-black hover:text-neutral-600 transition-colors">Discover</Link>
            <Link to="/calculators" className="font-semibold text-neutral-500 hover:text-black transition-colors">Calculators</Link>
            <Link to="/chat" className="font-semibold text-neutral-500 hover:text-black transition-colors">Assistant</Link>
            <Link to="/about" className="font-semibold text-neutral-500 hover:text-black transition-colors">About</Link>
          </div>

          {/* Auth Section */}
          <div className="flex items-center">
            {isLoading ? (
              <div className="w-8 h-8 rounded-full border-2 border-neutral-300 border-t-black animate-spin"></div>
            ) : !isAuthenticated || !user ? (
              <button 
                onClick={() => window.location.href = 'https://carfinder-project-backend.onrender.com/auth/login'}
                className="flex items-center px-4 py-2 bg-white border border-neutral-200 rounded-full shadow-sm hover:shadow-md transition-all font-semibold text-sm"
              >
                <img src="https://www.svgrepo.com/show/475656/google-color.svg" alt="Google" className="w-4 h-4 mr-2" />
                Sign in
              </button>
            ) : (
              <button 
                onClick={() => setIsDrawerOpen(true)}
                className="flex items-center gap-2 hover:bg-neutral-100 p-1 pr-3 rounded-full transition-colors"
              >
                {user.picture ? (
                  <img src={user.picture} alt={user.name} className="w-10 h-10 rounded-full object-cover shadow-sm" />
                ) : (
                  <div className="w-10 h-10 rounded-full bg-black text-white flex items-center justify-center shadow-sm">
                    <User className="w-5 h-5" />
                  </div>
                )}
                <span className="font-semibold text-sm hidden sm:block">Welcome, {user.name?.split(' ')[0]}</span>
              </button>
            )}
          </div>
        </div>
      </nav>

      {/* Main Content Area - Outlet renders the current page */}
      <main className="relative z-10 pt-20">
        <Outlet />
      </main>

      {/* Sliding Preferences Drawer */}
      <div 
        className={`fixed inset-y-0 right-0 z-[60] w-80 bg-white/90 backdrop-blur-2xl shadow-2xl border-l border-white/50 transform transition-transform duration-300 ease-in-out ${isDrawerOpen ? 'translate-x-0' : 'translate-x-full'}`}
      >
        <div className="p-6">
          <div className="flex justify-between items-center mb-8">
            <h2 className="text-xl font-bold tracking-tight">Preferences</h2>
            <button onClick={() => setIsDrawerOpen(false)} className="p-2 hover:bg-neutral-100 rounded-full">
              <X className="w-5 h-5" />
            </button>
          </div>
          
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-bold mb-2">Daily Commute (km)</label>
              <input type="range" min="0" max="100" className="w-full accent-black" />
            </div>
            <div>
              <label className="block text-sm font-bold mb-2">Tax Status</label>
              <select className="w-full p-3 bg-neutral-100 rounded-lg outline-none font-medium border border-transparent focus:border-black">
                <option>Filer</option>
                <option>Non-Filer</option>
              </select>
            </div>
            <button 
              onClick={() => setIsAuthenticated(false)}
              className="w-full mt-4 py-3 bg-red-50 text-red-600 font-bold rounded-lg hover:bg-red-100 transition-colors"
            >
              Sign Out
            </button>
          </div>
        </div>
      </div>

    </div>
  );
}