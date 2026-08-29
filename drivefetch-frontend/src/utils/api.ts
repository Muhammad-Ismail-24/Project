import axios from 'axios';
import { Car, ChatMessage, CarEvaluation, CalculatorResult } from '../types';

// PROXY FIX: All API requests will now prepend /api. 
// Vercel routes this instantly to your Render backend!
const API_BASE = '/api';

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const searchCars = async (query: string): Promise<Car[]> => {
  const response = await api.post('/search', { query });
  return Array.isArray(response.data) ? response.data : (response.data.listings || []);
};

export const searchCarsStream = async (query: string, onMessage: (data: unknown) => void): Promise<void> => {
  // Uses /api/search/stream perfectly
  const response = await fetch(`${API_BASE}/search/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query })
  });

  const reader = response.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    
    const lines = buffer.split('\n\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const dataStr = line.substring(6);
        try {
          const data = JSON.parse(dataStr);
          onMessage(data);
        } catch (e) {
          // @ts-ignore
          if (import.meta.env.DEV) {
            console.error('Full error for debugging:', e);
          }
          console.error('Error parsing SSE JSON:', e instanceof Error ? e.message : 'Unknown error');
        }
      }
    }
  }
};

export const calculateFuel = async (data: Record<string, unknown>): Promise<CalculatorResult> => {
  const response = await api.post('/calc/fuel', data);
  return response.data;
};

export const calculateTransfer = async (data: Record<string, unknown>): Promise<CalculatorResult> => {
  const response = await api.post('/calc/transfer-fee', data);
  return response.data;
};

export const calculateToken = async (data: Record<string, unknown>): Promise<CalculatorResult> => {
  const response = await api.post('/calc/token-tax', data);
  return response.data;
};

export const chatWithBot = async (messages: ChatMessage[]): Promise<string> => {
  const response = await api.post('/chat', { messages });
  return response.data.reply;
};

export const evaluateSingleCar = async (listingData: Car, userQuery: string, signal: AbortSignal | null = null): Promise<CarEvaluation | null> => {
  try {
    const response = await api.post('/evaluate-single', {
      title: listingData.title,
      price: typeof listingData.price === 'number' ? listingData.price : parseInt(String(listingData.price).replace(/\D/g, '')) || 0,
      mileage: typeof listingData.mileage === 'number' ? listingData.mileage : parseInt(String(listingData.mileage).replace(/\D/g, '')) || 0,
      year: typeof listingData.year === 'number' ? listingData.year : parseInt(String(listingData.year)) || 0,
      city: listingData.city || '',
      platform: listingData.platform || '',
      user_query: userQuery,
    }, {
      signal: signal || undefined,
      timeout: 15000,
    });
    return response.data;
  } catch (err: unknown) {
    if (axios.isCancel(err) || (err instanceof Error && err.name === 'CanceledError')) {
      return null;
    }
    // @ts-ignore
    if (import.meta.env.DEV) {
      console.error('Full error for debugging:', err);
    }
    console.error('[evaluateSingleCar] API error:', err instanceof Error ? err.message : 'Unknown error');
    return {
      red_flags: [],
      liquidity_score: 'Medium',
      justification: 'AI appraisal is currently unavailable. Please try again later.',
    };
  }
};

export default api;
