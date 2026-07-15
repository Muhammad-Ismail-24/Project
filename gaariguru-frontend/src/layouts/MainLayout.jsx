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
      
      {/* ── Flat Grey Top Navigation with Black Border ── */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-[#a3a3a3] border-b border-black">
        <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
          
          {/* Logo */}
          <Link to="/" className="text-2xl font-black tracking-tighter uppercase text-black">
            GaariGuru
          </Link>

          {/* Center Links (Stark Black) */}
          <div className="hidden md:flex space-x-8">
            <Link to="/" className="font-bold text-black hover:opacity-70 transition-opacity">Discover</Link>
            <Link to="/calculators" className="font-bold text-black hover:opacity-70 transition-opacity">Calculators</Link>
            <Link to="/chat" className="font-bold text-black hover:opacity-70 transition-opacity">Assistant</Link>
            <Link to="/about" className="font-bold text-black hover:opacity-70 transition-opacity">About</Link>
          </div>

          {/* Auth Section */}
          <div className="flex items-center">
            {isLoading ? (
              <div className="w-8 h-8 rounded-full border-2 border-black/30 border-t-black animate-spin"></div>
            ) : !isAuthenticated || !user ? (
              <button 
                onClick={() => window.location.href = 'https://carfinder-project-backend.onrender.com/auth/login'}
                className="flex items-center px-4 py-2 bg-[#a3a3a3] border border-black rounded-full hover:bg-black hover:text-white transition-colors font-bold text-sm"
              >
                <img src="https://www.svgrepo.com/show/475656/google-color.svg" alt="Google" className="w-4 h-4 mr-2 bg-white rounded-full" />
                Sign in
              </button>
            ) : (
              <button 
                onClick={() => setIsDrawerOpen(true)}
                className="flex items-center gap-2 hover:bg-black/10 p-1 pr-3 rounded-full transition-colors"
              >
                {user.picture ? (
                  <img src={user.picture} alt={user.name} className="w-10 h-10 rounded-full object-cover border border-black" />
                ) : (
                  <div className="w-10 h-10 rounded-full bg-black text-white flex items-center justify-center">
                    <User className="w-5 h-5" />
                  </div>
                )}
                <span className="font-bold text-sm hidden sm:block text-black">Welcome, {user.name?.split(' ')[0]}</span>
              </button>
            )}
          </div>
        </div>
      </nav>

      {/* Main Content Area */}
      <main className="relative z-10 pt-20">
        <Outlet />
      </main>

      {/* Sliding Preferences Drawer (Also styled to match) */}
      <div 
        className={`fixed inset-y-0 right-0 z-[60] w-80 bg-[#a3a3a3] shadow-2xl border-l border-black transform transition-transform duration-300 ease-in-out ${isDrawerOpen ? 'translate-x-0' : 'translate-x-full'}`}
      >
        <div className="p-6">
          <div className="flex justify-between items-center mb-8 border-b border-black pb-4">
            <h2 className="text-xl font-black tracking-tight text-black">Preferences</h2>
            <button onClick={() => setIsDrawerOpen(false)} className="p-2 hover:bg-black/10 rounded-full text-black">
              <X className="w-6 h-6" />
            </button>
          </div>
          
          <div className="space-y-6">
            <Link 
              to="/saved" 
              onClick={() => setIsDrawerOpen(false)}
              className="flex items-center justify-between w-full p-4 bg-black text-white rounded-xl hover:bg-neutral-800 transition-colors font-bold border border-black"
            >
              <span>My Saved Cars</span>
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/></svg>
            </Link>
            <div>
              <label className="block text-sm font-bold mb-2 text-black">Daily Commute (km)</label>
              <input type="range" min="0" max="100" className="w-full accent-black" />
            </div>
            <div>
              <label className="block text-sm font-bold mb-2 text-black">Tax Status</label>
              <select className="w-full p-3 bg-transparent border border-black rounded-lg outline-none font-bold text-black focus:ring-2 focus:ring-black">
                <option>Filer</option>
                <option>Non-Filer</option>
              </select>
            </div>
            <button 
              onClick={() => setIsAuthenticated(false)}
              className="w-full mt-4 py-3 bg-transparent border border-black text-black font-black rounded-lg hover:bg-black hover:text-white transition-colors"
            >
              Sign Out
            </button>
          </div>
        </div>
      </div>

    </div>
  );
}