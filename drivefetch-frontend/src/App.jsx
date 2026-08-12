import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';

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

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<div className="flex h-screen items-center justify-center font-mono text-xs font-bold tracking-[0.1em] text-df-black/40 uppercase">[LOADING_SYS]</div>}>
        <Routes>
          <Route path="/" element={<MainLayout />}>
            {/* Default Route */}
            <Route index element={<Home />} />
            
            {/* Page Routes */}
            <Route path="saved" element={<SavedCarsPage />} />
            <Route path="calculators" element={<CalculatorsHub />} />
            <Route path="chat" element={<ChatPage />} />
            <Route path="about" element={<About />} />
            <Route path="recommend" element={<RecommendPage />} /> {/* <--- NEW ROUTE */}
            
            {/* Catch-all 404 Route */}
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}