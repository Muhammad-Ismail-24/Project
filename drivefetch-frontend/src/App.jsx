import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';

// Import Layout
import MainLayout from './layouts/MainLayout';

// Import Pages
const Home = lazy(() => import('./pages/Home'));
const SavedCarsPage = lazy(() => import('./pages/SavedCarsPage'));
const CalculatorsHub = lazy(() => import('./pages/CalculatorsHub'));
const ChatPage = lazy(() => import('./pages/ChatPage'));
const About = lazy(() => import('./pages/About'));
const RecommendPage = lazy(() => import('./pages/RecommendPage'));
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'));

// Protected Route Wrapper
function ProtectedRoute({ children }) {
  if (!document.cookie.includes('has_auth=1')) {
    return <Navigate to="/" replace />;
  }
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<div className="flex h-screen items-center justify-center font-mono text-xs font-bold tracking-[0.1em] text-df-black/40 uppercase">[LOADING_SYS]</div>}>
        <Routes>
          <Route path="/" element={<MainLayout />}>
            {/* Default Route */}
            <Route index element={<Home />} />
            
            {/* Page Routes */}
            {/* Protected Routes */}
            <Route path="saved" element={<ProtectedRoute><SavedCarsPage /></ProtectedRoute>} />
            <Route path="chat" element={<ProtectedRoute><ChatPage /></ProtectedRoute>} />
            <Route path="recommend" element={<ProtectedRoute><RecommendPage /></ProtectedRoute>} />
            
            {/* Public Routes */}
            <Route path="calculators" element={<CalculatorsHub />} />
            
            {/* Catch-all 404 Route */}
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}