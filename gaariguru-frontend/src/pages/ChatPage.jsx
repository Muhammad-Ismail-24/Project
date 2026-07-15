import React, { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, User, Loader2, Trash2, Settings, Plus, MessageSquare, X } from 'lucide-react';

function TypingDots() {
  return (
    <span className="flex items-center gap-[5px]" aria-label="Typing">
      <span className="w-2 h-2 rounded-full bg-black/40 animate-bounce [animation-delay:0ms]"   />
      <span className="w-2 h-2 rounded-full bg-black/40 animate-bounce [animation-delay:160ms]" />
      <span className="w-2 h-2 rounded-full bg-black/40 animate-bounce [animation-delay:320ms]" />
    </span>
  );
}

// PROXY FIX: Changed this to an empty string so it automatically routes to /api/...
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
  const [agentName, setAgentName] = useState('GaariGuru Expert');
  const [isGuest, setIsGuest] = useState(true);
  
  const [isTyping, setIsTyping] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  const [showNameEditor, setShowNameEditor] = useState(false);
  const [nameInput, setNameInput] = useState('');
  const [nameSaving, setNameSaving] = useState(false);

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
              setAgentName(hist.agent_name || 'GaariGuru Expert');
              setNameInput(hist.agent_name || 'GaariGuru Expert');
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
                setAgentName(hist.agent_name || 'GaariGuru Expert');
                setNameInput(hist.agent_name || 'GaariGuru Expert');
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
    try {
      const data = await fetchSessionHistory(sessionId);
      setAgentName(data.agent_name || 'GaariGuru Expert');
      setNameInput(data.agent_name || 'GaariGuru Expert');
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

  const handleSaveAgentName = async () => {
    const trimmed = nameInput.trim();
    if (!trimmed || trimmed === agentName) {
      setShowNameEditor(false);
      return;
    }
    setNameSaving(true);
    try {
      const data = await updateAgentName(trimmed);
      setAgentName(data.agent_name);
      setNameInput(data.agent_name);
      setShowNameEditor(false);
    } catch {
      alert('Failed to update assistant name. Please try again.');
    } finally {
      setNameSaving(false);
    }
  };

  return (
    <div className="flex h-[calc(100vh-80px)] w-full overflow-hidden bg-[#a3a3a3] font-sans text-black">
      
      {/* ── Sidebar ── */}
      {!isGuest && (
        <div className="w-64 bg-white/20 backdrop-blur-md border-r border-black/15 flex flex-col shrink-0">
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
      <div className="flex-1 flex flex-col h-full relative">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-black/15 bg-white/40 backdrop-blur-md sticky top-0 z-10 shadow-sm">
          <div className="flex flex-col">
            <h1 className="text-xl font-black tracking-tight text-black">GaariGuru Expert</h1>
            <div className="flex items-center gap-2">
              <p className="text-xs text-black/60 font-bold">
                {isLoading ? 'Loading...' : `Powered by ${agentName}`}
              </p>
              {!isGuest && (
                <button
                  onClick={() => { setNameInput(agentName); setShowNameEditor(true); }}
                  title="Assistant preferences"
                  className="text-black/40 hover:text-black transition-colors"
                >
                  <Settings className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-black/10 bg-white/60 text-xs font-bold text-black shadow-sm">
              <span className="w-2 h-2 rounded-full bg-black"></span>
              Online
            </span>
          </div>
        </div>

        {/* Chat Feed */}
        <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6 scrollbar-hide">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center h-full text-black/60 gap-3">
              <Loader2 className="w-6 h-6 animate-spin text-black" />
              <p className="font-bold text-sm">Loading your conversation...</p>
            </div>
          ) : (
            messages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex items-end gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {/* AI Avatar */}
                {msg.role === 'assistant' && (
                  <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center bg-black shadow-md border border-white/20">
                    <Sparkles className="w-3.5 h-3.5 text-white" />
                  </div>
                )}

                {/* Message Bubble */}
                <div className={`
                  max-w-[85%] md:max-w-[70%] px-5 py-3.5 rounded-3xl text-[15px] leading-relaxed font-bold whitespace-pre-wrap break-words shadow-md
                  ${msg.role === 'user'
                    ? 'bg-black text-white rounded-br-sm border border-black'
                    : 'bg-white/60 backdrop-blur-md text-black rounded-bl-sm border border-black/15'
                  }
                `}>
                  {msg.content}
                </div>

                {/* User Avatar */}
                {msg.role === 'user' && (
                  <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center bg-white border border-black/20 shadow-sm">
                    <User className="w-4 h-4 text-black" />
                  </div>
                )}
              </div>
            ))
          )}

          {isTyping && (
            <div className="flex items-end gap-3 justify-start">
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
                placeholder="Ask about fuel averages, ground clearance, parts..."
                disabled={isTyping || isLoading}
                className="w-full bg-white/60 backdrop-blur-md border border-black/20 rounded-full pl-6 pr-16 py-4 outline-none focus:border-black focus:ring-1 focus:ring-black transition-all font-bold text-base md:text-lg placeholder-black/50 text-black shadow-sm disabled:opacity-60"
              />
              <button
                type="submit"
                disabled={isTyping || isLoading || !input.trim()}
                className="absolute right-2 w-12 h-12 bg-black text-white rounded-full flex items-center justify-center hover:bg-neutral-800 transition-colors shadow-md disabled:opacity-50"
              >
                <Send className="w-5 h-5 ml-1" />
              </button>
            </form>
          </div>
        </div>

      </div>

      {/* ── Settings Drawer ── */}
      <div
        aria-hidden="true"
        onClick={() => { setShowNameEditor(false); setNameInput(agentName); }}
        className={['fixed inset-0 z-50 bg-black/20 backdrop-blur-sm transition-opacity duration-300', showNameEditor ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'].join(' ')}
      />

      <div
        role="dialog"
        className={['fixed inset-y-0 right-0 z-50 w-80 lg:w-96 bg-[#a3a3a3] shadow-2xl flex flex-col border-l border-black/15 transition-transform duration-300 ease-out', showNameEditor ? 'translate-x-0' : 'translate-x-full'].join(' ')}
      >
        <div className="flex items-center justify-between px-6 py-5 border-b border-black/10 bg-white/40 backdrop-blur-md">
          <div>
            <h2 className="text-base font-black tracking-tight text-black">Assistant Preferences</h2>
            <p className="text-xs text-black/60 font-bold mt-0.5">Personalise your AI expert</p>
          </div>
          <button
            onClick={() => { setShowNameEditor(false); setNameInput(agentName); }}
            className="w-8 h-8 flex items-center justify-center rounded-full text-black/60 hover:text-black hover:bg-black/10 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-8 space-y-8">
          <div className="space-y-2">
            <label className="block text-xs font-black tracking-widest uppercase text-black">Assistant Name</label>
            <input
              type="text"
              value={nameInput}
              onChange={e => setNameInput(e.target.value)}
              maxLength={40}
              placeholder="e.g. GaariGuru Expert..."
              onKeyDown={e => e.key === 'Enter' && handleSaveAgentName()}
              className="w-full px-4 py-3 rounded-xl border border-black/20 bg-white/60 backdrop-blur-sm text-sm font-bold text-black placeholder-black/40 outline-none focus:border-black focus:ring-1 focus:ring-black shadow-sm"
            />
          </div>

          <div className="rounded-xl bg-white/60 backdrop-blur-md border border-black/15 px-4 py-3 flex items-center gap-3 shadow-sm">
            <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center bg-black shadow-md border border-white/20">
              <Sparkles className="w-3.5 h-3.5 text-white" />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-black text-black truncate">{nameInput.trim() || 'GaariGuru Expert'}</p>
              <p className="text-[11px] text-black/60 font-bold">Preview</p>
            </div>
          </div>
        </div>

        <div className="px-6 py-5 border-t border-black/10 bg-white/40 backdrop-blur-md flex gap-3">
          <button
            onClick={() => { setShowNameEditor(false); setNameInput(agentName); }}
            className="flex-1 py-3 rounded-xl border border-black text-sm font-bold text-black hover:bg-black hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSaveAgentName}
            disabled={nameSaving || !nameInput.trim()}
            className="flex-1 py-3 rounded-xl bg-black border border-black text-white text-sm font-bold hover:bg-neutral-800 transition-colors disabled:opacity-50 shadow-md"
          >
            {nameSaving ? 'Saving…' : 'Save'}
          </button>
        </div>

      </div>

    </div>
  );
}