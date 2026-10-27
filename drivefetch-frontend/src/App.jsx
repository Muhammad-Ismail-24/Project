import React, { Suspense, lazy, useEffect, useRef, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useOutletContext, useLocation } from 'react-router-dom';

// Import Layout
import MainLayout from './layouts/MainLayout';
import FeatureErrorBoundary from './components/FeatureErrorBoundary';
import { PageLoader } from './components/ui/Loaders';
import { dismissSplash } from './components/SplashScreen';
import SmoothScroll, { useLenis, useScrollLock } from './components/motion/SmoothScroll';
import useAutoReveal from './components/motion/useAutoReveal';

// Page chunks. Kept in a map so a page can be fetched while the transition
// curtain is covering the screen, before it is shown.
const PAGES = {
  '/': () => import('./pages/Home'),
  '/saved': () => import('./pages/SavedCarsPage'),
  '/calculators': () => import('./pages/CalculatorsHub'),
  '/chat': () => import('./pages/ChatPage'),
  '/about': () => import('./pages/About'),
  '/recommend': () => import('./pages/RecommendPage'),
  '/privacy': () => import('./pages/PrivacyPolicy'),
  '404': () => import('./pages/NotFoundPage'),
};
const Home = lazy(PAGES['/']);
const SavedCarsPage = lazy(PAGES['/saved']);
const CalculatorsHub = lazy(PAGES['/calculators']);
const ChatPage = lazy(PAGES['/chat']);
const About = lazy(PAGES['/about']);
const RecommendPage = lazy(PAGES['/recommend']);
const NotFoundPage = lazy(PAGES['404']);
const PrivacyPolicy = lazy(PAGES['/privacy']);

const PAGE_LABELS = {
  '/': 'Discover',
  '/recommend': 'Matchmaker',
  '/chat': 'Chat',
  '/calculators': 'Calculators',
  '/saved': 'Saved cars',
  '/about': 'About',
  '/privacy': 'Privacy',
};

/**
 * ChunkErrorBoundary
 *
 * After a new Vercel deployment, browsers with stale sessions try to fetch
 * lazy-loaded chunks whose hashed filenames no longer exist. Vercel returns
 * index.html (MIME "text/html") instead of JS, causing a white-screen crash.
 *
 * This boundary catches those specific errors and forces a single hard reload
 * so the browser fetches the latest index.html (with updated chunk URLs).
 * A sessionStorage flag prevents infinite reload loops.
 */
class ChunkErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasChunkError: false };
  }

  static getDerivedStateFromError(error) {
    if (ChunkErrorBoundary.isChunkLoadError(error)) {
      return { hasChunkError: true, errorMsg: error?.message };
    }
    // Re-throw non-chunk errors so they propagate normally
    throw error;
  }

  componentDidCatch(error) {
    dismissSplash();
    if (ChunkErrorBoundary.isChunkLoadError(error)) {
      const reloadKey = 'vite-chunk-reload';

      // Guard against infinite reload loops: only reload once per session
      if (!sessionStorage.getItem(reloadKey)) {
        sessionStorage.setItem(reloadKey, 'true');
        window.location.reload(true);
      }
    }
  }

  /**
   * Detects the two error signatures Vite produces for stale chunks:
   * 1. "Failed to fetch dynamically imported module"  (network / 404)
   * 2. "Loading chunk … failed"                       (older bundlers / edge cases)
   */
  static isChunkLoadError(error) {
    const msg = error?.message || '';
    return (
      msg.includes('Failed to fetch dynamically imported module') ||
      msg.includes('Loading chunk') ||
      msg.includes('Loading CSS chunk') ||
      error?.name === 'ChunkLoadError'
    );
  }

  render() {
    if (this.state.hasChunkError) {
      return (
        <div role="alert" className="min-h-screen bg-df-red text-white flex flex-col justify-between p-8 sm:p-12">
          <span className="font-mono text-xs font-semibold">NEW VERSION</span>
          <div className="flex flex-col gap-6 max-w-2xl">
            <h1 className="df-display text-[length:clamp(72px,12vw,160px)]">Fresh<br /><span className="text-black">paint.</span></h1>
            <p className="text-lg leading-relaxed">DriveFetch was updated while this tab was open. Reload to get the new version. Your saved cars are safe.</p>
            <button
              type="button"
              onClick={() => window.location.replace(window.location.pathname)}
              className="self-start h-14 px-7 bg-black text-white text-base font-extrabold tracking-wide hover:bg-white hover:text-black transition-colors"
            >
              Reload
            </button>
          </div>
          <span className="text-sm">If this keeps happening, clear the cache for this site.</span>
        </div>
      );
    }
    return this.props.children;
  }
}

// Protected Route Wrapper
function ProtectedRoute({ children }) {
  const context = useOutletContext();
  // If context is undefined, it means we're outside MainLayout, but we shouldn't be.
  const isLoading = context?.isLoading ?? false;
  const isAuthenticated = context?.isAuthenticated ?? false;

  if (isLoading) {
    return <PageLoader label="Checking your sign-in…" />;
  }
  
  if (!isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return children;
}

/**
 * Routes with a page transition. When the path changes, a red curtain rises
 * over the old page (showing the destination's name), the new page chunk is
 * fetched meanwhile, the page is swapped and scrolled to the top under cover,
 * then the curtain lifts away and the new page's reveals play.
 *
 * Query-string or hash changes on the same page swap instantly. So do
 * navigations from the open menu, because the menu's own exit already acts as
 * the transition.
 */
function AnimatedRoutes() {
  const location = useLocation();
  const lenis = useLenis();
  const { lock, unlock } = useScrollLock();
  const [display, setDisplay] = useState(location);
  const [phase, setPhase] = useState('idle'); // idle | covering | revealing
  const [label, setLabel] = useState('');
  const displayRef = useRef(location);
  const timers = useRef([]);

  useAutoReveal();

  useEffect(() => {
    const prev = displayRef.current;
    if (location.key === prev.key && location.pathname === prev.pathname && location.search === prev.search && location.hash === prev.hash) return undefined;

    const root = document.documentElement;
    const clearTimers = () => { timers.current.forEach(clearTimeout); timers.current = []; };
    const later = (fn, ms) => timers.current.push(setTimeout(fn, ms));
    const swap = () => {
      displayRef.current = location;
      setDisplay(location);
    };
    clearTimers();

    const samePage = location.pathname === prev.pathname;
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const fromMenu = root.classList.contains('df-menu-open');
    const introPlaying = Boolean(document.getElementById('df-splash'));

    if (samePage || reduce || fromMenu || introPlaying) {
      swap();
      if (!samePage) {
        lenis?.scrollTo(0, { immediate: true, force: true });
        window.scrollTo(0, 0);
      }
      root.classList.remove('df-hold');
      unlock('route');
      setPhase('idle');
      return undefined;
    }

    let cancelled = false;
    setLabel(PAGE_LABELS[location.pathname] || 'DriveFetch');
    setPhase('covering');
    root.classList.add('df-hold');
    lock('route');

    const load = (PAGES[location.pathname] || PAGES['404'])().catch(() => null);
    const covered = new Promise((resolve) => later(resolve, 560));
    const capped = Promise.race([load, new Promise((resolve) => later(resolve, 1500))]);

    Promise.all([covered, capped]).then(() => {
      if (cancelled) return;
      swap();
      window.scrollTo(0, 0);
      unlock('route');
      lenis?.scrollTo(0, { immediate: true, force: true });
      later(() => {
        if (cancelled) return;
        setPhase('revealing');
        root.classList.remove('df-hold');
        later(() => { if (!cancelled) setPhase('idle'); }, 700);
      }, 90);
    });

    return () => {
      // A newer navigation interrupted this one; it takes over from here.
      cancelled = true;
    };
  }, [location, lenis, lock, unlock]);

  // After a swap, scroll to #hash targets (they may render a moment later).
  useEffect(() => {
    if (!display.hash) return undefined;
    let tries = 0;
    let timer = 0;
    const find = () => {
      const el = document.getElementById(decodeURIComponent(display.hash.slice(1)));
      if (el) {
        const top = el.getBoundingClientRect().top + window.scrollY - 90;
        if (lenis) lenis.scrollTo(top, { duration: 1.2, force: true });
        else window.scrollTo({ top, behavior: 'smooth' });
      } else if (tries++ < 15) {
        timer = setTimeout(find, 100);
      }
    };
    timer = setTimeout(find, 120);
    return () => clearTimeout(timer);
  }, [display, lenis]);

  const curtainClass = phase === 'covering' ? 'is-covering' : phase === 'revealing' ? 'is-revealing' : '';

  return (
    <>
      <Suspense fallback={<PageLoader label="Loading…" />}>
        <Routes location={display}>
          <Route path="/" element={<MainLayout />}>
            {/* Default Route */}
            <Route index element={<Home />} />

            {/* Page Routes */}
            {/* Public Routes */}
            <Route path="saved" element={<SavedCarsPage />} />
            <Route path="chat" element={<FeatureErrorBoundary featureName="AI Chat"><ChatPage /></FeatureErrorBoundary>} />
            <Route path="recommend" element={<FeatureErrorBoundary featureName="AI Matchmaker"><RecommendPage /></FeatureErrorBoundary>} />
            <Route path="about" element={<About />} />
            <Route path="calculators" element={<CalculatorsHub />} />
            <Route path="privacy" element={<PrivacyPolicy />} />

            {/* Catch-all 404 Route */}
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </Suspense>

      <div aria-hidden="true" className={`df-curtain fixed inset-0 z-[95] bg-df-red text-white flex items-end ${curtainClass}`}>
        <div className="w-full px-5 sm:px-10 pb-8 sm:pb-12 flex flex-wrap items-end justify-between gap-4">
          <span className="block overflow-hidden pb-2">
            <span className="df-ci df-display text-[length:clamp(64px,12vw,200px)]">{label}</span>
          </span>
          <span className="block overflow-hidden">
            <span className="df-ci font-mono text-[13px] font-semibold tracking-[0.08em]">DRIVEFETCH · USED CARS, PAKISTAN</span>
          </span>
        </div>
      </div>
    </>
  );
}

export default function App() {
  // Clear the chunk-reload guard after a successful mount.
  // This resets the mechanism so it's ready for the next deployment.
  useEffect(() => {
    sessionStorage.removeItem('vite-chunk-reload');
  }, []);

  return (
    <ChunkErrorBoundary>
      <BrowserRouter>
        <SmoothScroll>
          <AnimatedRoutes />
        </SmoothScroll>
      </BrowserRouter>
    </ChunkErrorBoundary>
  );
}
