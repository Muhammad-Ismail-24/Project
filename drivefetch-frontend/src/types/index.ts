export interface Car {
  id: string;
  title?: string;
  make: string;
  model: string;
  year: number;
  price: number | string;
  mileage: number | string;
  fuel_type?: 'petrol' | 'diesel' | 'hybrid' | 'electric' | 'cng';
  transmission?: 'automatic' | 'manual';
  city: string;
  listing_url?: string;
  url?: string;
  image_url?: string;
  images?: string[];
  platform?: string;
  source?: string;
  ai_evaluation?: CarEvaluation | null;
  ai_analysis?: CarEvaluation | null;
  red_flags_json?: string | string[];
  relevance_score?: number;
  score?: number;
}

export interface CarEvaluation {
  score?: number;
  summary?: string;
  pros?: string[];
  cons?: string[];
  red_flags?: string[];
  liquidity_score?: string;
  justification?: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
}

export interface MatchmakerInput {
  budget: number;
  family_size: number;
  commute_km: number;
  fuel_preference: string;
  city: string;
}

export interface CalculatorResult {
  tax_amount: number;
  transfer_fee: number;
  total_cost: number;
}
