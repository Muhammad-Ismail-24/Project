import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';

// Import the Layout
import MainLayout from './layouts/MainLayout';

// Import all the Pages
import Home from './pages/Home';
import CalculatorsHub from './pages/CalculatorsHub';
import ChatPage from './pages/ChatPage';
import About from './pages/About';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MainLayout />}>
          {/* Default Route */}
          <Route index element={<Home />} />
          
          {/* New Page Routes */}
          <Route path="calculators" element={<CalculatorsHub />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="about" element={<About />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}