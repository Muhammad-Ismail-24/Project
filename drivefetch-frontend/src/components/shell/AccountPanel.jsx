import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTheme } from '../../contexts/ThemeContext';
import useDialog from './useDialog';
import { Spinner } from '../ui/Loaders';

export default function AccountPanel({ open, onClose, user, assistantName, onSaveAssistantName, onLogout }) {
  const { theme, chooseTheme } = useTheme();
  const ref = useDialog(open, onClose);
  const [draft, setDraft] = useState(assistantName);
  const [saveState, setSaveState] = useState('idle'); // idle | saving | saved | error
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    if (open) {
      setDraft(assistantName);
      setSaveState('idle');
      setConfirming(false);
    }
  }, [open, assistantName]);

  useEffect(() => {
    if (saveState !== 'saved') return undefined;
    const t = setTimeout(() => setSaveState('idle'), 1800);
    return () => clearTimeout(t);
  }, [saveState]);

  if (!open || !user) return null;

  const unchanged = draft.trim() === (assistantName || '').trim();
  const initial = (user.name || 'U').trim().charAt(0).toUpperCase();

  const save = async () => {
    if (unchanged || saveState === 'saving') return;
    setSaveState('saving');
    try {
      await onSaveAssistantName(draft);
      setSaveState('saved');
    } catch {
      setSaveState('error');
    }
  };

  return (
    <div className="fixed inset-0 z-[90]">
      <button type="button" aria-label="Close account panel" onClick={onClose} className="absolute inset-0 w-full h-full bg-black/55 animate-df-fade-up cursor-default" tabIndex={-1} />
      <aside
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby="acc-title"
        className="absolute top-0 right-0 bottom-0 w-full max-w-[440px] bg-white text-black dark:bg-df-night dark:text-zinc-50 border-l-4 border-df-red flex flex-col animate-df-slide-in-right"
      >
        <div className="flex items-center justify-between px-6 sm:px-7 py-5 border-b-2 border-black dark:border-zinc-50">
          <h2 id="acc-title" className="df-display text-[44px]">Account</h2>
          <button type="button" onClick={onClose} aria-label="Close" data-autofocus className="w-11 h-11 border border-black dark:border-zinc-700 text-2xl leading-none hover:bg-black hover:text-white dark:hover:bg-zinc-50 dark:hover:text-black">×</button>
        </div>

        <div data-lenis-prevent className="flex-1 overflow-y-auto px-6 sm:px-7 py-6 flex flex-col gap-7">
          <div className="flex items-center gap-4">
            {user.picture ? (
              <img src={user.picture} alt="" className="w-16 h-16 object-cover" referrerPolicy="no-referrer" />
            ) : (
              <span className="w-16 h-16 bg-df-red text-white flex items-center justify-center text-3xl font-black [font-stretch:70%]">{initial}</span>
            )}
            <div className="flex flex-col min-w-0">
              <strong className="text-xl truncate">{user.name}</strong>
              <span className="font-mono text-[12.5px] df-muted truncate">{user.email}</span>
            </div>
          </div>

          <nav aria-label="Your stuff" className="flex flex-col border-t border-black dark:border-zinc-700">
            <Link to="/saved" onClick={onClose} className="flex items-center justify-between min-h-[56px] border-b border-black dark:border-zinc-700 text-[17px] font-extrabold hover:text-df-red">
              Saved cars <span aria-hidden="true">→</span>
            </Link>
            <Link to="/chat" onClick={onClose} className="flex items-center justify-between min-h-[56px] border-b border-black dark:border-zinc-700 text-[17px] font-extrabold hover:text-df-red">
              Chat history <span aria-hidden="true">→</span>
            </Link>
          </nav>

          <div className="flex flex-col gap-2">
            <label htmlFor="acc-bot" className="text-sm font-extrabold">Your assistant’s name</label>
            <div className="flex">
              <input
                id="acc-bot"
                type="text"
                maxLength={24}
                value={draft}
                onChange={(e) => { setDraft(e.target.value); setSaveState('idle'); }}
                onKeyDown={(e) => { if (e.key === 'Enter') save(); }}
                placeholder="e.g. Ustaad"
                className="df-input border-r-0 font-bold"
              />
              <button
                type="button"
                onClick={save}
                disabled={unchanged && saveState !== 'saved'}
                className={`px-5 text-sm font-extrabold text-white transition-colors flex items-center gap-2 ${
                  saveState === 'saved' ? 'bg-black dark:bg-zinc-700' : unchanged ? 'bg-neutral-400 dark:bg-zinc-700 cursor-not-allowed' : 'bg-df-red hover:bg-black'
                }`}
              >
                {saveState === 'saving' ? <Spinner className="w-4 h-4" light /> : null}
                {saveState === 'saved' ? 'Saved ✓' : 'Save'}
              </button>
            </div>
            <span className={`text-[13px] ${saveState === 'error' ? 'font-bold text-df-red-dark dark:text-zinc-50' : 'df-muted'}`} role={saveState === 'error' ? 'alert' : undefined}>
              {saveState === 'error' ? 'Couldn’t save. Check your connection and try again.' : 'Shown in Chat. Your assistant answers to this name.'}
            </span>
          </div>

          <fieldset className="flex flex-col gap-2">
            <legend className="text-sm font-extrabold mb-2">Theme</legend>
            <div role="radiogroup" aria-label="Theme" className="grid grid-cols-2">
              {['light', 'dark'].map((t) => (
                <button
                  key={t}
                  type="button"
                  role="radio"
                  aria-checked={theme === t}
                  onClick={() => chooseTheme(t)}
                  className={`h-12 border border-black dark:border-zinc-700 -ml-px first:ml-0 text-sm font-extrabold capitalize ${
                    theme === t ? 'bg-black text-white dark:bg-zinc-50 dark:text-black' : ''
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </fieldset>
        </div>

        <div className="px-6 sm:px-7 py-5 border-t-2 border-black dark:border-zinc-50 bg-df-grey dark:bg-black">
          {confirming ? (
            <div className="flex flex-col gap-2.5">
              <strong>Sign out of DriveFetch?</strong>
              <div className="flex gap-2">
                <button type="button" onClick={onLogout} className="df-btn-red flex-1 h-12">Sign out</button>
                <button type="button" onClick={() => setConfirming(false)} className="df-btn-outline flex-1 h-12">Stay</button>
              </div>
            </div>
          ) : (
            <button type="button" onClick={() => setConfirming(true)} className="df-btn-outline w-full h-12">Sign out</button>
          )}
        </div>
      </aside>
    </div>
  );
}
