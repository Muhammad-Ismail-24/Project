import { useState } from 'react';
import { Link } from 'react-router-dom';
import useDialog from './useDialog';
import { Spinner } from '../ui/Loaders';

const TITLES = {
  save: 'Sign in to save this car.',
  chat: 'Sign in to keep this chat.',
  saved: 'Sign in to see your garage.',
  generic: 'Sign in to keep your cars.',
};

export default function SignInSheet({ reason, onClose }) {
  const open = reason !== null && reason !== undefined;
  const ref = useDialog(open, onClose);
  const [redirecting, setRedirecting] = useState(false);
  if (!open) return null;

  const go = () => {
    setRedirecting(true);
    window.location.href = '/auth/login';
  };

  return (
    <div className="fixed inset-0 z-[95] bg-black/60 flex items-end sm:items-center justify-center p-0 sm:p-6" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby="signin-title"
        className="w-full sm:max-w-[560px] bg-white text-black dark:bg-df-night dark:text-zinc-50 flex flex-col animate-df-fade-up"
      >
        <div className="bg-df-red text-white px-6 sm:px-8 py-6 sm:py-7 flex items-start justify-between gap-4">
          <h2 id="signin-title" className="df-display text-[44px] sm:text-[56px]">{TITLES[reason] || TITLES.generic}</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="w-11 h-11 shrink-0 border-2 border-white text-2xl leading-none hover:bg-white hover:text-df-red">×</button>
        </div>
        <div className="px-6 sm:px-8 py-6 sm:py-8 flex flex-col gap-5">
          <ul className="flex flex-col text-[17px] leading-snug">
            {['Save cars and come back to them on any device', 'Keep your chats and name your assistant', 'Your light or dark theme follows you'].map((t, i) => (
              <li key={t} className="flex gap-3.5 py-3 border-t border-black dark:border-zinc-700 last:border-b">
                <span className="font-mono font-semibold text-df-red-dark dark:text-zinc-400">0{i + 1}</span>{t}
              </li>
            ))}
          </ul>
          <button type="button" onClick={go} disabled={redirecting} data-autofocus className="df-btn-ink h-14 text-base">
            {redirecting ? <Spinner className="w-4 h-4" /> : null}
            {redirecting ? 'Opening Google…' : 'Continue with Google'}
          </button>
          <div className="flex items-center justify-between text-[13px] df-muted">
            <span>We never see your password · <Link to="/privacy" onClick={onClose} className="underline underline-offset-2">Privacy</Link></span>
            <button type="button" onClick={onClose} className="h-11 text-sm font-bold text-black dark:text-zinc-50 underline underline-offset-2">Not now</button>
          </div>
        </div>
      </div>
    </div>
  );
}
