import React, { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, User, Loader2, Trash2, Settings } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || 'https://carfinder-project-backend.onrender.com';

// ─── API helpers (inline so no changes needed to utils/api.js) ──────────────

async function fetchHistory() {
  const res = await fetch(`${API_BASE}/api/chat/history`, {
    credentials: 'include',
  });
  if (!res.ok) throw new Error('Failed to fetch history');
  return res.json();   // { agent_name, messages: [{role, content}], is_guest }
}

async function sendMessage(message) {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Chat service unavailable.');
  }
  return res.json();   // { reply, agent_name }
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

async function clearHistory() {
  const res = await fetch(`${API_BASE}/api/chat/history`, {
    method: 'DELETE',
    credentials: 'include',
  });
  if (!res.ok) throw new Error('Failed to clear history');
  return res.json();
}

// ─── Component ───────────────────────────────────────────────────────────────

export default function ChatPage() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([]);
  const [agentName, setAgentName] = useState('GaariGuru Expert');
  const [isGuest, setIsGuest] = useState(true);
  const [isTyping, setIsTyping] = useState(false);
  const [isLoading, setIsLoading] = useState(true);   // loading history on mount

  // Agent name editor state
  const [showNameEditor, setShowNameEditor] = useState(false);
  const [nameInput, setNameInput] = useState('');
  const [nameSaving, setNameSaving] = useState(false);

  const chatEndRef = useRef(null);

  // ── Auto-scroll ────────────────────────────────────────────────────────────
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  // ── Load history on mount ──────────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      try {
        const data = await fetchHistory();
        setAgentName(data.agent_name || 'GaariGuru Expert');
        setIsGuest(data.is_guest);
        setNameInput(data.agent_name || 'GaariGuru Expert');

        if (data.messages && data.messages.length > 0) {
          // Logged-in user with existing history — show it directly
          setMessages(data.messages.map(m => ({ role: m.role, content: m.content })));
        } else {
          // Guest OR logged-in with no history — show default greeting
          const name = data.agent_name || 'GaariGuru Expert';
          setMessages([{
            role: 'assistant',
            content: `Asalam o Alaikum! ${name} here. Which car are you looking to buy or inspect today?`,
          }]);
        }
      } catch {
        // Network error / backend down — show default greeting anyway
        setMessages([{
          role: 'assistant',
          content: "Asalam o Alaikum! GaariGuru Expert here. Which car are you looking to buy or inspect today?",
        }]);
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

  // ── Send message ──────────────────────────────────────────────────────────
  const handleSend = async (e) => {
    e.preventDefault();
    const query = input.trim();
    if (!query || isTyping) return;

    // Append user message immediately for snappy UX
    setMessages(prev => [...prev, { role: 'user', content: query }]);
    setInput('');
    setIsTyping(true);

    try {
      // Send ONLY the new message — server reconstructs context from DB (logged-in)
      // or handles it as a stateless single-turn request (guest)
      const data = await sendMessage(query);
      setMessages(prev => [...prev, { role: 'assistant', content: data.reply }]);
      // Sync agent name in case it changed server-side
      if (data.agent_name) setAgentName(data.agent_name);
    } catch (err) {
      const errMsg = err.message || 'Automotive chat service is temporarily unavailable.';
      setMessages(prev => [...prev, { role: 'assistant', content: `⚠️ ${errMsg}` }]);
    } finally {
      setIsTyping(false);
    }
  };

  // ── Clear history ─────────────────────────────────────────────────────────
  const handleClearHistory = async () => {
    if (!window.confirm('Clear your entire chat history? This cannot be undone.')) return;
    try {
      await clearHistory();
      setMessages([{
        role: 'assistant',
        content: `Asalam o Alaikum! ${agentName} here. Fresh start — which car can I help you with?`,
      }]);
    } catch {
      alert('Failed to clear history. Please try again.');
    }
  };

  // ── Save agent name ───────────────────────────────────────────────────────
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

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="relative z-10 flex flex-col h-[calc(100vh-80px)] max-w-4xl mx-auto px-4 py-6">

      {/* Header */}
      <div className="text-center mb-6 relative">
        <h1 className="text-3xl font-black tracking-tight">AI Assistant</h1>

        {/* Agent name display + editor toggle */}
        <div className="flex items-center justify-center gap-2 mt-1">
          {showNameEditor ? (
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={nameInput}
                onChange={e => setNameInput(e.target.value)}
                maxLength={40}
                className="border border-neutral-300 rounded-full px-3 py-1 text-sm outline-none focus:border-black"
                placeholder="Enter assistant name..."
                onKeyDown={e => e.key === 'Enter' && handleSaveAgentName()}
                autoFocus
              />
              <button
                onClick={handleSaveAgentName}
                disabled={nameSaving}
                className="text-xs bg-black text-white px-3 py-1 rounded-full disabled:opacity-50"
              >
                {nameSaving ? 'Saving...' : 'Save'}
              </button>
              <button
                onClick={() => { setShowNameEditor(false); setNameInput(agentName); }}
                className="text-xs text-neutral-500 px-2"
              >
                Cancel
              </button>
            </div>
          ) : (
            <>
              <p className="text-neutral-500 font-medium">
                {isLoading ? 'Loading...' : `Powered by ${agentName}`}
              </p>
              {/* Only show rename button for logged-in users */}
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

        {/* Clear history button — top-right, logged-in only */}
        {!isGuest && messages.length > 1 && (
          <button
            onClick={handleClearHistory}
            title="Clear chat history"
            className="absolute right-0 top-0 flex items-center gap-1 text-xs text-neutral-400 hover:text-red-500 transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Clear history</span>
          </button>
        )}
      </div>

      {/* Chat Feed */}
      <div className="flex-1 overflow-y-auto space-y-6 mb-6 p-4 bg-white/40 backdrop-blur-xl border border-white/50 rounded-3xl shadow-inner scrollbar-hide">

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
                <div className="w-8 h-8 rounded-full bg-black text-white flex items-center justify-center shrink-0 shadow-md">
                  <Sparkles className="w-4 h-4" />
                </div>
              )}

              <div className={`max-w-[75%] p-4 rounded-2xl text-[15px] leading-relaxed font-medium whitespace-pre-wrap ${
                msg.role === 'user'
                  ? 'bg-black text-white rounded-br-none shadow-md'
                  : 'bg-white border border-neutral-200 text-black rounded-bl-none shadow-sm'
              }`}>
                {msg.content}
              </div>

              {msg.role === 'user' && (
                <div className="w-8 h-8 rounded-full bg-neutral-200 flex items-center justify-center shrink-0">
                  <User className="w-4 h-4 text-neutral-600" />
                </div>
              )}
            </div>
          ))
        )}

        {/* Typing indicator */}
        {isTyping && (
          <div className="flex items-end space-x-3 justify-start">
            <div className="w-8 h-8 rounded-full bg-black text-white flex items-center justify-center shrink-0 shadow-md animate-pulse">
              <Sparkles className="w-4 h-4" />
            </div>
            <div className="bg-white border border-neutral-200 text-neutral-500 p-4 rounded-2xl rounded-bl-none shadow-sm flex items-center space-x-2 text-[15px] font-medium">
              <Loader2 className="w-4 h-4 animate-spin text-black" />
              <span>{agentName} is thinking...</span>
            </div>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* Guest notice */}
      {isGuest && !isLoading && (
        <p className="text-center text-xs text-neutral-400 mb-2">
          Sign in to save your conversation history and customize your assistant's name.
        </p>
      )}

      {/* Input */}
      <form onSubmit={handleSend} className="relative flex items-center shrink-0">
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Ask about fuel averages, common faults, or parts availability..."
          disabled={isTyping || isLoading}
          className="w-full bg-white/80 backdrop-blur-xl border border-neutral-300 rounded-full pl-6 pr-16 py-4 outline-none focus:border-black shadow-lg transition-colors font-medium text-lg placeholder-neutral-400 disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={isTyping || isLoading || !input.trim()}
          className="absolute right-2 w-12 h-12 bg-black text-white rounded-full flex items-center justify-center hover:scale-105 transition-transform disabled:opacity-50"
        >
          <Send className="w-5 h-5 ml-1" />
        </button>
      </form>

    </div>
  );
}
