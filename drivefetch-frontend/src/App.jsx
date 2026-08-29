import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useOutletContext } from 'react-router-dom';

// Import Layout
import MainLayout from './layouts/MainLayout';
import FeatureErrorBoundary from './components/FeatureErrorBoundary';

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
      return { hasChunkError: true };
    }
    // Re-throw non-chunk errors so they propagate normally
    throw error;
  }

  componentDidCatch(error) {
    if (ChunkErrorBoundary.isChunkLoadError(error)) {
      const reloadKey = 'df-chunk-reload';

      // Guard against infinite reload loops: only reload once per session
      if (!sessionStorage.getItem(reloadKey)) {
        sessionStorage.setItem(reloadKey, '1');
        window.location.reload();
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
        <div className="flex h-screen items-center justify-center flex-col gap-6 px-6">
          <div className="font-mono text-xs font-bold tracking-[0.1em] text-df-black/50 dark:text-white/50 uppercase text-center">
            [SYS_UPDATE_DETECTED] — A new version is available.
          </div>
          <button
            onClick={() => {
              sessionStorage.removeItem('df-chunk-reload');
              window.location.reload();
            }}
            className="border-2 border-black dark:border-white px-6 py-3 font-mono text-sm font-bold uppercase tracking-[0.06em] hover:-translate-y-0.5 hover:shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] dark:hover:shadow-[3px_3px_0px_0px_rgba(255,255,255,1)] transition-all"
          >
            [ RELOAD PAGE ]
          </button>
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
    return <div className="flex h-screen items-center justify-center font-mono text-xs font-bold tracking-[0.1em] text-df-black/40 uppercase">[LOADING_AUTH]</div>;
  }
  
  if (!isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return children;
}

export default function App() {
  return (
    <ChunkErrorBoundary>
      <BrowserRouter>
        <Suspense fallback={<div className="flex h-screen items-center justify-center font-mono text-xs font-bold tracking-[0.1em] text-df-black/40 dark:text-white/40 uppercase">[LOADING_SYS]</div>}>
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