import { Link } from 'react-router-dom';
import { useScrollTo } from '../motion/SmoothScroll';

const LINKS = [
  { to: '/', label: 'Discover' },
  { to: '/recommend', label: 'Matchmaker' },
  { to: '/chat', label: 'Chat' },
  { to: '/calculators', label: 'Calculators' },
  { to: '/about', label: 'About' },
  { to: '/about#contact', label: 'Contact' },
  { to: '/privacy', label: 'Privacy' },
];

export default function SiteFooter() {
  const scrollTo = useScrollTo();
  return (
    <footer className="border-t border-neutral-200 dark:border-zinc-800 bg-white dark:bg-df-night">
      <div className="px-4 sm:px-6 lg:px-10 py-8 flex flex-col gap-6">
        <div className="flex flex-wrap items-center justify-between gap-x-8 gap-y-4">
          <nav aria-label="Footer" className="flex flex-wrap gap-x-6 gap-y-2 text-[15px] font-semibold">
            {LINKS.map((l) => (
              <Link key={l.to} to={l.to} className="df-link py-1">{l.label}</Link>
            ))}
          </nav>
          <button
            type="button"
            onClick={() => scrollTo(0)}
            className="group flex items-center gap-2 text-[15px] font-semibold"
          >
            Back to top
            <span aria-hidden="true" className="inline-block transition-transform duration-500 group-hover:-translate-y-1">↑</span>
          </button>
        </div>
        <div className="flex flex-wrap justify-between gap-3 text-[13px] df-muted">
          <span>© {new Date().getFullYear()} DriveFetch · Built by Muhammad Ismail</span>
          <span>Listings belong to their original sites. We link back to every ad.</span>
        </div>
      </div>
    </footer>
  );
}
