import React, { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, User, Loader2, Trash2, Settings, Plus, MessageSquare, X } from 'lucide-react';

// ─── Typing dots — three bouncing spans with staggered delays ─────────────────
// Extracted as a tiny component so it can be used both in the isTyping bubble
// and anywhere else a "pending" state needs to be shown.
function TypingDots() {
  return (
    <span className="flex items-center gap-[5px]" aria-label="Typing">
      <span className="w-2 h-2 rounded-full bg-neutral-400 animate-bounce [animation-delay:0ms]"   />
      <span className="w-2 h-2 rounded-full bg-neutral-400 animate-bounce [animation-delay:160ms]" />
      <span className="w-2 h-2 rounded-full bg-neutral-400 animate-bounce [animation-delay:320ms]" />
    </span>
  );
}

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

async function sendMessage(message, sessionId, guestHistory = []) {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      session_id: sessionId,
      // Send conversation history for guest mode continuity — the backend
      // uses this to give the expert context across the whole browser session.
      // For logged-in users this is ignored (backend reads from DB instead).
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

// ─── Component ───────────────────────────────────────────────────────────────

export default function ChatPage() {
  const [sessionsList, setSessionsList] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);

  // FIX: ref mirrors activeSessionId so handleSend always reads the
  // current session ID synchronously, even if a second message is sent
  // before React has flushed the previous state update. Without this,
  // rapid consecutive messages each get session_id=null and the backend
  // creates a new session for every message instead of continuing the
  // existing one.
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
            // Don't call loadSession here — it sets isLoading=true again
            // inside an already-loading state, causing a double spinner.
            // Set everything directly instead.
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
          // Genuinely a guest — show welcome message
          startNewChat();
        }
      } catch (err) {
        // fetchSessions failed — this usually means Render is cold-starting
        // or there's a network hiccup. DO NOT assume guest. Retry once after
        // 4 seconds to give Render time to wake up.
        console.warn("[ChatPage] fetchSessions failed, retrying in 4s:", err.message);
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
            console.error("[ChatPage] Retry also failed:", retryErr.message);
            // Only NOW fall back to guest mode — after two genuine failures
            startNewChat();
          } finally {
            setIsLoading(false);
          }
        }, 4000);
        // Keep isLoading=true during the retry window so user sees spinner
        // not a broken guest UI while Render wakes up
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
      // Pass full message history for guest mode so the expert has
      // context across the whole browser session, not just one message.
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
              <p className="text-xs text-neutral-500 font-medium">
                {isLoading ? 'Loading...' : `Powered by ${agentName}`}
              </p>
              {!isGuest && (
                <button
                  onClick={() => { setNameInput(agentName); setShowNameEditor(true); }}
                  title="Assistant preferences"
                  className="text-neutral-400 hover:text-black transition-colors"
                >
                  <Settings className="w-3.5 h-3.5" />
                </button>
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
            <div className="flex flex-col items-center justify-center h-full text-neutral-400 gap-3">
              <Loader2 className="w-6 h-6 animate-spin text-black" />
              <p className="font-medium text-sm">Loading your conversation...</p>
              <p className="text-xs text-neutral-300">This may take a moment on first load.</p>
            </div>
          ) : (
            messages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex items-end gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {/* ── AI avatar — subtle gradient background + soft glow ring ── */}
                {msg.role === 'assistant' && (
                  <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center
                                  bg-gradient-to-br from-neutral-800 to-black
                                  shadow-[0_0_0_3px_rgba(0,0,0,0.06),0_0_18px_rgba(0,0,0,0.12)]
                                  border border-white/10">
                    <Sparkles className="w-3.5 h-3.5 text-white" />
                  </div>
                )}

                {/* ── Message bubble ── */}
                <div className={`
                  max-w-[85%] md:max-w-[70%]
                  px-5 py-3.5
                  rounded-2xl
                  text-[15px] leading-relaxed font-medium
                  whitespace-pre-wrap break-words
                  ${msg.role === 'user'
                    ? 'bg-neutral-900 text-white rounded-br-sm shadow-sm'
                    : 'bg-white text-neutral-800 rounded-bl-sm border border-neutral-100 shadow-[0_2px_12px_rgba(0,0,0,0.06)]'
                  }
                `}>
                  {msg.content}
                </div>

                {/* ── User avatar ── */}
                {msg.role === 'user' && (
                  <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center
                                  bg-neutral-200 border border-neutral-300">
                    <User className="w-4 h-4 text-neutral-600" />
                  </div>
                )}
              </div>
            ))
          )}

          {isTyping && (
            <div className="flex items-end gap-3 justify-start">
              {/* Same polished avatar as in the message list */}
              <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center
                              bg-gradient-to-br from-neutral-800 to-black
                              shadow-[0_0_0_3px_rgba(0,0,0,0.06),0_0_18px_rgba(0,0,0,0.12)]
                              border border-white/10">
                <Sparkles className="w-3.5 h-3.5 text-white" />
              </div>

              {/* Typing bubble — same geometry as assistant bubbles */}
              <div className="px-5 py-3.5 rounded-2xl rounded-bl-sm
                              bg-white border border-neutral-100
                              shadow-[0_2px_12px_rgba(0,0,0,0.06)]
                              flex items-center gap-2">
                <TypingDots />
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

      {/* ── Settings Slide-over ─────────────────────────────────────────────────
          Rendered at the root level so it layers correctly above the sidebar
          and chat area without being clipped by any overflow:hidden ancestor.

          Backdrop: fixed, full-screen, z-50 so it sits above the sticky header
          (z-10). Clicking it closes the drawer without saving.

          Drawer: slides in from the right via translate-x transform.
          CSS transition handles the animation — no Framer Motion needed here,
          keeping the bundle lean.

          All handleSaveAgentName / updateAgentName logic is unchanged.
      ──────────────────────────────────────────────────────────────────────── */}

      {/* Backdrop */}
      <div
        aria-hidden="true"
        onClick={() => { setShowNameEditor(false); setNameInput(agentName); }}
        className={[
          'fixed inset-0 z-50',
          'bg-black/20 backdrop-blur-sm',
          'transition-opacity duration-300',
          showNameEditor ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none',
        ].join(' ')}
      />

      {/* Drawer panel */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Assistant preferences"
        className={[
          'fixed inset-y-0 right-0 z-50',
          'w-80 lg:w-96',
          'bg-white shadow-2xl',
          'flex flex-col',
          'transition-transform duration-300 ease-out',
          showNameEditor ? 'translate-x-0' : 'translate-x-full',
        ].join(' ')}
      >
        {/* ── Drawer header ── */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-neutral-100">
          <div>
            <h2 className="text-base font-black tracking-tight text-black">
              Assistant Preferences
            </h2>
            <p className="text-xs text-neutral-400 font-medium mt-0.5">
              Personalise your AI expert
            </p>
          </div>
          <button
            onClick={() => { setShowNameEditor(false); setNameInput(agentName); }}
            className="w-8 h-8 flex items-center justify-center rounded-full text-neutral-400 hover:text-black hover:bg-neutral-100 transition-colors"
            aria-label="Close preferences"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* ── Drawer body ── */}
        <div className="flex-1 overflow-y-auto px-6 py-8 space-y-8">

          {/* Agent name field */}
          <div className="space-y-2">
            <label
              htmlFor="agent-name-input"
              className="block text-xs font-black tracking-widest uppercase text-neutral-500"
            >
              Assistant Name
            </label>
            <input
              id="agent-name-input"
              type="text"
              value={nameInput}
              onChange={e => setNameInput(e.target.value)}
              maxLength={40}
              placeholder="e.g. GaariGuru Expert, Ustad Jee…"
              onKeyDown={e => e.key === 'Enter' && handleSaveAgentName()}
              autoFocus={showNameEditor}
              className={[
                'w-full px-4 py-3',
                'rounded-xl border',
                'text-sm font-medium text-black',
                'placeholder-neutral-300',
                'outline-none transition-all duration-200',
                'focus:border-black focus:ring-2 focus:ring-black/8 focus:shadow-md',
                'border-neutral-200 bg-neutral-50 hover:border-neutral-300',
              ].join(' ')}
            />
            <p className="text-xs text-neutral-400">
              This name appears in the header and in the AI's greeting message.
            </p>
          </div>

          {/* Current name preview chip */}
          <div className="rounded-xl bg-neutral-50 border border-neutral-100 px-4 py-3 flex items-center gap-3">
            <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center
                            bg-gradient-to-br from-neutral-800 to-black
                            shadow-[0_0_0_3px_rgba(0,0,0,0.06)]">
              <Sparkles className="w-3.5 h-3.5 text-white" />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-black text-black truncate">
                {nameInput.trim() || 'GaariGuru Expert'}
              </p>
              <p className="text-[11px] text-neutral-400">Preview</p>
            </div>
          </div>

        </div>

        {/* ── Drawer footer — sticky save / cancel ── */}
        <div className="px-6 py-5 border-t border-neutral-100 flex gap-3">
          <button
            onClick={() => { setShowNameEditor(false); setNameInput(agentName); }}
            className="flex-1 py-3 rounded-xl border border-neutral-200 text-sm font-bold text-neutral-600 hover:bg-neutral-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSaveAgentName}
            disabled={nameSaving || !nameInput.trim()}
            className="flex-1 py-3 rounded-xl bg-black text-white text-sm font-bold hover:bg-neutral-800 transition-colors disabled:opacity-50"
          >
            {nameSaving ? 'Saving…' : 'Save'}
          </button>
        </div>

      </div>

    </div>
  );
}