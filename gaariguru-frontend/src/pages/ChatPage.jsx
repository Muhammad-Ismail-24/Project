import React, { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, User, Loader2, Trash2, Settings, Plus, MessageSquare } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || 'https://carfinder-project-backend.onrender.com';

// ─── API helpers ──────────────
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

async function sendMessage(message, sessionId) {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId }),
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

// ─── Component ───────────────────────────────────────────────────────────────

export default function ChatPage() {
  const [sessionsList, setSessionsList] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  
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
            loadSession(data.sessions[0].session_id);
          } else {
            startNewChat();
          }
        } else {
          startNewChat();
        }
      } catch (err) {
        console.error("Failed to load sessions:", err);
        startNewChat();
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
      setActiveSessionId(sessionId);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  const startNewChat = () => {
    setActiveSessionId(null);
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
      const data = await sendMessage(query, activeSessionId);
      
      if (data.session_id && !activeSessionId) {
        setActiveSessionId(data.session_id);
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
      if (activeSessionId === sessionId) {
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
    <div className="flex h-[calc(100vh-80px)] w-full overflow-hidden">
      
      {/* Sidebar - Strict Tailwind Split Layout */}
      {!isGuest && (
        <div className="w-64 bg-neutral-50 border-r flex flex-col shrink-0">
          <div className="p-4 border-b border-neutral-200">
            <button 
              onClick={startNewChat}
              className="w-full flex items-center justify-center gap-2 bg-black text-white font-bold py-3 rounded-lg hover:bg-neutral-800 transition-colors shadow-sm"
            >
              <Plus className="w-5 h-5" />
              New Chat
            </button>
          </div>
          
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            <h3 className="text-[11px] font-bold text-neutral-400 uppercase tracking-wider mb-2 px-2 mt-2">Recent Chats</h3>
            {sessionsList.map(session => (
              <div 
                key={session.session_id}
                onClick={() => loadSession(session.session_id)}
                className={`group flex items-center justify-between p-3 rounded-lg cursor-pointer transition-colors ${activeSessionId === session.session_id ? 'bg-white shadow-sm border border-neutral-200' : 'hover:bg-neutral-200/50 text-neutral-600 border border-transparent'}`}
              >
                <div className="flex items-center gap-2 overflow-hidden w-full">
                  <MessageSquare className={`w-4 h-4 shrink-0 ${activeSessionId === session.session_id ? 'text-black' : 'text-neutral-400'}`} />
                  <span className={`text-sm font-medium truncate ${activeSessionId === session.session_id ? 'text-black' : ''}`}>
                    {session.latest_message}
                  </span>
                </div>
                <button 
                  onClick={(e) => handleDeleteSession(e, session.session_id)}
                  className="opacity-0 group-hover:opacity-100 p-1 text-neutral-400 hover:text-red-500 rounded transition-all shrink-0"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col h-full bg-white relative">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-100 bg-white/80 backdrop-blur-md sticky top-0 z-10">
          <div className="flex flex-col">
            <h1 className="text-xl font-black tracking-tight text-black">GaariGuru Expert</h1>
            <div className="flex items-center gap-2">
              {showNameEditor ? (
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={nameInput}
                    onChange={e => setNameInput(e.target.value)}
                    maxLength={40}
                    className="border border-neutral-300 rounded-md px-2 py-0.5 text-xs outline-none focus:border-black"
                    placeholder="Enter assistant name..."
                    onKeyDown={e => e.key === 'Enter' && handleSaveAgentName()}
                    autoFocus
                  />
                  <button
                    onClick={handleSaveAgentName}
                    disabled={nameSaving}
                    className="text-[10px] uppercase font-bold bg-black text-white px-2 py-1 rounded disabled:opacity-50"
                  >
                    {nameSaving ? 'Saving' : 'Save'}
                  </button>
                  <button
                    onClick={() => { setShowNameEditor(false); setNameInput(agentName); }}
                    className="text-[10px] uppercase font-bold text-neutral-500 hover:text-black px-1"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <>
                  <p className="text-xs text-neutral-500 font-medium">
                    {isLoading ? 'Loading...' : `Powered by ${agentName}`}
                  </p>
                  {!isGuest && (
                    <button
                      onClick={() => setShowNameEditor(true)}
                      title="Rename your assistant"
                      className="text-neutral-400 hover:text-black transition-colors"
                    >
                      <Settings className="w-3.5 h-3.5" />
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-neutral-100 text-xs font-bold text-neutral-600">
              <span className="w-2 h-2 rounded-full bg-green-500"></span>
              Online
            </span>
          </div>
        </div>

        {/* Chat Feed */}
        <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6 bg-white scrollbar-hide">
          {isLoading ? (
            <div className="flex items-center justify-center h-full text-neutral-400 font-medium">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />
              Loading your conversation...
            </div>
          ) : (
            messages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex items-end space-x-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {msg.role === 'assistant' && (
                  <div className="w-8 h-8 rounded-full bg-black text-white flex items-center justify-center shrink-0 shadow-sm border border-neutral-200">
                    <Sparkles className="w-4 h-4" />
                  </div>
                )}

                <div className={`max-w-[85%] md:max-w-[70%] p-4 rounded-2xl text-[15px] leading-relaxed font-medium whitespace-pre-wrap break-words ${
                  msg.role === 'user'
                    ? 'bg-neutral-100 text-black rounded-br-none shadow-sm border border-neutral-200'
                    : 'bg-white border border-neutral-200 text-black rounded-bl-none shadow-sm'
                }`}>
                  {msg.content}
                </div>

                {msg.role === 'user' && (
                  <div className="w-8 h-8 rounded-full bg-black flex items-center justify-center shrink-0 shadow-sm">
                    <User className="w-4 h-4 text-white" />
                  </div>
                )}
              </div>
            ))
          )}

          {isTyping && (
            <div className="flex items-end space-x-3 justify-start">
              <div className="w-8 h-8 rounded-full bg-black text-white flex items-center justify-center shrink-0 shadow-sm border border-neutral-200 animate-pulse">
                <Sparkles className="w-4 h-4" />
              </div>
              <div className="bg-white border border-neutral-200 text-neutral-500 p-4 rounded-2xl rounded-bl-none shadow-sm flex items-center space-x-2 text-[15px] font-medium">
                <Loader2 className="w-4 h-4 animate-spin text-black" />
                <span>{agentName} is typing...</span>
              </div>
            </div>
          )}

          <div ref={chatEndRef} />
        </div>

        {/* Input Area */}
        <div className="p-4 bg-white border-t border-neutral-100">
          <div className="max-w-3xl mx-auto">
            {isGuest && !isLoading && (
              <p className="text-center text-xs text-neutral-400 mb-2">
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
                className="w-full bg-neutral-100 border border-neutral-200 rounded-full pl-6 pr-16 py-4 outline-none focus:border-black focus:ring-1 focus:ring-black focus:bg-white transition-all font-medium text-base md:text-lg placeholder-neutral-400 disabled:opacity-60"
              />
              <button
                type="submit"
                disabled={isTyping || isLoading || !input.trim()}
                className="absolute right-2 w-12 h-12 bg-black text-white rounded-full flex items-center justify-center hover:bg-neutral-800 transition-colors disabled:opacity-50"
              >
                <Send className="w-5 h-5 ml-1" />
              </button>
            </form>
          </div>
        </div>

      </div>
    </div>
  );
}