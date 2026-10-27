import { useState, useRef, useEffect, useCallback } from 'react';
import { useOutletContext } from 'react-router-dom';
import SEO from '../components/SEO';
import { chatSchema } from '../config/seoSchemas';
import { Spinner, TypingDots } from '../components/ui/Loaders';

/* ── API layer (unchanged endpoints) ── */
async function fetchSessions() {
  const res = await fetch('/api/chat/sessions', { credentials: 'include' });
  if (!res.ok) throw new Error('Failed to fetch sessions');
  return res.json();
}

async function fetchSessionHistory(sessionId) {
  const res = await fetch(`/api/chat/history/${sessionId}`, { credentials: 'include' });
  if (!res.ok) throw new Error('Failed to fetch history');
  return res.json();
}

const MAX_HISTORY_MESSAGES = 20;
const MAX_INPUT = 200;

async function sendMessage(message, sessionId, guestHistory = []) {
  const trimmedHistory = guestHistory.filter((m) => !m.error && !m.greeting).slice(-MAX_HISTORY_MESSAGES);
  const res = await fetch('/api/chat', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      session_id: sessionId,
      guest_history: trimmedHistory.map((m) => ({ role: m.role, content: m.content })),
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Chat service unavailable.');
  }
  return res.json();
}

async function deleteSession(sessionId) {
  const res = await fetch(`/api/chat/${sessionId}`, { method: 'DELETE', credentials: 'include' });
  if (!res.ok) throw new Error('Failed to delete session');
  return res.json();
}

const STARTERS = [
  'Is a 2016 Aqua a good buy?',
  'What does “showered” mean in an ad?',
  'Real fuel average of a Cultus AGS?',
  'How much is transfer for a 2019 Civic in Punjab?',
];

const QUICK = ['Token tax for 1300cc in Punjab?', 'How do I check an auction sheet?', 'Best automatic under 30 lac?'];

export default function ChatPage() {
  const outlet = useOutletContext() || {};
  const user = outlet.user;
  const agentName = outlet.assistantName || 'DriveFetch AI';
  const setAgentName = outlet.setAssistantName || (() => {});
  const saveAssistantName = outlet.saveAssistantName;
  const openSignIn = outlet.openSignIn || (() => {});

  const [sessionsList, setSessionsList] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const activeSessionIdRef = useRef(null);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([]);
  const [isGuest, setIsGuest] = useState(true);
  const [isTyping, setIsTyping] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState(agentName);
  const [nameError, setNameError] = useState('');
  const [nudgeDismissed, setNudgeDismissed] = useState(false);
  const chatEndRef = useRef(null);
  const inputRef = useRef(null);

  const setSession = (id) => {
    activeSessionIdRef.current = id;
    setActiveSessionId(id);
  };

  const greeting = useCallback((name) => ({
    role: 'assistant',
    greeting: true,
    content: `Asalam o Alaikum! ${name} here. Which car are you looking to buy or inspect today?`,
  }), []);

  const startNewChat = useCallback(() => {
    setSession(null);
    setIsSidebarOpen(false);
    setMessages([greeting(agentName)]);
    setTimeout(() => inputRef.current?.focus(), 0);
  }, [agentName, greeting]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, isTyping]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const data = await fetchSessions();
      if (cancelled) return;
      setIsGuest(data.is_guest);
      if (!data.is_guest) {
        setSessionsList(data.sessions || []);
        if (data.sessions && data.sessions.length > 0) {
          try {
            const hist = await fetchSessionHistory(data.sessions[0].session_id);
            if (cancelled) return;
            if (hist.agent_name) setAgentName(hist.agent_name);
            setMessages(hist.messages.map((m) => ({ role: m.role, content: m.content })));
            setSession(data.sessions[0].session_id);
            return;
          } catch { /* fall through to a new chat */ }
        }
      }
      startNewChat();
    };
    (async () => {
      try {
        await load();
      } catch {
        // Render's free tier can be asleep: retry once after a short wait.
        await new Promise((r) => setTimeout(r, 4000));
        if (cancelled) return;
        try { await load(); } catch { if (!cancelled) startNewChat(); }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadSession = async (sessionId) => {
    setIsLoading(true);
    setIsSidebarOpen(false);
    setConfirmDelete(null);
    try {
      const data = await fetchSessionHistory(sessionId);
      if (data.agent_name) setAgentName(data.agent_name);
      setMessages(data.messages.map((m) => ({ role: m.role, content: m.content })));
      setSession(sessionId);
    } catch (err) {
      console.error('Request failed:', err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setIsLoading(false);
    }
  };

  const send = async (text) => {
    const query = String(text || '').trim().slice(0, MAX_INPUT);
    if (!query || isTyping) return;
    const history = messages;
    setMessages((prev) => [...prev, { role: 'user', content: query }]);
    setInput('');
    setIsTyping(true);
    try {
      const data = await sendMessage(query, activeSessionIdRef.current, history);
      if (data.session_id && !activeSessionIdRef.current) setSession(data.session_id);
      setMessages((prev) => [...prev, { role: 'assistant', content: data.content }]);
      if (data.agent_name) setAgentName(data.agent_name);
      if (!isGuest) {
        const sessionsData = await fetchSessions();
        setSessionsList(sessionsData.sessions || []);
      }
    } catch (err) {
      const errMsg = err instanceof Error && err.message ? err.message : 'The chat service is temporarily unavailable.';
      setMessages((prev) => [...prev, { role: 'assistant', content: errMsg, error: true }]);
    } finally {
      setIsTyping(false);
      inputRef.current?.focus();
    }
  };

  const handleSend = (e) => {
    e.preventDefault();
    send(input);
  };

  const handleDeleteSession = async (sessionId) => {
    try {
      await deleteSession(sessionId);
      setSessionsList((prev) => prev.filter((s) => s.session_id !== sessionId));
      if (activeSessionIdRef.current === sessionId) startNewChat();
    } catch {
      setMessages((prev) => [...prev, { role: 'assistant', content: 'Couldn’t delete that chat. Try again.', error: true }]);
    } finally {
      setConfirmDelete(null);
    }
  };

  const saveName = async () => {
    setNameError('');
    if (!saveAssistantName) { setEditingName(false); return; }
    try {
      await saveAssistantName(nameDraft);
      setEditingName(false);
    } catch {
      setNameError('Couldn’t save. Try again.');
    }
  };

  const userMessages = messages.filter((m) => m.role === 'user').length;
  const showStarters = !isLoading && userMessages === 0 && !isTyping;
  const showNudge = isGuest && !nudgeDismissed && userMessages >= 2;
  const initial = (agentName || 'D').trim().charAt(0).toUpperCase();

  return (
    <div className="flex h-[calc(100dvh-64px)] sm:h-[calc(100dvh-68px)] w-full overflow-hidden">
      <SEO
        title="Ask DriveFetch AI | Pakistani Car Buying Expert"
        description="Chat with DriveFetch for mechanic tips, real-world fuel averages, auction sheet checks and Pakistan excise transfer rules."
        path="/chat"
        keywords={['car advice Pakistan', 'auction sheet check', 'car inspection AI Pakistan']}
        schema={chatSchema}
      />

      {/* ═══ HISTORY SIDEBAR (signed in) ═══ */}
      {!isGuest && isSidebarOpen && (
        <button type="button" aria-label="Close chat history" onClick={() => setIsSidebarOpen(false)} className="md:hidden fixed inset-0 z-30 bg-black/50" />
      )}
      {!isGuest && (
        <aside
          aria-label="Chat history"
          className={`fixed md:static top-16 sm:top-[68px] bottom-0 left-0 z-40 w-[280px] shrink-0 flex flex-col bg-df-grey dark:bg-black border-r border-neutral-200 dark:border-zinc-800 transition-transform duration-200 ${
            isSidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
          }`}
        >
          <div className="p-3.5">
            <button type="button" onClick={startNewChat} className="w-full h-12 bg-df-red text-white text-[15px] font-extrabold tracking-[0.04em] hover:bg-black dark:hover:bg-zinc-50 dark:hover:text-black transition-colors">
              + NEW CHAT
            </button>
          </div>
          <span className="px-4 pb-2 font-mono text-[11.5px] font-semibold df-muted">HISTORY</span>
          <div className="flex-1 overflow-y-auto flex flex-col">
            {sessionsList.length === 0 ? (
              <p className="px-4 py-3 text-sm df-muted">Your chats will show up here.</p>
            ) : sessionsList.map((session) => {
              const active = activeSessionId === session.session_id;
              return (
                <div key={session.session_id} className={`flex items-stretch border-l-4 ${active ? 'border-df-red bg-white dark:bg-df-night' : 'border-transparent'}`}>
                  {confirmDelete === session.session_id ? (
                    <div className="flex-1 flex items-center gap-1.5 px-3 py-2 text-[13px] font-bold">
                      <span className="flex-1">Delete this chat?</span>
                      <button type="button" onClick={() => handleDeleteSession(session.session_id)} className="h-9 px-2.5 bg-df-red text-white font-extrabold">Delete</button>
                      <button type="button" onClick={() => setConfirmDelete(null)} className="h-9 px-2 border border-black dark:border-zinc-700">Keep</button>
                    </div>
                  ) : (
                    <>
                      <button
                        type="button"
                        onClick={() => loadSession(session.session_id)}
                        aria-current={active ? 'true' : undefined}
                        className="flex-1 min-w-0 text-left px-3 py-3 hover:text-df-red"
                      >
                        <span className="block text-sm font-bold truncate">{session.latest_message || 'Untitled chat'}</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirmDelete(session.session_id)}
                        aria-label={`Delete chat: ${session.latest_message || 'Untitled chat'}`}
                        className="w-11 flex items-center justify-center df-muted hover:text-df-red"
                      >
                        <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" /></svg>
                      </button>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </aside>
      )}

      {/* ═══ MAIN ═══ */}
      <section className="flex-1 min-w-0 flex flex-col">
        <div className="shrink-0 flex items-center gap-3 px-4 sm:px-6 py-3 border-b border-neutral-200 dark:border-zinc-800">
          {!isGuest && (
            <button type="button" onClick={() => setIsSidebarOpen(true)} aria-label="Open chat history" className="md:hidden w-11 h-11 flex items-center justify-center border border-black dark:border-zinc-700">
              <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="square"><path d="M3 6h18M3 12h18M3 18h12" /></svg>
            </button>
          )}
          <span aria-hidden="true" className="w-9 h-9 bg-df-red text-white flex items-center justify-center font-black [font-stretch:70%] text-lg">{initial}</span>
          {editingName ? (
            <div className="flex items-center gap-2 flex-wrap">
              <label htmlFor="bot-name" className="sr-only">Assistant name</label>
              <input
                id="bot-name"
                type="text"
                maxLength={24}
                value={nameDraft}
                autoFocus
                onChange={(e) => setNameDraft(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') saveName(); if (e.key === 'Escape') setEditingName(false); }}
                className="h-10 w-48 px-2.5 border-2 border-df-red bg-transparent font-extrabold outline-none"
              />
              <button type="button" onClick={saveName} className="h-10 px-3 bg-black text-white dark:bg-zinc-50 dark:text-black text-[13px] font-extrabold">Save</button>
              <button type="button" onClick={() => setEditingName(false)} className="h-10 px-2 text-[13px] font-bold underline">Cancel</button>
              {nameError ? <span role="alert" className="text-[13px] font-bold">{nameError}</span> : null}
            </div>
          ) : (
            <button
              type="button"
              onClick={() => { if (isGuest) { openSignIn('chat'); return; } setNameDraft(agentName); setEditingName(true); }}
              title={isGuest ? 'Sign in to rename your assistant' : 'Rename your assistant'}
              className="flex items-center gap-2 h-10 text-lg font-black uppercase truncate hover:text-df-red"
            >
              {agentName}
              <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="df-muted"><path d="M4 20h4L19 9l-4-4L4 16z" /></svg>
            </button>
          )}
          <span className="ml-auto flex items-center gap-1.5 text-xs font-extrabold tracking-[0.08em]">
            <span aria-hidden="true" className="w-2 h-2 bg-df-red animate-df-pulse" />ONLINE
          </span>
        </div>

        <div aria-live="polite" className="flex-1 min-h-0 overflow-y-auto overscroll-contain">
          <div className="w-full max-w-[880px] mx-auto px-4 sm:px-8 py-6 sm:py-8 flex flex-col gap-5">
            {isLoading ? (
              <div className="flex flex-col items-center justify-center gap-3 py-24 df-muted">
                <Spinner className="w-6 h-6" />
                <span className="text-sm font-bold">Loading your chats…</span>
              </div>
            ) : (
              <>
                {showStarters && (
                  <div className="flex flex-col gap-6 pt-2 pb-4 animate-df-fade-up">
                    <h1 className="df-display text-[length:clamp(52px,7vw,112px)]">Ask<br /><span className="text-df-red">{isGuest ? 'DriveFetch.' : `${agentName.split(' ')[0]}.`}</span></h1>
                    <p className="text-lg leading-relaxed df-muted max-w-[560px]">Mechanic tips, real fuel averages, auction sheets, excise and transfer rules. Ask it like you’d ask your ustaad.</p>
                    <div className="flex flex-col border-t-2 border-black dark:border-zinc-50">
                      {STARTERS.map((s, i) => (
                        <button key={s} type="button" onClick={() => send(s)} className="grid grid-cols-[44px_minmax(0,1fr)_28px] items-center gap-3 min-h-[64px] border-b border-neutral-200 dark:border-zinc-800 text-left hover:text-df-red">
                          <span className="font-mono text-sm font-semibold text-df-red-dark dark:text-zinc-400">0{i + 1}</span>
                          <span className="text-lg font-bold">{s}</span>
                          <span aria-hidden="true" className="text-xl">→</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {messages.length > MAX_HISTORY_MESSAGES && (
                  <span className="self-center text-xs df-muted">Older messages are kept, but only the most recent ones are sent as context.</span>
                )}

                {messages.filter((m) => !(showStarters && m.greeting)).map((msg, idx) => {
                  const mine = msg.role === 'user';
                  return (
                    <div key={idx} className={`flex flex-col gap-1.5 max-w-[88%] sm:max-w-[76%] animate-df-fade-up ${mine ? 'self-end items-end' : 'self-start items-start'}`}>
                      <span className={`text-[11.5px] font-extrabold tracking-[0.06em] ${mine ? 'df-muted' : msg.error ? '' : 'text-df-red-dark dark:text-zinc-300'}`}>
                        {mine ? 'YOU' : msg.error ? 'COULDN’T ANSWER' : agentName.toUpperCase()}
                      </span>
                      <div
                        className={`px-4 sm:px-5 py-3.5 text-[15px] sm:text-base leading-relaxed whitespace-pre-wrap break-words ${
                          mine
                            ? 'bg-black text-white dark:bg-zinc-50 dark:text-black'
                            : msg.error
                              ? 'border-2 border-df-red'
                              : 'bg-df-grey dark:bg-zinc-900 border border-neutral-200 dark:border-zinc-800'
                        }`}
                      >
                        {msg.content}
                      </div>
                    </div>
                  );
                })}

                {isTyping && (
                  <div className="self-start px-5 py-4 bg-df-grey dark:bg-zinc-900 border border-neutral-200 dark:border-zinc-800">
                    <TypingDots label={`${agentName} is typing`} />
                  </div>
                )}

                {showNudge && (
                  <div className="flex flex-wrap items-center gap-3 p-4 bg-df-red text-white animate-df-fade-up">
                    <strong className="flex-1 min-w-[220px]">Guest chats disappear when you close the tab.</strong>
                    <button type="button" onClick={() => openSignIn('chat')} className="h-11 px-4 bg-black text-white text-sm font-extrabold">Sign in to keep it</button>
                    <button type="button" onClick={() => setNudgeDismissed(true)} aria-label="Dismiss" className="w-11 h-11 text-2xl leading-none">×</button>
                  </div>
                )}
              </>
            )}
            <div ref={chatEndRef} />
          </div>
        </div>

        <div className="shrink-0 border-t border-neutral-200 dark:border-zinc-800 px-4 sm:px-8 pt-3 pb-4">
          <div className="w-full max-w-[880px] mx-auto flex flex-col gap-2.5">
            {!showStarters && !isTyping && !isLoading && (
              <div className="flex gap-1.5 overflow-x-auto df-no-scrollbar">
                {QUICK.map((q) => (
                  <button key={q} type="button" onClick={() => send(q)} className="shrink-0 h-9 px-3 border border-black dark:border-zinc-700 text-[13px] font-semibold hover:bg-black hover:text-white dark:hover:bg-zinc-50 dark:hover:text-black">{q}</button>
                ))}
              </div>
            )}
            <form onSubmit={handleSend} className="flex border-2 border-black dark:border-zinc-50 bg-white dark:bg-black">
              <label htmlFor="chat-input" className="sr-only">Message</label>
              <input
                id="chat-input"
                ref={inputRef}
                type="text"
                maxLength={MAX_INPUT}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask about fuel averages, auction sheets, transfer rules…"
                disabled={isTyping || isLoading}
                autoComplete="off"
                className="flex-1 min-w-0 h-14 px-4 sm:px-5 bg-transparent text-base outline-none placeholder:text-neutral-500 disabled:opacity-50"
              />
              <span className={`self-center px-2 font-mono text-xs ${input.length > 180 ? 'text-df-red-dark dark:text-zinc-50 font-bold' : 'df-muted'}`}>{input.length}/{MAX_INPUT}</span>
              <button
                type="submit"
                aria-label="Send message"
                disabled={isTyping || isLoading || !input.trim()}
                className="w-16 bg-df-red text-white flex items-center justify-center hover:bg-black disabled:opacity-40 disabled:hover:bg-df-red"
              >
                <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
              </button>
            </form>
            <div className="flex justify-between text-xs df-muted">
              <span>{isGuest ? 'Guest mode · not saved' : `Signed in as ${user?.name?.split(' ')[0] || 'you'} · saved to your history`}</span>
              <span>Press Enter to send</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
