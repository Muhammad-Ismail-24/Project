import React, { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, User, Loader2, Trash2, Plus, MessageSquare } from 'lucide-react';
import { useOutletContext } from 'react-router-dom';
import SEO from '../components/SEO';
import { chatSchema } from '../config/seoSchemas';

/* ── Typing Indicator ── */
function TypingDots() {
  return (
    <span className="flex items-center gap-[6px]" aria-label="Typing">
      <span className="w-2 h-2 bg-df-black/40 animate-bounce [animation-delay:0ms]" />
      <span className="w-2 h-2 bg-df-black/40 animate-bounce [animation-delay:160ms]" />
      <span className="w-2 h-2 bg-df-black/40 animate-bounce [animation-delay:320ms]" />
    </span>
  );
}


/* ── API Layer ── */
const API_BASE = '';

async function fetchSessions() {
  const res = await fetch(`${API_BASE}/api/chat/sessions`, { credentials: 'include' });
  if (!res.ok) throw new Error('Failed to fetch sessions');
  return res.json();
}

async function fetchSessionHistory(sessionId) {
  const res = await fetch(`${API_BASE}/api/chat/history/${sessionId}`, { credentials: 'include' });
  if (!res.ok) throw new Error('Failed to fetch history');
  return res.json();
}

const MAX_HISTORY_MESSAGES = 20;

async function sendMessage(message, sessionId, guestHistory = []) {
  const trimmedHistory = guestHistory.slice(-MAX_HISTORY_MESSAGES);
  
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      session_id: sessionId,
      guest_history: trimmedHistory.map(m => ({ role: m.role, content: m.content })),
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Chat service unavailable.');
  }
  return res.json();
}

async function deleteSession(sessionId) {
  const res = await fetch(`${API_BASE}/api/chat/${sessionId}`, {
    method: 'DELETE',
    credentials: 'include',
  });
  if (!res.ok) throw new Error('Failed to delete session');
  return res.json();
}

/* ════════════════════════════════════════════════════════════
   CHAT PAGE — Premium Neo-Brutalist Terminal
   ════════════════════════════════════════════════════════════ */
export default function ChatPage() {
  const [sessionsList, setSessionsList] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const activeSessionIdRef = useRef(null);

  const setSession = (id) => {
    activeSessionIdRef.current = id;
    setActiveSessionId(id);
  };

  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([]);
  const outletContext = useOutletContext() || {};
  const user = outletContext.user;
  const agentName = outletContext.assistantName || 'DriveFetch AI';
  const setAgentName = outletContext.setAssistantName || (() => {});
  const [isGuest, setIsGuest] = useState(true);
  const [isTyping, setIsTyping] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const chatEndRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  useEffect(() => {
    (async () => {
      try {
        const data = await fetchSessions();
        setIsGuest(data.is_guest);
        if (!data.is_guest) {
          setSessionsList(data.sessions || []);
          if (data.sessions && data.sessions.length > 0) {
            try {
              const hist = await fetchSessionHistory(data.sessions[0].session_id);
              if (hist.agent_name) setAgentName(hist.agent_name);
              setMessages(hist.messages.map(m => ({ role: m.role, content: m.content })));
              setSession(data.sessions[0].session_id);
            } catch { startNewChat(); }
          } else { startNewChat(); }
        } else { startNewChat(); }
      } catch (err) {
        setTimeout(async () => {
          try {
            const data = await fetchSessions();
            setIsGuest(data.is_guest);
            if (!data.is_guest) {
              setSessionsList(data.sessions || []);
              if (data.sessions && data.sessions.length > 0) {
                const hist = await fetchSessionHistory(data.sessions[0].session_id);
                if (hist.agent_name) setAgentName(hist.agent_name);
                setMessages(hist.messages.map(m => ({ role: m.role, content: m.content })));
                setSession(data.sessions[0].session_id);
              } else { startNewChat(); }
            } else { startNewChat(); }
          } catch { startNewChat(); }
          finally { setIsLoading(false); }
        }, 4000);
        return;
      } finally { setIsLoading(false); }
    })();
  }, []);

  const loadSession = async (sessionId) => {
    setIsLoading(true);
    setIsMobileSidebarOpen(false);
    try {
      const data = await fetchSessionHistory(sessionId);
      if (data.agent_name) setAgentName(data.agent_name);
      setMessages(data.messages.map(m => ({ role: m.role, content: m.content })));
      setSession(sessionId);
    } catch (err) { console.error(err); }
    finally { setIsLoading(false); }
  };

  const startNewChat = () => {
    setSession(null);
    setIsMobileSidebarOpen(false);
    setMessages([{
      role: 'assistant',
      content: `Asalam o Alaikum! ${agentName} here. Which car are you looking to buy or inspect today?`,
    }]);
  };

  const handleSend = async (e) => {
    e.preventDefault();
    const query = input.trim();
    if (!query || isTyping) return;
    setMessages(prev => [...prev, { role: 'user', content: query }]);
    setInput('');
    setIsTyping(true);
    try {
      const data = await sendMessage(query, activeSessionIdRef.current, messages);
      if (data.session_id && !activeSessionIdRef.current) setSession(data.session_id);
      setMessages(prev => [...prev, { role: 'assistant', content: data.content }]);
      if (data.agent_name) setAgentName(data.agent_name);
      if (!isGuest) {
        const sessionsData = await fetchSessions();
        setSessionsList(sessionsData.sessions || []);
      }
    } catch (err) {
      const errMsg = err.message || 'Automotive chat service is temporarily unavailable.';
      setMessages(prev => [...prev, { role: 'assistant', content: `⚠️ ${errMsg}` }]);
    } finally { setIsTyping(false); }
  };

  const handleDeleteSession = async (e, sessionId) => {
    e.stopPropagation();
    if (!window.confirm('Delete this chat?')) return;
    try {
      await deleteSession(sessionId);
      setSessionsList(prev => prev.filter(s => s.session_id !== sessionId));
      if (activeSessionIdRef.current === sessionId) startNewChat();
    } catch { alert('Failed to delete chat.'); }
  };

  /* ═══════════════════════════════════════════
     RENDER — Premium Viewport-Locked Terminal
     ═══════════════════════════════════════════ */
  return (
    <main
      className="flex h-[calc(100dvh-64px)] sm:h-[calc(100dvh-72px)] w-full overflow-hidden font-body text-df-black dark:text-zinc-50 dark:bg-black"
    >
      <SEO
        title="Ask DriveFetch AI | 24/7 Pakistani Automotive Expert & Valuation"
        description="Chat with DriveFetch Expert for ustaad mechanic advice, real-world fuel averages, JDM auction sheet checks, and Pakistan Excise transfer policies."
        path="/chat"
        keywords={['car advice Pakistan', 'auction sheet check', 'car inspection AI Pakistan']}
        schema={chatSchema}
      />

      {/* ── Mobile sidebar backdrop ── */}
      {isMobileSidebarOpen && !isGuest && (
        <div
          onClick={() => setIsMobileSidebarOpen(false)}
          className="fixed inset-0 z-30 bg-df-black/30 md:hidden"
        />
      )}

      {/* ═══ SIDEBAR — Session History ═══ */}
      {!isGuest && (
        <div className={`
          fixed top-16 sm:top-[72px] bottom-0 left-0 z-40 w-64 flex flex-col flex-shrink-0
          border-r-2 border-df-black bg-df-grey dark:border-white dark:bg-zinc-900
          transition-transform duration-200 ease-out
          md:static md:translate-x-0
          ${isMobileSidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        `}>
          {/* New Chat Button — with hard shadow + press state */}
          <div className="p-3 border-b-2 border-df-black">
            <button
              onClick={startNewChat}
              className="w-full flex items-center justify-center gap-2 bg-df-black text-df-white font-mono text-xs font-bold tracking-[0.06em] py-2.5 border-2 border-df-black shadow-[3px_3px_0px_#000000] hover:bg-df-white hover:text-df-black active:translate-x-[2px] active:translate-y-[2px] active:shadow-none transition-none dark:border-white dark:bg-zinc-800 dark:hover:bg-white dark:hover:text-black"
            >
              <Plus className="w-4 h-4" strokeWidth={2.5} />
              NEW CHAT
            </button>
          </div>

          {/* Session List */}
          <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
            <p className="font-mono text-[10px] font-bold text-df-black/35 dark:text-zinc-50/50 uppercase tracking-[0.12em] px-2 pt-3 pb-2 select-none">
              [ HISTORY ]
            </p>
            {sessionsList.map(session => (
              <div
                key={session.session_id}
                onClick={() => {
                  loadSession(session.session_id).catch(err => console.error('Failed to load session:', err));
                }}
                className={`group flex items-center justify-between px-3 py-2.5 cursor-pointer border-2 transition-none
                  ${activeSessionId === session.session_id
                    ? 'bg-df-red text-df-white border-df-black shadow-[3px_3px_0px_#000000] dark:border-white'
                    : 'bg-df-white text-df-black border-df-black/15 hover:border-df-black hover:bg-df-black hover:text-df-white dark:bg-black dark:text-zinc-50 dark:border-zinc-700 dark:hover:border-white dark:hover:bg-zinc-800'
                  }`}
              >
                <div className="flex items-center gap-2 overflow-hidden min-w-0">
                  <MessageSquare
                    className="w-3.5 h-3.5 shrink-0"
                    strokeWidth={2}
                  />
                  <span className="text-xs font-mono font-medium truncate">
                    {session.latest_message}
                  </span>
                </div>
                <button
                  onClick={(e) => {
                    handleDeleteSession(e, session.session_id).catch(err => console.error('Failed to delete session:', err));
                  }}
                  aria-label="Delete this chat session"
                  title="Delete chat"
                  className={`p-1 shrink-0 transition-none
                    ${activeSessionId === session.session_id
                      ? 'opacity-70 hover:opacity-100 text-df-white'
                      : 'opacity-0 group-hover:opacity-60 group-hover:hover:opacity-100 text-df-white'
                    }`}
                >
                  <Trash2 className="w-3.5 h-3.5" strokeWidth={2} />
                </button>
              </div>
            ))}
          </div>

          {/* Sidebar footer tag */}
          <div className="border-t-2 border-df-black px-3 py-2.5 bg-df-white/50 dark:border-white dark:bg-black">
            <p className="font-mono text-[9px] font-bold text-df-black/20 dark:text-zinc-50/50 tracking-[0.08em] uppercase select-none">
              SYS::CHAT_V2.1_BRUTALIST
            </p>
          </div>
        </div>
      )}

      {/* ═══ MAIN CHAT AREA ═══ */}
      <div className="flex-1 flex flex-col min-w-0">

        {/* ── Chat Header Bar — with subtle bottom shadow ── */}
        <div className="flex items-center justify-between px-4 sm:px-6 py-3 border-b-2 border-df-black bg-df-white flex-shrink-0 relative z-10 shadow-[0_2px_0px_rgba(0,0,0,0.04)] dark:border-white dark:bg-black">
          <div className="flex items-center gap-3 min-w-0">
            {/* Mobile sidebar toggle */}
            {!isGuest && (
              <button
                onClick={() => setIsMobileSidebarOpen(!isMobileSidebarOpen)}
                aria-label={isMobileSidebarOpen ? 'Close chat history' : 'Open chat history'}
                aria-expanded={isMobileSidebarOpen}
                className="md:hidden p-1.5 border-2 border-df-black text-df-black shadow-[2px_2px_0px_#000000] hover:bg-df-black hover:text-df-white active:translate-x-[2px] active:translate-y-[2px] active:shadow-none transition-none dark:border-white dark:text-zinc-50 dark:hover:bg-white dark:hover:text-black"
              >
                <MessageSquare className="w-4 h-4" strokeWidth={2} />
              </button>
            )}
            <div className="min-w-0 flex items-center gap-2.5">
              <div className="min-w-0">
                <h1 className="font-mono text-sm font-bold tracking-[0.04em] text-df-black dark:text-zinc-50 truncate uppercase">
                  {user?.bot_name || agentName}
                </h1>
              </div>
            </div>
          </div>

          {/* Status badge — Signal Red */}
          <div className="flex items-center gap-2 shrink-0 border-2 border-df-black px-2.5 py-1 bg-df-white shadow-[2px_2px_0px_#000000] dark:border-white dark:bg-black">
            <span className="w-2 h-2 bg-df-red animate-pulse" />
            <span className="font-mono text-[10px] font-bold text-df-black dark:text-zinc-50 tracking-[0.08em] uppercase">
              LIVE
            </span>
          </div>
        </div>

        {/* ── Message Feed (Scrollable) — Engineering dot-grid canvas ── */}
        <div
          className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6 overscroll-y-contain bg-[radial-gradient(#d1d5db_1px,transparent_1px)] dark:bg-[radial-gradient(#333_1px,transparent_1px)] [background-size:20px_20px]"
        >
          {isLoading ? (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-df-black/40 dark:text-zinc-50/50">
              <Loader2 className="w-5 h-5 animate-spin" strokeWidth={2} />
              <p className="font-mono text-xs font-bold tracking-[0.08em] uppercase">[ LOADING_HISTORY ]</p>
            </div>
          ) : (
            messages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {/* ── AI Message ── */}
                {msg.role === 'assistant' && (
                  <div className="max-w-[88%] md:max-w-[72%] flex gap-3 items-start">
                    {/* AI avatar — black shadow */}
                    <div className="w-9 h-9 bg-df-black border-2 border-df-black shadow-[3px_3px_0px_#000000] flex items-center justify-center flex-shrink-0 mt-0.5 dark:border-white dark:bg-zinc-800">
                      <Sparkles className="w-4 h-4 text-df-white" strokeWidth={2} />
                    </div>
                    {/* AI bubble — white + hard offset shadow */}
                    <div className="bg-df-white border-2 border-df-black shadow-[5px_5px_0px_#000000] px-5 py-4 dark:bg-black dark:border-white">
                      <span className="font-mono text-[10px] font-bold text-df-red tracking-[0.08em] block mb-2 select-none">
                        [ SYSTEM ]:
                      </span>
                      <p className="text-sm sm:text-[15px] leading-relaxed whitespace-pre-wrap break-words font-body text-df-black dark:text-zinc-50">
                        {msg.content}
                      </p>
                    </div>
                  </div>
                )}

                {/* ── User Message ── */}
                {msg.role === 'user' && (
                  <div className="max-w-[88%] md:max-w-[72%] flex gap-3 items-start flex-row-reverse">
                    {/* User avatar */}
                    <div className="w-9 h-9 bg-df-grey border-2 border-df-black shadow-[3px_3px_0px_#000000] flex items-center justify-center flex-shrink-0 mt-0.5 dark:bg-zinc-800 dark:border-white">
                      <User className="w-4 h-4 text-df-black dark:text-zinc-50" strokeWidth={2} />
                    </div>
                    {/* User bubble — solid black, black offset shadow */}
                    <div className="bg-df-black text-df-white border-2 border-df-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] px-5 py-4 dark:bg-zinc-800 dark:border-white">
                      <span className="font-mono text-[10px] font-bold text-df-white/40 tracking-[0.08em] block mb-2 select-none">
                        [ YOU ]:
                      </span>
                      <p className="text-sm sm:text-[15px] leading-relaxed whitespace-pre-wrap break-words font-body font-medium">
                        {msg.content}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            ))
          )}

          {/* Typing indicator */}
          {isTyping && (
            <div className="flex gap-3 justify-start">
              <div className="flex gap-3 items-start">
                <div className="w-9 h-9 bg-df-black border-2 border-df-black shadow-[3px_3px_0px_#000000] flex items-center justify-center flex-shrink-0 mt-0.5 dark:border-white dark:bg-zinc-800">
                  <Sparkles className="w-4 h-4 text-df-white" strokeWidth={2} />
                </div>
                <div className="bg-df-white border-2 border-df-black shadow-[5px_5px_0px_#000000] px-5 py-4 dark:bg-black dark:border-white">
                  <span className="font-mono text-[10px] font-bold text-df-red tracking-[0.08em] block mb-2 select-none">
                    [ SYSTEM ]:
                  </span>
                  <TypingDots />
                </div>
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        {/* ═══ INPUT CONSOLE (Pinned Bottom) ═══ */}
        <div className="flex-shrink-0 border-t-2 border-df-black bg-df-white p-4 sm:p-5 dark:border-white dark:bg-black">
          <div className="max-w-3xl mx-auto">
            {/* Guest notice */}
            {isGuest && !isLoading && (
              <p className="font-mono text-[10px] font-bold text-df-black/35 dark:text-zinc-50/50 tracking-[0.06em] text-center mb-3 uppercase select-none">
                [ SIGN IN TO SAVE CONVERSATIONS ]
              </p>
            )}
            <form onSubmit={handleSend} className="flex items-stretch gap-0">
              {/* Input container — industrial terminal style */}
              <div className="flex-1 border-2 border-df-black bg-df-grey/50 shadow-[3px_3px_0px_#000000] focus-within:shadow-[3px_3px_0px_#E5202E] focus-within:border-df-red transition-none dark:border-white dark:bg-zinc-900">
                <input
                  id="chat-input"
                  type="text"
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  placeholder="> Ask about fuel averages, ground clearance…"
                  disabled={isTyping || isLoading}
                  className="w-full bg-transparent px-5 py-4 outline-none font-mono text-sm text-df-black placeholder-df-black/30 disabled:opacity-40 dark:text-zinc-50 dark:placeholder-zinc-50/30"
                />
              </div>
              {/* Send button — brutalist press-offset physics */}
              <button
                id="chat-send-button"
                type="submit"
                disabled={isTyping || isLoading || !input.trim()}
                className="w-14 bg-df-red text-df-white border-2 border-df-black border-l-0 flex items-center justify-center shadow-[3px_3px_0px_#000000] hover:bg-df-black active:translate-x-[3px] active:translate-y-[3px] active:shadow-none transition-none disabled:opacity-30 disabled:active:translate-x-0 disabled:active:translate-y-0 disabled:active:shadow-[3px_3px_0px_#000000] dark:border-white"
                aria-label="Send message"
              >
                <Send className="w-4 h-4" strokeWidth={2.5} />
              </button>
            </form>
            {messages.length > MAX_HISTORY_MESSAGES && (
              <p className="font-mono text-[9px] font-bold text-df-black/40 dark:text-zinc-50/50 tracking-[0.06em] mt-2 text-center uppercase select-none">
                [ Showing recent conversation context only ]
              </p>
            )}
            <p className="font-mono text-[9px] font-bold text-df-black/15 dark:text-zinc-50/50 tracking-[0.06em] mt-2 text-center select-none">
              DRIVEFETCH_TERMINAL // PRESS ENTER TO SEND
            </p>
          </div>
        </div>

      </div>
    </main>
  );
}
