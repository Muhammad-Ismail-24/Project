import axios from 'axios';

// 1. Define the base URL dynamically. 
// It uses Vercel's environment variable in production, but falls back to localhost when you are coding on your machine.
const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const searchCars = async (query) => {
  const response = await api.post('/search', { query });
  return Array.isArray(response.data) ? response.data : (response.data.listings || []);
};

export const searchCarsStream = async (query, onMessage) => {
  // 2. We also apply API_BASE here so your streaming fetch call doesn't break in production!
  const response = await fetch(`${API_BASE}/search/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query })
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    
    const lines = buffer.split('\n\n');
    buffer = lines.pop();

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const dataStr = line.substring(6);
        try {
          const data = JSON.parse(dataStr);
          onMessage(data);
        } catch (e) {
          console.error("Error parsing SSE JSON:", e);
        }
      }
    }
  }
};

export const calculateFuel = async (data) => {
  const response = await api.post('/calc/fuel', data);
  return response.data;
};

export const calculateTransfer = async (data) => {
  const response = await api.post('/calc/transfer-fee', data);
  return response.data;
};

export const calculateToken = async (data) => {
  const response = await api.post('/calc/token-tax', data);
  return response.data;
};

export const chatWithBot = async (messages) => {
  const response = await api.post('/chat', { messages });
  return response.data.reply;
};

export default api;