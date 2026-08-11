import React from 'react';
import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center text-center px-4 font-sans">
      <h1 className="font-display text-6xl font-black text-text mb-4">404</h1>
      <h2 className="text-2xl font-semibold text-text-dim mb-6">Page Not Found</h2>
      <p className="text-text-faint max-w-md mb-8">
        Oops! The page you're looking for doesn't exist or has been moved.
      </p>

      <div className="flex flex-col sm:flex-row gap-4">
        <Link to="/" className="btn-primary">
          Back to Home
        </Link>
        <Link to="/recommend" className="btn-ghost">
          Try AI Matchmaker
        </Link>
      </div>
    </div>
  );
}
