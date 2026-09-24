import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

export function ErrorState({
  title = 'Something went wrong',
  message = 'An unexpected error occurred while loading this view.',
  onRetry = null,
}) {
  return (
    <div className="flex flex-col items-center justify-center p-8 text-center rounded-xl border border-rose-900/30 bg-rose-950/10 my-4">
      <div className="h-10 w-10 rounded-lg bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400 mb-3">
        <AlertTriangle className="h-5 w-5" />
      </div>
      <h3 className="text-sm font-semibold text-rose-200 mb-1">{title}</h3>
      <p className="text-xs text-rose-300/70 max-w-md mb-4">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-700 transition"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Retry Request
        </button>
      )}
    </div>
  );
}

export default ErrorState;
