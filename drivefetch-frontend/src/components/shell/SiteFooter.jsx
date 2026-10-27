import { Link } from 'react-router-dom';
import { REPO_URL } from './navLinks';

export default function SiteFooter() {
  return (
    <footer className="bg-black text-white border-t border-zinc-800">
      <div className="px-4 sm:px-6 lg:px-10 py-10 flex flex-col gap-8">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <span className="df-display text-[length:clamp(44px,6vw,80px)]">DriveFetch<span className="text-df-red">.</span></span>
          <nav aria-label="Footer" className="flex flex-wrap gap-x-6 gap-y-2 text-sm font-bold">
            <Link to="/" className="hover:text-df-red">Discover</Link>
            <Link to="/recommend" className="hover:text-df-red">Matchmaker</Link>
            <Link to="/chat" className="hover:text-df-red">Chat</Link>
            <Link to="/calculators" className="hover:text-df-red">Calculators</Link>
            <Link to="/about" className="hover:text-df-red">About</Link>
            <Link to="/privacy" className="hover:text-df-red">Privacy</Link>
            <Link to="/about#contact" className="hover:text-df-red">Contact</Link>
            <a href={REPO_URL} target="_blank" rel="noopener noreferrer" className="hover:text-df-red">GitHub ↗</a>
          </nav>
        </div>
        <div className="flex flex-wrap justify-between gap-3 pt-5 border-t border-zinc-800 text-[13px] text-zinc-400">
          <span>© {new Date().getFullYear()} DriveFetch · Built by Muhammad Ismail</span>
          <span>Listings belong to their original sites. DriveFetch links back to every ad.</span>
        </div>
      </div>
    </footer>
  );
}
