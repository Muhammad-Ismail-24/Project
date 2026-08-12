import React, { useState, useRef, useEffect } from 'react';
import { Helmet } from 'react-helmet-async';
import { Send, Sparkles, User, Loader2, Trash2, Plus, MessageSquare } from 'lucide-react';
import { useOutletContext } from 'react-router-dom';

function TypingDots() {
  return (
    <span className="flex items-center gap-[5px]" aria-label="Typing">
      <span className="w-1.5 h-1.5 rounded-full bg-text-faint animate-bounce [animation-delay:0ms]" />
      <span className="w-1.5 h-1.5 rounded-full bg-text-faint animate-bounce [animation-delay:160ms]" />
      <span className="w-1.5 h-1.5 rounded-full bg-text-faint animate-bounce [animation-delay:320ms]" />
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

  return (
    <main className="flex mt-24 h-[calc(100dvh-6rem)] w-full overflow-hidden font-sans relative">
      <Helmet>
        <title>AI Car Inspection Assistant | DriveFetch</title>
        <meta name="description" content="Chat with our AI Car Inspection Assistant to ask questions about specific car conditions and make an informed buying decision." />
        <link rel="canonical" href="https://carfinderproject.vercel.app/chat" />
      </Helmet>

      {/* Mobile sidebar backdrop */}
      {isMobileSidebarOpen && !isGuest && (
        <div
          onClick={() => setIsMobileSidebarOpen(false)}
          className="fixed inset-0 top-24 z-30 bg-black/40 backdrop-blur-sm md:hidden"
        />
      )}

      {/* ── Sidebar ── */}
      {!isGuest && (
        <div className={`
          glass-thin !rounded-none fixed top-24 bottom-0 left-0 z-40 w-60 flex flex-col shrink-0
          transition-transform duration-300 ease-in-out
          md:static md:translate-x-0 h-full
          ${isMobileSidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        `}>
          <div className="p-3" style={{ borderBottom: '1px solid var(--df-glass-border)' }}>
            <button
              onClick={startNewChat}
              className="btn-primary w-full justify-center text-sm"
            >
              <Plus className="w-4 h-4" strokeWidth={2} />
              New Chat
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
            <p className="text-[10px] font-semibold text-text-faint uppercase tracking-[0.14em] px-2 pt-3 pb-2">
              Recent Chats
            </p>
            {sessionsList.map(session => (
              <div
                key={session.session_id}
                onClick={() => loadSession(session.session_id)}
                className={`group flex items-center justify-between px-3 py-2.5 rounded-xl cursor-pointer transition-all
                  ${activeSessionId === session.session_id
                    ? 'bg-white/10'
                    : 'hover:bg-white/5'
                  }`}
              >
                <div className="flex items-center gap-2 overflow-hidden">
                  <MessageSquare
                    className={`w-3.5 h-3.5 shrink-0 ${activeSessionId === session.session_id ? 'text-text' : 'text-text-faint'}`}
                    strokeWidth={1.5}
                  />
                  <span className={`text-sm truncate ${activeSessionId === session.session_id ? 'font-semibold text-text' : 'font-normal text-text-dim'}`}>
                    {session.latest_message}
                  </span>
                </div>
                <button
                  onClick={(e) => handleDeleteSession(e, session.session_id)}
                  className="opacity-0 group-hover:opacity-100 p-1 text-text-faint hover:text-text rounded-lg transition-all shrink-0"
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
        <div className="glass-thin !rounded-none flex items-center justify-between px-5 py-3.5 sticky top-0 z-10">
          <div className="flex items-center gap-3 min-w-0">
            {!isGuest && (
              <button
                onClick={() => setIsMobileSidebarOpen(!isMobileSidebarOpen)}
                className="md:hidden p-1.5 text-text-dim hover:text-text hover:bg-white/5 rounded-lg transition-all shrink-0"
              >
                <MessageSquare className="w-5 h-5" strokeWidth={1.5} />
              </button>
            )}
            <div className="min-w-0">
              <h1 className="text-base font-semibold text-text tracking-tight truncate">{agentName}</h1>
            </div>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            <span className="w-1.5 h-1.5 rounded-full bg-good" />
            <span className="text-xs font-medium text-text-dim">Online</span>
          </div>
        </div>

        {/* Chat Feed */}
        <div className="flex-1 overflow-y-auto px-4 md:px-8 py-6 space-y-5 overscroll-y-contain">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-text-faint">
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
                  <div className="w-7 h-7 rounded-full shrink-0 flex items-center justify-center bg-accent">
                    <Sparkles className="w-3 h-3 text-white" strokeWidth={1.5} />
                  </div>
                )}

                {/* Bubble — one surface, no stacked decorations */}
                <div className={`
                  max-w-[85%] md:max-w-[68%] px-4 py-3 text-[14px] sm:text-[15px] leading-relaxed whitespace-pre-wrap break-words
                  ${msg.role === 'user'
                    ? 'bg-surface-2 text-text rounded-2xl rounded-br-sm font-medium'
                    : 'glass !rounded-2xl rounded-bl-sm text-text font-normal'
                  }
                `}>
                  {msg.content}
                </div>

                {/* User avatar */}
                {msg.role === 'user' && (
                  <div className="glass-thin w-7 h-7 rounded-full shrink-0 flex items-center justify-center">
                    <User className="w-3.5 h-3.5 text-text-dim" strokeWidth={1.5} />
                  </div>
                )}
              </div>
            ))
          )}

          {isTyping && (
            <div className="flex items-end gap-2.5 justify-start animate-in fade-in slide-in-from-bottom-2 duration-300">
              <div className="w-7 h-7 rounded-full shrink-0 flex items-center justify-center bg-accent">
                <Sparkles className="w-3 h-3 text-white" strokeWidth={1.5} />
              </div>
              <div className="glass !rounded-2xl rounded-bl-sm px-4 py-3">
                <TypingDots />
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        {/* Input Area */}
        <div className="glass-thin !rounded-none px-4 py-3">
          <div className="max-w-3xl mx-auto">
            {isGuest && !isLoading && (
              <p className="text-center text-xs text-text-faint font-medium mb-2">
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
                className="field !rounded-2xl pl-5 pr-14 py-3.5 text-base"
              />
              <button
                type="submit"
                disabled={isTyping || isLoading || !input.trim()}
                className="absolute right-1.5 w-9 h-9 bg-accent text-white rounded-xl flex items-center justify-center hover:brightness-110 transition-all disabled:opacity-40 active:scale-95"
              >
                <Send className="w-3.5 h-3.5 ml-0.5" strokeWidth={1.5} />
              </button>
            </form>
          </div>
        </div>

      </div>
    </main>
  );
}
