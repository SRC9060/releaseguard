import React from 'react';
import { Loader2 } from 'lucide-react';

export function LoadingSpinner({ size = 'default', text = 'Loading...' }) {
  const sizeClasses = {
    small: 'h-4 w-4',
    default: 'h-6 w-6',
    large: 'h-8 w-8',
  };

  return (
    <div className="flex flex-col items-center justify-center p-8 text-zinc-400">
      <Loader2 className={`${sizeClasses[size] || sizeClasses.default} animate-spin text-indigo-500 mb-2`} />
      {text && <span className="text-xs text-zinc-500 font-medium">{text}</span>}
    </div>
  );
}

export function SkeletonRow({ cols = 4 }) {
  return (
    <tr className="animate-pulse border-b border-zinc-800/60">
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} className="py-4 px-4">
          <div className="h-4 bg-zinc-800/80 rounded w-3/4"></div>
        </td>
      ))}
    </tr>
  );
}

export function SkeletonCard() {
  return (
    <div className="animate-pulse bg-zinc-900/60 border border-zinc-800 rounded-lg p-5">
      <div className="h-3 bg-zinc-800 rounded w-1/3 mb-3"></div>
      <div className="h-7 bg-zinc-800 rounded w-1/2 mb-2"></div>
      <div className="h-2 bg-zinc-800 rounded w-2/3"></div>
    </div>
  );
}
