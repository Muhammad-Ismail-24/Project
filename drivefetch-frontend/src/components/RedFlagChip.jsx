import React from 'react';
import { ShieldAlert, Sparkles } from 'lucide-react';

export default function RedFlagChip({ children, tone = 'danger' }) {
  const toneClasses = {
    danger: 'bg-danger/10 border-danger/30 text-danger',
    warning: 'bg-warn/10 border-warn/30 text-warn',
    positive: 'bg-good/10 border-good/30 text-good',
  }[tone] || 'bg-danger/10 border-danger/30 text-danger';

  const Icon = tone === 'positive' ? Sparkles : ShieldAlert;

  return (
    <span className={`inline-flex items-center gap-1.5 border text-xs font-semibold px-3 py-1 rounded-full ${toneClasses}`}>
      <Icon className="w-3 h-3" />
      {children}
    </span>
  );
}
