import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { ThemeProvider } from '../contexts/ThemeContext';
import UIContext from '../contexts/UIContext';
import SiteHeader from '../components/shell/SiteHeader';
import SiteFooter from '../components/shell/SiteFooter';
import SiteMenu from '../components/shell/SiteMenu';
import SignInSheet from '../components/shell/SignInSheet';
import SplashScreen from '../components/SplashScreen';
import { useScrollLock } from '../components/motion/SmoothScroll';

export default function MainLayout() {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [menuView, setMenuView] = useState('main'); // which view the menu opens on
  const [signInReason, setSignInReason] = useState(null); // null = closed
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [assistantName, setAssistantName] = useState('DriveFetch AI');
  const location = useLocation();
  const { lock, unlock } = useScrollLock();

  // Close overlays on route change
  useEffect(() => {
    setIsMenuOpen(false);
    setSignInReason(null);
  }, [location.pathname]);

  // Pause scrolling (Lenis and native) while any overlay is open
  const overlayOpen = isMenuOpen || signInReason !== null;
  useEffect(() => {
    if (overlayOpen) lock('overlay');
    else unlock('overlay');
    return () => unlock('overlay');
  }, [overlayOpen, lock, unlock]);

  useEffect(() => {
    if (user?.bot_name) setAssistantName(user.bot_name);
  }, [user?.bot_name]);

  // Auth check (same endpoints and behaviour as before the redesign)
  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;

    const checkAuth = async () => {
      try {
        const response = await fetch('/auth/me', {
          method: 'GET',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          signal,
        });
        if (response.ok) {
          const userData = await response.json();
          if (signal.aborted) return;
          setUser(userData);
          setIsAuthenticated(true);
          if (userData.bot_name) {
            setAssistantName(userData.bot_name);
          } else {
            try {
              const sessRes = await fetch('/api/chat/sessions', { method: 'GET', credentials: 'include', signal });
              if (sessRes.ok) {
                const sessData = await sessRes.json();
                if (!sessData.is_guest && sessData.sessions && sessData.sessions.length > 0) {
                  const histRes = await fetch(`/api/chat/history/${sessData.sessions[0].session_id}`, { method: 'GET', credentials: 'include', signal });
                  if (histRes.ok) {
                    const histData = await histRes.json();
                    if (!signal.aborted && histData.agent_name) {
                      setAssistantName(histData.agent_name);
                      setUser((prev) => ({ ...prev, bot_name: histData.agent_name }));
                    }
                  }
                }
              }
            } catch (chatErr) {
              if (chatErr.name !== 'AbortError') {
                console.error('Chat preferences fetch failed:', chatErr instanceof Error ? chatErr.message : 'Unknown error');
              }
            }
          }
        } else if (!signal.aborted) {
          setIsAuthenticated(false);
          setUser(null);
        }
      } catch (error) {
        if (error.name !== 'AbortError') {
          console.error('Auth check failed:', error instanceof Error ? error.message : 'Unknown error');
        }
        if (!signal.aborted) {
          setIsAuthenticated(false);
          setUser(null);
        }
      } finally {
        if (!signal.aborted) setIsLoading(false);
      }
    };
    checkAuth();
    return () => controller.abort();
  }, [location.pathname]);

  const handleLogout = useCallback(async () => {
    try {
      await fetch('/auth/logout', { method: 'GET', credentials: 'include' });
    } catch (error) {
      console.error('Logout request failed', error instanceof Error ? error.message : 'Unknown error');
    } finally {
      try { localStorage.removeItem('df-garage-v1'); } catch { /* storage blocked */ }
      try { sessionStorage.clear(); } catch { /* storage blocked */ }
      setUser(null);
      setIsAuthenticated(false);
      document.cookie = 'has_auth=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
      window.location.replace('/');
    }
  }, []);

  const saveAssistantName = useCallback(async (name) => {
    const clean = String(name || '').trim().slice(0, 24) || 'DriveFetch AI';
    const res = await fetch('/user/preferences', {
      method: 'PATCH',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bot_name: clean }),
    });
    if (!res.ok) throw new Error('Could not save the name');
    setAssistantName(clean);
    setUser((prev) => (prev ? { ...prev, bot_name: clean } : prev));
    return clean;
  }, []);

  const openSignIn = useCallback((reason = 'generic') => {
    setIsMenuOpen(false);
    setSignInReason(reason);
  }, []);
  // Account and settings live inside the menu now.
  const openAccount = useCallback(() => {
    setMenuView('settings');
    setIsMenuOpen(true);
  }, []);
  const toggleMenu = useCallback(() => {
    setMenuView('main');
    setIsMenuOpen((v) => !v);
  }, []);

  const uiValue = useMemo(() => ({
    user, isAuthenticated, isLoading, openSignIn, openAccount, assistantName, setAssistantName, saveAssistantName,
  }), [user, isAuthenticated, isLoading, openSignIn, openAccount, assistantName, saveAssistantName]);

  const isChat = location.pathname === '/chat';

  return (
    <ThemeProvider user={user}>
      <UIContext.Provider value={uiValue}>
        <SplashScreen />
        <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[100] focus:px-4 focus:py-3 focus:bg-df-red focus:text-white focus:font-bold">
          Skip to content
        </a>
        <div className="relative min-h-screen flex flex-col bg-white text-black dark:bg-df-night dark:text-zinc-50 font-body transition-colors duration-200">
          <SiteHeader
            isAuthenticated={isAuthenticated}
            isLoading={isLoading}
            menuOpen={isMenuOpen}
            onToggleMenu={toggleMenu}
          />

          <main id="main" className="relative flex-grow flex flex-col">
            <Outlet context={{ user, isAuthenticated, isLoading, assistantName, setAssistantName, openSignIn, saveAssistantName }} />
          </main>

          {!isChat && <SiteFooter />}
        </div>

        <SiteMenu
          open={isMenuOpen}
          initialView={menuView}
          onClose={() => setIsMenuOpen(false)}
          onNavigateSame={() => setIsMenuOpen(false)}
          isAuthenticated={isAuthenticated}
          user={user}
          assistantName={assistantName}
          onSaveAssistantName={saveAssistantName}
          onLogout={handleLogout}
        />
        <SignInSheet reason={signInReason} onClose={() => setSignInReason(null)} />
      </UIContext.Provider>
    </ThemeProvider>
  );
}
