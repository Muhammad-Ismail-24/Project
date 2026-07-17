import React, { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, User, Loader2, Trash2, Settings, Plus, MessageSquare, X } from 'lucide-react';
import { useOutletContext } from 'react-router-dom';

function TypingDots() {
  return (
    <span className="flex items-center gap-[5px]" aria-label="Typing">
      <span className="w-2 h-2 rounded-full bg-black/40 animate-bounce [animation-delay:0ms]"   />
      <span className="w-2 h-2 rounded-full bg-black/40 animate-bounce [animation-delay:160ms]" />
      <span className="w-2 h-2 rounded-full bg-black/40 animate-bounce [animation-delay:320ms]" />
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

async function updateAgentName(agent_name) {
  const res = await fetch(`${API_BASE}/api/chat/agent`, {
    method: 'PUT',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_name }),
  });
  if (!res.ok) throw new Error('Failed to update agent name');
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
  const { assistantName: agentName, setAssistantName: setAgentName } = useOutletContext() || { assistantName: 'GaariGuru Expert', setAssistantName: () => {} };
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
            } catch {
              startNewChat();
            }
          } else {
            startNewChat();
          }
        } else {
          startNewChat();
        }
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
              } else {
                startNewChat();
              }
            } else {
              startNewChat();
            }
          } catch (retryErr) {
            startNewChat();
          } finally {
            setIsLoading(false);
          }
        }, 4000);
        return;
      } finally {
        setIsLoading(false);
      }
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
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
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
      
      if (data.session_id && !activeSessionIdRef.current) {
        setSession(data.session_id);
      }

      setMessages(prev => [...prev, { role: 'assistant', content: data.content }]);
      if (data.agent_name) setAgentName(data.agent_name);
      
      if (!isGuest) {
        const sessionsData = await fetchSessions();
        setSessionsList(sessionsData.sessions || []);
      }
    } catch (err) {
      const errMsg = err.message || 'Automotive chat service is temporarily unavailable.';
      setMessages(prev => [...prev, { role: 'assistant', content: `⚠️ ${errMsg}` }]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleDeleteSession = async (e, sessionId) => {
    e.stopPropagation();
    if (!window.confirm('Delete this chat?')) return;
    try {
      await deleteSession(sessionId);
      setSessionsList(prev => prev.filter(s => s.session_id !== sessionId));
      if (activeSessionIdRef.current === sessionId) {
        startNewChat();
      }
    } catch (err) {
      alert('Failed to delete chat.');
    }
  };

  return (
    <div className="flex h-[calc(100dvh-80px)] w-full overflow-hidden bg-white font-sans text-black relative">

      {/* ── Mobile Sidebar Backdrop ── */}
      {isMobileSidebarOpen && !isGuest && (
        <div
          onClick={() => setIsMobileSidebarOpen(false)}
          className="fixed inset-0 top-20 z-30 bg-black/30 backdrop-blur-sm md:hidden"
        />
      )}

      {/* ── Sidebar ── */}
      {!isGuest && (
        <aside className={`
          fixed top-20 bottom-0 left-0 z-40 w-72 bg-neutral-950 flex flex-col shrink-0
          transition-transform duration-300 ease-in-out
          md:static md:translate-x-0 h-full
          ${isMobileSidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        `}>
          {/* Sidebar Header */}
          <div className="p-5 border-b border-white/10">
            <button
              onClick={startNewChat}
              className="w-full flex items-center justify-center gap-2 bg-white text-black text-sm font-bold py-3 rounded-xl hover:bg-neutral-100 transition-colors"
            >
              <Plus className="w-4 h-4" />
              New Chat
            </button>
          </div>

          {/* Sessions List */}
          <div className="flex-1 overflow-y-auto p-3 space-y-0.5">
            <p className="text-[10px] font-black text-white/30 uppercase tracking-widest mb-3 px-2 mt-2">
              Recent Chats
            </p>
            {sessionsList.length === 0 && (
              <p className="text-xs text-white/30 px-2 py-4 text-center">No conversations yet.</p>
            )}
            {sessionsList.map(session => (
              <div
                key={session.session_id}
                onClick={() => loadSession(session.session_id)}
                className={`group flex items-center justify-between px-3 py-2.5 rounded-lg cursor-pointer transition-all ${
                  activeSessionId === session.session_id
                    ? 'bg-white/10 text-white'
                    : 'text-white/60 hover:bg-white/5 hover:text-white'
                }`}
              >
                <div className="flex items-center gap-2.5 overflow-hidden min-w-0">
                  <MessageSquare className="w-3.5 h-3.5 shrink-0 opacity-60" />
                  <span className="text-[13px] font-medium truncate">{session.latest_message}</span>
                </div>
                <button
                  onClick={(e) => handleDeleteSession(e, session.session_id)}
                  className="opacity-0 group-hover:opacity-100 p-1 text-white/30 hover:text-white rounded transition-all shrink-0 ml-1"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        </aside>
      )}

      {/* ── Main Chat Area ── */}
      <div className="flex-1 flex flex-col h-full min-w-0 bg-white">

        {/* ── Header ── */}
        <div className="flex items-center justify-between px-5 sm:px-8 py-4 border-b border-neutral-100 bg-white sticky top-0 z-10">
          <div className="flex items-center gap-3 min-w-0">
            {!isGuest && (
              <button
                onClick={() => setIsMobileSidebarOpen(!isMobileSidebarOpen)}
                className="md:hidden p-2 text-black hover:bg-neutral-100 rounded-lg transition-all shrink-0"
              >
                <MessageSquare className="w-5 h-5" />
              </button>
            )}
            <div className="flex items-center gap-3 min-w-0">
              {/* Agent avatar */}
              <div className="w-9 h-9 rounded-xl bg-black flex items-center justify-center shrink-0">
                <Sparkles className="w-4 h-4 text-white" />
              </div>
              <div className="min-w-0">
                <h1 className="text-base font-black tracking-tight text-black leading-tight truncate">
                  {agentName}
                </h1>
                <p className="text-[11px] text-neutral-400 font-medium">Pakistani Car Expert</p>
              </div>
            </div>
          </div>

          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-neutral-100 text-[11px] font-bold text-neutral-600 shrink-0">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
            Online
          </span>
        </div>

        {/* ── Chat Feed ── */}
        <div className="flex-1 overflow-y-auto overscroll-y-contain scrollbar-hide">
          <div className="max-w-3xl mx-auto px-4 sm:px-6 py-8 space-y-8">
            {isLoading ? (
              <div className="flex flex-col items-center justify-center h-64 gap-4 text-neutral-400">
                <Loader2 className="w-6 h-6 animate-spin" />
                <p className="text-sm font-medium">Loading your conversation...</p>
                <p className="text-xs text-neutral-300">This may take a moment on first load.</p>
              </div>
            ) : (
              messages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`flex items-start gap-3 animate-in fade-in slide-in-from-bottom-2 duration-300 ${
                    msg.role === 'user' ? 'justify-end' : 'justify-start'
                  }`}
                >
                  {/* AI Avatar */}
                  {msg.role === 'assistant' && (
                    <div className="w-8 h-8 rounded-xl bg-black flex items-center justify-center shrink-0 mt-0.5">
                      <Sparkles className="w-3.5 h-3.5 text-white" />
                    </div>
                  )}

                  {/* Bubble */}
                  <div className={`
                    max-w-[80%] md:max-w-[68%]
                    ${msg.role === 'user'
                      ? 'bg-black text-white px-5 py-3.5 rounded-2xl rounded-tr-sm text-[14px] sm:text-[15px] font-medium leading-relaxed'
                      : 'text-black text-[14px] sm:text-[15px] font-normal leading-relaxed'
                    }
                  `}>
                    {msg.role === 'assistant' ? (
                      // AI messages: no bubble, just clean prose on white
                      // This gives it a professional editorial feel vs chat-bubble feel
                      <div className="bg-neutral-50 border border-neutral-100 rounded-2xl rounded-tl-sm px-5 py-4 whitespace-pre-wrap break-words">
                        {msg.content}
                      </div>
                    ) : (
                      // User messages: solid black pill
                      <div className="whitespace-pre-wrap break-words">{msg.content}</div>
                    )}
                  </div>

                  {/* User Avatar */}
                  {msg.role === 'user' && (
                    <div className="w-8 h-8 rounded-xl bg-neutral-100 border border-neutral-200 flex items-center justify-center shrink-0 mt-0.5">
                      <User className="w-4 h-4 text-neutral-600" />
                    </div>
                  )}
                </div>
              ))
            )}

            {/* Typing indicator */}
            {isTyping && (
              <div className="flex items-start gap-3 animate-in fade-in slide-in-from-bottom-2 duration-300">
                <div className="w-8 h-8 rounded-xl bg-black flex items-center justify-center shrink-0 mt-0.5">
                  <Sparkles className="w-3.5 h-3.5 text-white" />
                </div>
                <div className="bg-neutral-50 border border-neutral-100 rounded-2xl rounded-tl-sm px-5 py-4">
                  <TypingDots />
                </div>
              </div>
            )}

            <div ref={chatEndRef} />
          </div>
        </div>

        {/* ── Input Area ── */}
        <div className="border-t border-neutral-100 bg-white px-4 sm:px-6 py-4">
          <div className="max-w-3xl mx-auto">
            {isGuest && !isLoading && (
              <p className="text-center text-xs text-neutral-400 font-medium mb-3">
                Sign in to save multiple conversations and customize your assistant.
              </p>
            )}
            <form onSubmit={handleSend} className="relative flex items-center w-full">
              <input
                type="text"
                value={input}
                onChange={e => setInput(e.target.value)}
                placeholder="Ask about fuel averages, ground clearance, parts..."
                disabled={isTyping || isLoading}
                className="w-full bg-neutral-50 border border-neutral-200 rounded-2xl pl-5 pr-14 py-4 outline-none focus:border-black focus:ring-2 focus:ring-black/5 transition-all font-medium text-base placeholder-neutral-400 text-black disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={isTyping || isLoading || !input.trim()}
                className="absolute right-2 w-10 h-10 bg-black text-white rounded-xl flex items-center justify-center hover:bg-neutral-800 transition-all disabled:opacity-40 active:scale-95"
              >
                <Send className="w-4 h-4" />
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}