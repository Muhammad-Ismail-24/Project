import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';

// Import Layout
import MainLayout from './layouts/MainLayout';

// Import Pages
import Home from './pages/Home';
import SavedCarsPage from './pages/SavedCarsPage';
import CalculatorsHub from './pages/CalculatorsHub';
import ChatPage from './pages/ChatPage';
import About from './pages/About';
import RecommendPage from './pages/RecommendPage'; // <--- IMPORT RECOMMENDER PAGE

export default function App() {
  return (
    <BrowserRouter>
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
        </Route>
      </Routes>
    </BrowserRouter>
  );
}