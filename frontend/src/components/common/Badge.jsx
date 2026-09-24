import React from 'react';

const VARIANTS = {
  default: 'bg-zinc-800 text-zinc-300 border-zinc-700',
  primary: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20',
  danger: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
  warning: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  success: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  mono: 'bg-zinc-900 text-zinc-400 border-zinc-800 font-mono text-[11px]',
};

export function Badge({ children, variant = 'default', className = '' }) {
  const variantClass = VARIANTS[variant] || VARIANTS.default;
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${variantClass} ${className}`}
    >
      {children}
    </span>
  );
}

export default Badge;
