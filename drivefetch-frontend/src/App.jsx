import React, { Suspense, lazy, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useOutletContext } from 'react-router-dom';

// Import Layout
import MainLayout from './layouts/MainLayout';
import FeatureErrorBoundary from './components/FeatureErrorBoundary';
import { PageLoader } from './components/ui/Loaders';
import { dismissSplash } from './components/SplashScreen';

// Import Pages
const Home = lazy(() => import('./pages/Home'));
const SavedCarsPage = lazy(() => import('./pages/SavedCarsPage'));
const CalculatorsHub = lazy(() => import('./pages/CalculatorsHub'));
const ChatPage = lazy(() => import('./pages/ChatPage'));
const About = lazy(() => import('./pages/About'));
const RecommendPage = lazy(() => import('./pages/RecommendPage'));
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'));
const PrivacyPolicy = lazy(() => import('./pages/PrivacyPolicy'));

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

export default function App() {
  // Clear the chunk-reload guard after a successful mount.
  // This resets the mechanism so it's ready for the next deployment.
  useEffect(() => {
    sessionStorage.removeItem('vite-chunk-reload');
  }, []);

  return (
    <ChunkErrorBoundary>
      <BrowserRouter>
        <Suspense fallback={<PageLoader label="Loading…" />}>
          <Routes>
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
      </BrowserRouter>
    </ChunkErrorBoundary>
  );
}