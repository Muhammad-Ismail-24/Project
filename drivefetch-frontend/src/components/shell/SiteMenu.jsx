import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { useTheme } from '../../contexts/ThemeContext';
import useDialog from './useDialog';
import { Spinner } from '../ui/Loaders';

const LINKS = [
  { to: '/', label: 'Discover', end: true, desc: 'Search seven sites at once' },
  { to: '/recommend', label: 'Matchmaker', desc: 'Three models that fit your life' },
  { to: '/chat', label: 'Chat', desc: 'Ask anything about buying' },
  { to: '/calculators', label: 'Calculators', desc: 'Tax, transfer and fuel' },
  { to: '/saved', label: 'Saved cars', desc: 'Your garage' },
  { to: '/about', label: 'About', desc: 'Why DriveFetch exists' },
];

const LEAVE_MS = 1000;
const SWITCH_MS = 260;

const signIn = () => { window.location.href = '/auth/login'; };

function GoogleMark() {
  return (
    <svg aria-hidden="true" width="18" height="18" viewBox="0 0 48 48">
      <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.5l6.7-6.7C35.6 2.4 30.2 0 24 0 14.6 0 6.6 5.4 2.7 13.3l7.8 6C12.4 13.6 17.7 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.1 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.4c-.5 2.9-2.1 5.3-4.6 7l7.4 5.7c4.3-4 6.9-9.9 6.9-17.2z" />
      <path fill="#FBBC05" d="M10.5 28.7A14.5 14.5 0 0 1 9.5 24c0-1.6.3-3.2.8-4.7l-7.8-6A24 24 0 0 0 0 24c0 3.9.9 7.5 2.6 10.7l7.9-6z" />
      <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.4-5.7c-2.1 1.4-4.8 2.3-8.5 2.3-6.3 0-11.6-4.1-13.5-9.7l-7.9 6C6.6 42.6 14.6 48 24 48z" />
    </svg>
  );
}

function GoogleButton({ tabIndex, className = '' }) {
  return (
    <button type="button" tabIndex={tabIndex} onClick={signIn} className={`df-btn h-12 px-5 bg-white text-black hover:text-white ${className}`} style={{ '--df-fill': '#000' }}>
      <GoogleMark /> Continue with Google
    </button>
  );
}

function Avatar({ user, size = 'w-14 h-14 text-2xl' }) {
  const initial = (user?.name || 'U').trim().charAt(0).toUpperCase();
  return user?.picture ? (
    <img src={user.picture} alt="" className={`${size} object-cover shrink-0`} referrerPolicy="no-referrer" />
  ) : (
    <span className={`${size} shrink-0 bg-black text-white flex items-center justify-center font-black`}>{initial}</span>
  );
}

/** One labelled row in the Settings view. */
function SettingRow({ i, label, hint, children }) {
  return (
    <div className="df-mrow grid md:grid-cols-[220px_minmax(0,1fr)] gap-x-8 gap-y-3 py-6 border-t border-white/30" style={{ '--i': i }}>
      <div className="flex flex-col gap-1">
        <span className="text-lg font-bold">{label}</span>
        {hint ? <span className="text-sm text-white/75 leading-snug">{hint}</span> : null}
      </div>
      <div className="flex flex-col gap-2 min-w-0">{children}</div>
    </div>
  );
}

/**
 * The one menu for everything: pages on the left, your account on the right,
 * and a Settings view (theme, assistant name, sign out) that swaps in place of
 * the page list.
 *
 * Opening drops two layers (black, then red) from the top, then each link rises
 * out of its own mask, 60ms apart. Closing runs it backwards. Switching between
 * the page list and Settings slides one view out and the other in.
 * Inspired by the menu on asiaxp.co.
 */
export default function SiteMenu({ open, initialView = 'main', onClose, isAuthenticated, user, assistantName, onSaveAssistantName, onLogout, onNavigateSame }) {
  const { theme, chooseTheme } = useTheme();
  const { pathname } = useLocation();
  const ref = useDialog(open, onClose);
  const [leaving, setLeaving] = useState(false);
  const [view, setView] = useState(initialView);
  const [exiting, setExiting] = useState(false);
  const [switched, setSwitched] = useState(false);
  const wasOpen = useRef(false);
  const viewRef = useRef(null);

  // Settings state
  const [draft, setDraft] = useState(assistantName || '');
  const [saveState, setSaveState] = useState('idle'); // idle | saving | saved | error
  const [confirmingOut, setConfirmingOut] = useState(false);

  useEffect(() => {
    const root = document.documentElement;
    if (open) {
      root.classList.add('df-menu-open');
      setLeaving(false);
      setView(initialView);
      setExiting(false);
      setSwitched(false);
      setDraft(assistantName || '');
      setSaveState('idle');
      setConfirmingOut(false);
      wasOpen.current = true;
      return undefined;
    }
    root.classList.remove('df-menu-open');
    if (!wasOpen.current) return undefined;
    wasOpen.current = false;
    setLeaving(true);
    const t = setTimeout(() => setLeaving(false), LEAVE_MS);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialView]);

  useEffect(() => {
    if (saveState !== 'saved') return undefined;
    const t = setTimeout(() => setSaveState('idle'), 1800);
    return () => clearTimeout(t);
  }, [saveState]);

  const switchTo = (next) => {
    if (next === view || exiting) return;
    setExiting(true);
    setTimeout(() => {
      setView(next);
      setExiting(false);
      setSwitched(true);
      setConfirmingOut(false);
      requestAnimationFrame(() => viewRef.current?.querySelector('[data-view-focus]')?.focus({ preventScroll: true }));
    }, SWITCH_MS);
  };

  const unchanged = draft.trim() === (assistantName || '').trim();
  const saveName = async () => {
    if (unchanged || saveState === 'saving') return;
    setSaveState('saving');
    try {
      await onSaveAssistantName(draft);
      setSaveState('saved');
    } catch {
      setSaveState('error');
    }
  };

  const active = LINKS.find((l) => (l.end ? pathname === l.to : pathname.startsWith(l.to)));
  const state = open ? 'is-open' : leaving ? 'is-leaving' : '';
  const tab = open ? 0 : -1;
  const signedIn = isAuthenticated && user;

  // Links to the page you're on close the menu here; any other page closes it
  // via the route change, so the menu's exit doubles as the page transition.
  const closeIfHere = (to) => () => { if (pathname === to.split('#')[0]) onNavigateSame?.(); };

  return (
    <div
      id="df-menu"
      ref={ref}
      role="dialog"
      aria-modal="true"
      aria-label={view === 'settings' ? 'Settings' : 'Menu'}
      aria-hidden={!open}
      data-lenis-prevent
      className={`df-menu fixed inset-0 z-[80] text-white ${state}`}
    >
      <div className="df-menu-layer l0 bg-black" />
      <div className="df-menu-layer l1 bg-df-red" />

      <div className="relative h-full flex flex-col pt-16 sm:pt-[72px] overflow-y-auto">
        <button
          type="button"
          onClick={onClose}
          tabIndex={tab}
          data-autofocus
          className="sr-only focus-visible:not-sr-only focus-visible:absolute focus-visible:top-20 focus-visible:right-4 focus-visible:px-4 focus-visible:py-2 focus-visible:bg-black focus-visible:text-white focus-visible:font-bold"
        >
          Close menu
        </button>

        <div className="flex-1 grid lg:grid-cols-[minmax(0,1.7fr)_minmax(320px,1fr)] gap-x-16 gap-y-10 px-4 sm:px-6 lg:px-10 pt-6 sm:pt-10 pb-6">
          {/* ── Left: pages, or Settings ── */}
          <div
            ref={viewRef}
            key={view}
            className={`df-view min-w-0 ${switched ? 'df-view-enter' : ''} ${exiting ? 'df-view-exit' : ''}`}
          >
            {view === 'main' ? (
              <nav aria-label="Main">
                <ul className="df-menu-list flex flex-col">
                  {LINKS.map((link, i) => {
                    const isCurrent = link === active;
                    return (
                      <li key={link.to} className="relative">
                        <span aria-hidden="true" className="df-mline absolute left-0 right-0 bottom-0 h-px bg-white/35" style={{ '--i': i }} />
                        <NavLink
                          to={link.to}
                          end={link.end}
                          tabIndex={tab}
                          data-view-focus={i === 0 ? '' : undefined}
                          onClick={closeIfHere(link.to)}
                          className="df-menu-link group flex items-center gap-4 sm:gap-6 py-2 sm:py-2.5"
                        >
                          <span className="block overflow-hidden w-8 shrink-0">
                            <span className="df-mi font-mono text-[13px] font-semibold" style={{ '--i': i }}>0{i + 1}</span>
                          </span>
                          <span className="df-menu-word block shrink-0 overflow-hidden pb-[.08em] -mb-[.08em]">
                            <span className="df-mi" style={{ '--i': i }}>
                              <span className="inline-flex items-center gap-4 text-[length:clamp(36px,min(5vw,8.6vh),80px)] font-bold leading-[1.02] tracking-[-0.02em] [font-stretch:78%]">
                                {link.label}
                                {isCurrent ? <span aria-hidden="true" className="w-3 h-3 sm:w-4 sm:h-4 bg-black rounded-full" /> : null}
                              </span>
                            </span>
                          </span>
                          <span className="df-menu-arrow ml-auto min-w-0 hidden xl:flex items-center gap-3 text-[15px] font-semibold whitespace-nowrap">
                            {link.desc}
                            <svg aria-hidden="true" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="square"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
                          </span>
                        </NavLink>
                      </li>
                    );
                  })}
                </ul>
              </nav>
            ) : (
              <section aria-labelledby="df-settings-title" className="flex flex-col">
                <div className="df-mrow flex flex-wrap items-end justify-between gap-4 pb-6" style={{ '--i': 0 }}>
                  <h2 id="df-settings-title" className="text-[length:clamp(40px,6vw,88px)] font-bold leading-none tracking-[-0.02em] [font-stretch:78%]">Settings</h2>
                  <button type="button" tabIndex={tab} data-view-focus onClick={() => switchTo('main')} className="group h-11 flex items-center gap-2 text-[15px] font-bold">
                    <span aria-hidden="true" className="transition-transform duration-500 group-hover:-translate-x-1">←</span>
                    <span className="df-link">Back to menu</span>
                  </button>
                </div>

                <SettingRow i={1} label="Appearance" hint="Also on the moon and sun button at the top.">
                  <div role="radiogroup" aria-label="Theme" className="flex">
                    {['light', 'dark'].map((t) => (
                      <button
                        key={t}
                        type="button"
                        role="radio"
                        tabIndex={tab}
                        aria-checked={theme === t}
                        onClick={() => chooseTheme(t)}
                        className={`h-12 px-6 border-2 border-white -ml-[2px] first:ml-0 text-sm font-extrabold capitalize transition-colors duration-300 ${theme === t ? 'bg-white text-black' : 'text-white hover:bg-white/10'}`}
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                </SettingRow>

                <SettingRow i={2} label="Assistant’s name" hint="Shown in Chat. Your assistant answers to this name.">
                  {signedIn ? (
                    <>
                      <div className="flex max-w-[520px]">
                        <label htmlFor="df-bot-name" className="sr-only">Assistant’s name</label>
                        <input
                          id="df-bot-name"
                          type="text"
                          maxLength={24}
                          tabIndex={tab}
                          value={draft}
                          onChange={(e) => { setDraft(e.target.value); setSaveState('idle'); }}
                          onKeyDown={(e) => { if (e.key === 'Enter') saveName(); }}
                          placeholder="e.g. Ustaad"
                          className="flex-1 min-w-0 h-12 px-4 bg-white text-black text-base font-bold outline-none focus:outline focus:outline-2 focus:outline-black"
                        />
                        <button
                          type="button"
                          tabIndex={tab}
                          onClick={saveName}
                          disabled={unchanged && saveState !== 'saved'}
                          className="df-btn h-12 px-5 bg-black text-white hover:text-black disabled:opacity-60"
                          style={{ '--df-fill': '#FFF' }}
                        >
                          {saveState === 'saving' ? <Spinner className="w-4 h-4" light /> : null}
                          {saveState === 'saved' ? 'Saved ✓' : 'Save'}
                        </button>
                      </div>
                      {saveState === 'error' ? <span role="alert" className="text-sm font-bold">Couldn’t save. Check your connection and try again.</span> : null}
                    </>
                  ) : (
                    <div className="flex flex-wrap items-center gap-3">
                      <span className="text-[15px] text-white/85">Sign in to name your assistant.</span>
                      <GoogleButton tabIndex={tab} />
                    </div>
                  )}
                </SettingRow>

                <SettingRow i={3} label="Account" hint={signedIn ? 'Signed in with Google.' : 'Keeps your garage and chats on every device.'}>
                  {signedIn ? (
                    <div className="flex flex-wrap items-center gap-4">
                      <span className="font-mono text-sm break-all">{user.email}</span>
                      {confirmingOut ? (
                        <span className="flex flex-wrap items-center gap-2 animate-df-fade-up">
                          <strong className="text-[15px] mr-1">Sign out?</strong>
                          <button type="button" tabIndex={tab} onClick={onLogout} className="df-btn h-11 px-4 bg-black text-white hover:text-black" style={{ '--df-fill': '#FFF' }}>Sign out</button>
                          <button type="button" tabIndex={tab} onClick={() => setConfirmingOut(false)} className="h-11 px-4 border-2 border-white text-sm font-extrabold hover:bg-white hover:text-black transition-colors">Stay</button>
                        </span>
                      ) : (
                        <button type="button" tabIndex={tab} onClick={() => setConfirmingOut(true)} className="h-11 px-4 border-2 border-white text-sm font-extrabold hover:bg-white hover:text-black transition-colors">Sign out</button>
                      )}
                    </div>
                  ) : (
                    <div><GoogleButton tabIndex={tab} /></div>
                  )}
                </SettingRow>

                <SettingRow i={4} label="Privacy" hint="What we store and why.">
                  <div className="flex flex-wrap gap-x-6 gap-y-2 text-[15px] font-semibold">
                    <Link to="/privacy" tabIndex={tab} onClick={closeIfHere('/privacy')} className="df-link">Read the privacy policy</Link>
                    <span className="text-white/75">Garage notes and stages stay in this browser.</span>
                  </div>
                </SettingRow>
              </section>
            )}
          </div>

          {/* ── Right: your account ── */}
          <aside aria-label="Your account" className="df-mfade flex flex-col gap-6 lg:pt-3">
            <span className="font-mono text-[13px] font-semibold tracking-[0.1em] text-white/75">YOUR ACCOUNT</span>
            {signedIn ? (
              <>
                <div className="flex items-center gap-4">
                  <Avatar user={user} />
                  <div className="flex flex-col min-w-0">
                    <strong className="text-xl leading-tight truncate">{user.name}</strong>
                    <span className="font-mono text-[12.5px] text-white/80 truncate">{user.email}</span>
                  </div>
                </div>
                <ul className="flex flex-col border-t border-white/30">
                  {[
                    { to: '/saved', label: 'Saved cars' },
                    { to: '/chat', label: 'Chat history' },
                  ].map((l) => (
                    <li key={l.to}>
                      <Link to={l.to} tabIndex={tab} onClick={closeIfHere(l.to)} className="group flex items-center justify-between min-h-[56px] border-b border-white/30 text-[17px] font-bold">
                        <span className="df-link">{l.label}</span>
                        <span aria-hidden="true" className="transition-transform duration-500 group-hover:translate-x-1">→</span>
                      </Link>
                    </li>
                  ))}
                  <li>
                    <button
                      type="button"
                      tabIndex={tab}
                      aria-pressed={view === 'settings'}
                      onClick={() => switchTo(view === 'settings' ? 'main' : 'settings')}
                      className="group w-full flex items-center justify-between min-h-[56px] border-b border-white/30 text-[17px] font-bold text-left"
                    >
                      <span className="flex items-center gap-3">
                        <GearIcon />
                        <span className="df-link" aria-current={view === 'settings' ? 'page' : undefined}>Settings</span>
                      </span>
                      <span aria-hidden="true" className="transition-transform duration-500 group-hover:translate-x-1">{view === 'settings' ? '←' : '→'}</span>
                    </button>
                  </li>
                </ul>
              </>
            ) : (
              <>
                <p className="text-[22px] leading-snug font-semibold max-w-[380px]">Sign in to keep your garage, your chats and your assistant’s name on every device.</p>
                <div><GoogleButton tabIndex={tab} /></div>
                <button
                  type="button"
                  tabIndex={tab}
                  aria-pressed={view === 'settings'}
                  onClick={() => switchTo(view === 'settings' ? 'main' : 'settings')}
                  className="group self-start flex items-center gap-3 min-h-[44px] text-[17px] font-bold"
                >
                  <GearIcon />
                  <span className="df-link" aria-current={view === 'settings' ? 'page' : undefined}>Settings</span>
                  <span aria-hidden="true" className="transition-transform duration-500 group-hover:translate-x-1">{view === 'settings' ? '←' : '→'}</span>
                </button>
              </>
            )}
          </aside>
        </div>

        <div className="df-mfade px-4 sm:px-6 lg:px-10 py-6 sm:py-8 flex flex-wrap items-end justify-between gap-6 border-t border-white/20">
          <Link to="/about#contact" tabIndex={tab} onClick={closeIfHere('/about')} className="group flex flex-col gap-1">
            <span className="font-mono text-[13px] font-semibold tracking-[0.08em] text-white/75">FEEDBACK, BUGS, IDEAS</span>
            <span className="df-link text-[length:clamp(26px,3.2vw,40px)] font-bold leading-tight [font-stretch:80%] self-start">Write to us →</span>
          </Link>
          <span className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-white/80">
            <Link to="/privacy" tabIndex={tab} onClick={closeIfHere('/privacy')} className="df-link">Privacy</Link>
            <span>© {new Date().getFullYear()} DriveFetch</span>
          </span>
        </div>
      </div>
    </div>
  );
}

function GearIcon() {
  return (
    <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="transition-transform duration-700 group-hover:rotate-90">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
    </svg>
  );
}
