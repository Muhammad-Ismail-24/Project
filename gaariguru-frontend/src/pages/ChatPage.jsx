import React, { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, User, Loader2 } from 'lucide-react';
import { chatWithBot } from '../utils/api';

export default function ChatPage() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([
    { role: 'assistant', content: 'Hello! I am your GaariGuru automotive assistant. Ask me anything about car specifications, maintenance costs, or market trends in Pakistan.' }
  ]);
  const [isTyping, setIsTyping] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  
  const chatEndRef = useRef(null);

  // Auto-scroll to bottom of chat feed
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const handleSend = async (e) => {
    e.preventDefault();
    const query = input.trim();
    if (!query || isTyping) return;
    
    // Add user message to state
    const userMsg = { role: 'user', content: query };
    const updatedMessages = [...messages, userMsg];
    setMessages(updatedMessages);
    setInput("");
    setIsTyping(true);
    setErrorMsg(null);
    
    try {
      // Call live chat API
      const replyText = await chatWithBot(updatedMessages);
      setMessages(prev => [...prev, { role: 'assistant', content: replyText }]);
    } catch (err) {
      console.error(err);
      const errMsg = err.response?.data?.detail || "Automotive chat service is temporarily unavailable. Please make sure the backend is running.";
      setErrorMsg(errMsg);
      setMessages(prev => [...prev, { role: 'assistant', content: `⚠️ Error: ${errMsg}` }]);
    } finally {
      setIsTyping(false);
    }
  };

  return (
    <div className="relative z-10 flex flex-col h-[calc(100vh-80px)] max-w-4xl mx-auto px-4 py-6">
      
      {/* Header */}
      <div className="text-center mb-6">
        <h1 className="text-3xl font-black tracking-tight">AI Assistant</h1>
        <p className="text-neutral-500 font-medium">Powered by GaariGuru Intelligence</p>
      </div>

      {/* Chat Feed */}
      <div className="flex-1 overflow-y-auto space-y-6 mb-6 p-4 bg-white/40 backdrop-blur-xl border border-white/50 rounded-3xl shadow-inner scrollbar-hide">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex items-end space-x-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            
            {msg.role === 'assistant' && (
              <div className="w-8 h-8 rounded-full bg-black text-white flex items-center justify-center shrink-0 shadow-md">
                <Sparkles className="w-4 h-4" />
              </div>
            )}

            <div className={`max-w-[75%] p-4 rounded-2xl text-[15px] leading-relaxed font-medium ${
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
        ))}

        {/* Typing Indicator */}
        {isTyping && (
          <div className="flex items-end space-x-3 justify-start">
            <div className="w-8 h-8 rounded-full bg-black text-white flex items-center justify-center shrink-0 shadow-md animate-pulse">
              <Sparkles className="w-4 h-4" />
            </div>
            <div className="bg-white border border-neutral-200 text-neutral-500 p-4 rounded-2xl rounded-bl-none shadow-sm flex items-center space-x-2 text-[15px] font-medium">
              <Loader2 className="w-4 h-4 animate-spin text-black" />
              <span>GaariGuru is thinking...</span>
            </div>
          </div>
        )}
        
        <div ref={chatEndRef} />
      </div>

      {/* Input Area */}
      <form onSubmit={handleSend} className="relative flex items-center shrink-0">
        <input 
          type="text" 
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about fuel averages, common faults, or parts availability..."
          disabled={isTyping}
          className="w-full bg-white/80 backdrop-blur-xl border border-neutral-300 rounded-full pl-6 pr-16 py-4 outline-none focus:border-black shadow-lg transition-colors font-medium text-lg placeholder-neutral-400 disabled:opacity-60"
        />
        <button 
          type="submit"
          disabled={isTyping || !input.trim()}
          className="absolute right-2 w-12 h-12 bg-black text-white rounded-full flex items-center justify-center hover:scale-105 transition-transform disabled:opacity-50"
        >
          <Send className="w-5 h-5 ml-1" />
        </button>
      </form>
      
    </div>
  );
}