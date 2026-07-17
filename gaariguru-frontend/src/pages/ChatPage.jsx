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
    // FIX 1: Using 100dvh prevents mobile browser address bars from breaking the chat view
    <div className="flex h-[calc(100dvh-80px)] w-full overflow-hidden bg-[#a3a3a3] font-sans text-black relative">
      
      {/* ── Mobile Sidebar Backdrop ── */}
      {isMobileSidebarOpen && !isGuest && (
        <div 
          onClick={() => setIsMobileSidebarOpen(false)}
          className="fixed inset-0 top-20 z-30 bg-black/20 backdrop-blur-sm md:hidden"
        />
      )}

      {/* ── Sidebar (Responsive Dynamic Layout) ── */}
      {!isGuest && (
        <div className={`
          fixed top-20 bottom-0 left-0 z-40 w-64 bg-[#a3a3a3] border-r border-black/15 flex flex-col shrink-0 transition-transform duration-300 ease-in-out
          md:static md:translate-x-0 md:bg-white/20 md:backdrop-blur-md h-full
          ${isMobileSidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        `}>
          <div className="p-4 border-b border-black/15">
            <button 
              onClick={startNewChat}
              className="w-full flex items-center justify-center gap-2 bg-black text-white font-bold py-3 rounded-xl hover:bg-neutral-800 transition-colors shadow-md border border-transparent"
            >
              <Plus className="w-5 h-5" />
              New Chat
            </button>
          </div>
          
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            <h3 className="text-[11px] font-black text-black/60 uppercase tracking-widest mb-2 px-2 mt-2">Recent Chats</h3>
            {sessionsList.map(session => (
              <div 
                key={session.session_id}
                onClick={() => loadSession(session.session_id)}
                className={`group flex items-center justify-between p-3 rounded-xl cursor-pointer transition-all ${activeSessionId === session.session_id ? 'bg-white/60 shadow-sm border border-black/20' : 'hover:bg-white/30 border border-transparent'}`}
              >
                <div className="flex items-center gap-2 overflow-hidden w-full">
                  <MessageSquare className={`w-4 h-4 shrink-0 ${activeSessionId === session.session_id ? 'text-black' : 'text-black/60'}`} />
                  <span className={`text-sm font-bold truncate ${activeSessionId === session.session_id ? 'text-black' : 'text-black/80'}`}>
                    {session.latest_message}
                  </span>
                </div>
                <button 
                  onClick={(e) => handleDeleteSession(e, session.session_id)}
                  className="opacity-0 group-hover:opacity-100 p-1 text-black/40 hover:text-black rounded transition-all shrink-0"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Main Chat Area ── */}
      <div className="flex-1 flex flex-col h-full relative min-w-0">
        
        {/* Header */}
        <div className="flex items-center justify-between px-4 sm:px-6 py-4 border-b border-black/15 bg-white/40 backdrop-blur-md sticky top-0 z-10 shadow-sm">
          <div className="flex items-center gap-3 min-w-0">
            {!isGuest && (
              <button
                onClick={() => setIsMobileSidebarOpen(!isMobileSidebarOpen)}
                className="md:hidden p-2 text-black hover:bg-black/10 rounded-xl border border-black/10 bg-white/60 shadow-sm transition-all shrink-0 active:scale-95"
                title="Toggle chat history"
              >
                <MessageSquare className="w-5 h-5" />
              </button>
            )}
            
            <div className="flex flex-col min-w-0">
              <h1 className="text-lg sm:text-xl font-black tracking-tight text-black truncate">{agentName}</h1>
            </div>
          </div>
          
          <div className="flex items-center gap-2 shrink-0">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-black/10 bg-white/60 text-xs font-bold text-black shadow-sm">
              <span className="w-2 h-2 rounded-full bg-black"></span>
              Online
            </span>
          </div>
        </div>

        {/* Chat Feed */}
        <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6 scrollbar-hide overscroll-y-contain">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center h-full text-black/60 gap-3">
              <Loader2 className="w-6 h-6 animate-spin text-black" />
              <p className="font-bold text-sm">Loading your conversation...</p>
            </div>
          ) : (
            messages.map((msg, idx) => (
              <div
                key={idx}
                // FIX 2: Slide-in and fade-in animation for a smoother mobile app feel
                className={`flex items-end gap-2 sm:gap-3 animate-in fade-in slide-in-from-bottom-2 duration-300 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {msg.role === 'assistant' && (
                  <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center bg-black shadow-md border border-white/20">
                    <Sparkles className="w-3.5 h-3.5 text-white" />
                  </div>
                )}

                <div className={`
                  max-w-[88%] md:max-w-[70%] px-4 sm:px-5 py-3 rounded-3xl text-[14px] sm:text-[15px] leading-relaxed font-bold whitespace-pre-wrap break-words shadow-md
                  ${msg.role === 'user'
                    ? 'bg-black text-white rounded-br-sm border border-black'
                    : 'bg-white/60 backdrop-blur-md text-black rounded-bl-sm border border-black/15'
                  }
                `}>
                  {msg.content}
                </div>

                {msg.role === 'user' && (
                  <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center bg-white border border-black/20 shadow-sm">
                    <User className="w-4 h-4 text-black" />
                  </div>
                )}
              </div>
            ))
          )}

          {isTyping && (
            <div className="flex items-end gap-3 justify-start animate-in fade-in slide-in-from-bottom-2 duration-300">
              <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center bg-black shadow-md border border-white/20">
                <Sparkles className="w-3.5 h-3.5 text-white" />
              </div>
              <div className="px-5 py-4 rounded-3xl rounded-bl-sm bg-white/60 backdrop-blur-md border border-black/15 shadow-md flex items-center gap-2">
                <TypingDots />
              </div>
            </div>
          )}

          <div ref={chatEndRef} />
        </div>

        {/* Input Area */}
        <div className="p-4 bg-white/40 backdrop-blur-md border-t border-black/15">
          <div className="max-w-3xl mx-auto">
            {isGuest && !isLoading && (
              <p className="text-center text-xs text-black/60 font-bold mb-2">
                Sign in to save multiple conversations and customize your assistant.
              </p>
            )}
            <form onSubmit={handleSend} className="relative flex items-center shrink-0 w-full">
              <input
                type="text"
                value={input}
                onChange={e => setInput(e.target.value)}
                placeholder="Ask about fuel averages, ground clearance..."
                disabled={isTyping || isLoading}
                // FIX 3: text-base instead of text-sm guarantees iOS Safari won't auto-zoom the page!
                className="w-full bg-white/60 backdrop-blur-md border border-black/20 rounded-full pl-5 pr-14 py-3.5 outline-none focus:border-black focus:ring-1 focus:ring-black transition-all font-bold text-base placeholder-black/50 text-black shadow-sm disabled:opacity-60"
              />
              <button
                type="submit"
                disabled={isTyping || isLoading || !input.trim()}
                className="absolute right-1.5 w-10 h-11 bg-black text-white rounded-full flex items-center justify-center hover:bg-neutral-800 transition-colors shadow-md disabled:opacity-50 active:scale-95"
              >
                <Send className="w-4 h-4 ml-0.5" />
              </button>
            </form>
          </div>
        </div>

      </div>
    </div>
  );
}