import React, { useState, useRef, useEffect } from 'react';
import { Helmet } from 'react-helmet-async';
import { Send, Sparkles, User, Loader2, Trash2, Plus, MessageSquare } from 'lucide-react';
import { useOutletContext } from 'react-router-dom';

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

async function sendMessage(message, sessionId, guestHistory = []) {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      session_id: sessionId,
      guest_history: guestHistory.map(m => ({ role: m.role, content: m.content })),
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
   CHAT PAGE — Viewport-Locked Neo-Brutalist Terminal
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
  const { assistantName: agentName, setAssistantName: setAgentName } =
    useOutletContext() || { assistantName: 'DriveFetch Expert', setAssistantName: () => {} };
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
     RENDER — Viewport-Locked Terminal
     ═══════════════════════════════════════════ */
  return (
    <main
      className="flex h-[calc(100vh-64px)] sm:h-[calc(100vh-72px)] w-full overflow-hidden font-body text-df-black"
    >
      <Helmet>
        <title>AI Car Inspection Assistant | DriveFetch</title>
        <meta name="description" content="Chat with our AI Car Inspection Assistant to ask questions about specific car conditions and make an informed buying decision." />
        <link rel="canonical" href="https://carfinderproject.vercel.app/chat" />
      </Helmet>

      {/* ── Mobile sidebar backdrop ── */}
      {isMobileSidebarOpen && !isGuest && (
        <div
          onClick={() => setIsMobileSidebarOpen(false)}
          className="fixed inset-0 z-30 bg-df-black/20 md:hidden"
        />
      )}

      {/* ═══ SIDEBAR — Session History ═══ */}
      {!isGuest && (
        <div className={`
          fixed top-16 sm:top-[72px] bottom-0 left-0 z-40 w-64 flex flex-col flex-shrink-0
          border-r-2 border-df-black bg-df-grey
          transition-transform duration-200 ease-out
          md:static md:translate-x-0
          ${isMobileSidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        `}>
          {/* New Chat Button */}
          <div className="p-3 border-b-2 border-df-black">
            <button
              onClick={startNewChat}
              className="w-full flex items-center justify-center gap-2 bg-df-black text-df-white font-mono text-xs font-bold tracking-[0.06em] py-2.5 border-2 border-df-black hover:bg-df-red hover:border-df-red transition-none"
            >
              <Plus className="w-4 h-4" strokeWidth={2.5} />
              NEW CHAT
            </button>
          </div>

          {/* Session List */}
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            <p className="font-mono text-[10px] font-bold text-df-black/35 uppercase tracking-[0.12em] px-2 pt-3 pb-2 select-none">
              [ HISTORY ]
            </p>
            {sessionsList.map(session => (
              <div
                key={session.session_id}
                onClick={() => loadSession(session.session_id)}
                className={`group flex items-center justify-between px-3 py-2.5 cursor-pointer border-2 transition-none
                  ${activeSessionId === session.session_id
                    ? 'bg-df-black text-df-white border-df-black'
                    : 'bg-df-white text-df-black border-transparent hover:bg-df-black hover:text-df-white hover:border-df-black'
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
                  onClick={(e) => handleDeleteSession(e, session.session_id)}
                  className={`p-1 shrink-0 transition-none
                    ${activeSessionId === session.session_id
                      ? 'opacity-60 hover:opacity-100 text-df-white'
                      : 'opacity-0 group-hover:opacity-60 group-hover:hover:opacity-100 text-df-white'
                    }`}
                >
                  <Trash2 className="w-3.5 h-3.5" strokeWidth={2} />
                </button>
              </div>
            ))}
          </div>

          {/* Sidebar footer tag */}
          <div className="border-t-2 border-df-black px-3 py-2">
            <p className="font-mono text-[9px] font-bold text-df-black/20 tracking-[0.08em] uppercase select-none">
              SYS::CHAT_V2.0
            </p>
          </div>
        </div>
      )}

      {/* ═══ MAIN CHAT AREA ═══ */}
      <div className="flex-1 flex flex-col bg-df-white min-w-0">

        {/* ── Chat Header Bar ── */}
        <div className="flex items-center justify-between px-4 sm:px-6 py-3 border-b-2 border-df-black bg-df-white flex-shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            {/* Mobile sidebar toggle */}
            {!isGuest && (
              <button
                onClick={() => setIsMobileSidebarOpen(!isMobileSidebarOpen)}
                className="md:hidden p-1.5 border-2 border-df-black text-df-black hover:bg-df-black hover:text-df-white transition-none"
              >
                <MessageSquare className="w-4 h-4" strokeWidth={2} />
              </button>
            )}
            <div className="min-w-0 flex items-center gap-2">
              <div className="w-7 h-7 bg-df-black flex items-center justify-center flex-shrink-0">
                <Sparkles className="w-3.5 h-3.5 text-df-white" strokeWidth={2} />
              </div>
              <h1 className="font-mono text-sm font-bold tracking-[0.04em] text-df-black truncate uppercase">
                {agentName}
              </h1>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <span className="w-2 h-2 bg-green-600" />
            <span className="font-mono text-[10px] font-bold text-df-black/40 tracking-[0.06em] uppercase">
              ONLINE
            </span>
          </div>
        </div>

        {/* ── Message Feed (Scrollable) ── */}
        <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6 overscroll-y-contain">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-df-black/40">
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
                  <div className="max-w-[85%] md:max-w-[70%] flex gap-3 items-start">
                    {/* AI avatar */}
                    <div className="w-8 h-8 bg-df-black flex items-center justify-center flex-shrink-0 mt-0.5">
                      <Sparkles className="w-3.5 h-3.5 text-df-white" strokeWidth={2} />
                    </div>
                    {/* AI bubble */}
                    <div className="bg-df-white border-2 border-df-black shadow-[4px_4px_0px_#000000] px-4 py-3">
                      <span className="font-mono text-[10px] font-bold text-df-black/40 tracking-[0.06em] block mb-1.5 select-none">
                        [ SYSTEM ]:
                      </span>
                      <p className="text-sm sm:text-[15px] leading-relaxed whitespace-pre-wrap break-words font-body">
                        {msg.content}
                      </p>
                    </div>
                  </div>
                )}

                {/* ── User Message ── */}
                {msg.role === 'user' && (
                  <div className="max-w-[85%] md:max-w-[70%] flex gap-3 items-start flex-row-reverse">
                    {/* User avatar */}
                    <div className="w-8 h-8 bg-df-grey border-2 border-df-black flex items-center justify-center flex-shrink-0 mt-0.5">
                      <User className="w-3.5 h-3.5 text-df-black" strokeWidth={2} />
                    </div>
                    {/* User bubble */}
                    <div className="bg-df-black text-df-white px-4 py-3">
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
                <div className="w-8 h-8 bg-df-black flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Sparkles className="w-3.5 h-3.5 text-df-white" strokeWidth={2} />
                </div>
                <div className="bg-df-white border-2 border-df-black shadow-[4px_4px_0px_#000000] px-4 py-3.5">
                  <TypingDots />
                </div>
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        {/* ═══ INPUT CONSOLE (Pinned Bottom) ═══ */}
        <div className="flex-shrink-0 border-t-2 border-df-black bg-df-white p-4">
          <div className="max-w-3xl mx-auto">
            {/* Guest notice */}
            {isGuest && !isLoading && (
              <p className="font-mono text-[10px] font-bold text-df-black/35 tracking-[0.06em] text-center mb-2.5 uppercase select-none">
                [ SIGN IN TO SAVE CONVERSATIONS ]
              </p>
            )}
            <form onSubmit={handleSend} className="flex items-stretch gap-0">
              <div className="flex-1 border-2 border-df-black focus-within:border-[#E5202E] focus-within:ring-1 focus-within:ring-[#E5202E] transition-none">
                <input
                  id="chat-input"
                  type="text"
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  placeholder="Ask about fuel averages, ground clearance…"
                  disabled={isTyping || isLoading}
                  className="w-full bg-transparent px-4 py-3.5 outline-none font-mono text-sm text-df-black placeholder-df-black/30 disabled:opacity-40"
                />
              </div>
              <button
                id="chat-send-button"
                type="submit"
                disabled={isTyping || isLoading || !input.trim()}
                className="w-12 bg-[#E5202E] text-df-white border-2 border-df-black border-l-0 flex items-center justify-center hover:bg-red-700 transition-none disabled:opacity-30"
                aria-label="Send message"
              >
                <Send className="w-4 h-4" strokeWidth={2.5} />
              </button>
            </form>
          </div>
        </div>

      </div>
    </main>
  );
}
