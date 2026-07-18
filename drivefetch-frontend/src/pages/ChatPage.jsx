import React, { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, User, Loader2, Trash2, Plus, MessageSquare } from 'lucide-react';
import { useOutletContext } from 'react-router-dom';

function TypingDots() {
  return (
    <span className="flex items-center gap-[5px]" aria-label="Typing">
      <span className="w-1.5 h-1.5 rounded-full bg-black/30 animate-bounce [animation-delay:0ms]" />
      <span className="w-1.5 h-1.5 rounded-full bg-black/30 animate-bounce [animation-delay:160ms]" />
      <span className="w-1.5 h-1.5 rounded-full bg-black/30 animate-bounce [animation-delay:320ms]" />
    </span>
  );
}

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
    useOutletContext() || { assistantName: 'GaariGuru Expert', setAssistantName: () => {} };
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

  return (
    <div className="flex h-[calc(100dvh-80px)] w-full overflow-hidden font-sans text-black relative"
      style={{ background: 'linear-gradient(160deg, #c0c0c0 0%, #a8a8a8 50%, #b8b8b8 100%)' }}
    >

      {/* Mobile sidebar backdrop */}
      {isMobileSidebarOpen && !isGuest && (
        <div
          onClick={() => setIsMobileSidebarOpen(false)}
          className="fixed inset-0 top-20 z-30 bg-black/10 backdrop-blur-sm md:hidden"
        />
      )}

      {/* ── Sidebar ── */}
      {!isGuest && (
        <div className={`
          fixed top-20 bottom-0 left-0 z-40 w-60 flex flex-col shrink-0
          border-r border-white/30 transition-transform duration-300 ease-in-out
          md:static md:translate-x-0 h-full
          bg-white/20 backdrop-blur-xl
          ${isMobileSidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        `}>
          <div className="p-3 border-b border-white/25">
            <button
              onClick={startNewChat}
              className="w-full flex items-center justify-center gap-2 bg-black text-white text-sm font-medium py-2.5 rounded-xl hover:bg-neutral-800 transition-colors"
            >
              <Plus className="w-4 h-4" strokeWidth={2} />
              New Chat
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
            <p className="text-[10px] font-semibold text-black/40 uppercase tracking-[0.14em] px-2 pt-3 pb-2">
              Recent Chats
            </p>
            {sessionsList.map(session => (
              <div
                key={session.session_id}
                onClick={() => loadSession(session.session_id)}
                className={`group flex items-center justify-between px-3 py-2.5 rounded-xl cursor-pointer transition-all
                  ${activeSessionId === session.session_id
                    ? 'bg-white/50 shadow-sm'
                    : 'hover:bg-white/25'
                  }`}
              >
                <div className="flex items-center gap-2 overflow-hidden">
                  <MessageSquare
                    className={`w-3.5 h-3.5 shrink-0 ${activeSessionId === session.session_id ? 'text-black' : 'text-black/40'}`}
                    strokeWidth={1.5}
                  />
                  <span className={`text-sm truncate ${activeSessionId === session.session_id ? 'font-semibold text-black' : 'font-normal text-black/70'}`}>
                    {session.latest_message}
                  </span>
                </div>
                <button
                  onClick={(e) => handleDeleteSession(e, session.session_id)}
                  className="opacity-0 group-hover:opacity-100 p-1 text-black/30 hover:text-black/70 rounded-lg transition-all shrink-0"
                >
                  <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Main Chat Area ── */}
      <div className="flex-1 flex flex-col h-full relative min-w-0">

        {/* Header — thin, minimal */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-white/25 bg-white/20 backdrop-blur-xl sticky top-0 z-10">
          <div className="flex items-center gap-3 min-w-0">
            {!isGuest && (
              <button
                onClick={() => setIsMobileSidebarOpen(!isMobileSidebarOpen)}
                className="md:hidden p-1.5 text-black/50 hover:text-black hover:bg-white/30 rounded-lg transition-all shrink-0"
              >
                <MessageSquare className="w-5 h-5" strokeWidth={1.5} />
              </button>
            )}
            <div className="min-w-0">
              <h1 className="text-base font-semibold text-black tracking-tight truncate">{agentName}</h1>
            </div>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            <span className="text-xs font-medium text-black/50">Online</span>
          </div>
        </div>

        {/* Chat Feed */}
        <div className="flex-1 overflow-y-auto px-4 md:px-8 py-6 space-y-5 overscroll-y-contain">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-black/40">
              <Loader2 className="w-5 h-5 animate-spin" strokeWidth={1.5} />
              <p className="text-sm font-medium">Loading…</p>
            </div>
          ) : (
            messages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex items-end gap-2.5 animate-in fade-in slide-in-from-bottom-2 duration-300
                  ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {/* AI avatar — smaller, cleaner */}
                {msg.role === 'assistant' && (
                  <div className="w-7 h-7 rounded-full shrink-0 flex items-center justify-center bg-black">
                    <Sparkles className="w-3 h-3 text-white" strokeWidth={1.5} />
                  </div>
                )}

                {/* Bubble — one surface, no stacked decorations */}
                <div className={`
                  max-w-[85%] md:max-w-[68%] px-4 py-3 text-[14px] sm:text-[15px] leading-relaxed whitespace-pre-wrap break-words
                  ${msg.role === 'user'
                    ? 'bg-black text-white rounded-2xl rounded-br-sm font-medium'
                    : 'bg-white/65 backdrop-blur-sm text-black rounded-2xl rounded-bl-sm font-normal border border-white/60 shadow-sm'
                  }
                `}>
                  {msg.content}
                </div>

                {/* User avatar */}
                {msg.role === 'user' && (
                  <div className="w-7 h-7 rounded-full shrink-0 flex items-center justify-center bg-white/60 border border-white/40">
                    <User className="w-3.5 h-3.5 text-black/60" strokeWidth={1.5} />
                  </div>
                )}
              </div>
            ))
          )}

          {isTyping && (
            <div className="flex items-end gap-2.5 justify-start animate-in fade-in slide-in-from-bottom-2 duration-300">
              <div className="w-7 h-7 rounded-full shrink-0 flex items-center justify-center bg-black">
                <Sparkles className="w-3 h-3 text-white" strokeWidth={1.5} />
              </div>
              <div className="px-4 py-3 rounded-2xl rounded-bl-sm bg-white/65 backdrop-blur-sm border border-white/60 shadow-sm">
                <TypingDots />
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        {/* Input Area */}
        <div className="px-4 py-3 bg-white/15 backdrop-blur-xl border-t border-white/25">
          <div className="max-w-3xl mx-auto">
            {isGuest && !isLoading && (
              <p className="text-center text-xs text-black/40 font-medium mb-2">
                Sign in to save conversations and customise your assistant.
              </p>
            )}
            <form onSubmit={handleSend} className="relative flex items-center w-full">
              <input
                type="text"
                value={input}
                onChange={e => setInput(e.target.value)}
                placeholder="Ask about fuel averages, ground clearance…"
                disabled={isTyping || isLoading}
                className="w-full bg-white/55 backdrop-blur-md border border-white/50 rounded-2xl pl-5 pr-14 py-3.5 outline-none focus:border-black/30 focus:ring-1 focus:ring-black/20 transition-all font-normal text-base placeholder-black/35 text-black shadow-sm disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={isTyping || isLoading || !input.trim()}
                className="absolute right-1.5 w-9 h-9 bg-black text-white rounded-xl flex items-center justify-center hover:bg-neutral-800 transition-colors disabled:opacity-40 active:scale-95"
              >
                <Send className="w-3.5 h-3.5 ml-0.5" strokeWidth={1.5} />
              </button>
            </form>
          </div>
        </div>

      </div>
    </div>
  );
}
