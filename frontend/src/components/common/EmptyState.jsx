import React from 'react';
import { Inbox } from 'lucide-react';

export function EmptyState({
  icon: Icon = Inbox,
  title = 'No data available',
  description = 'There are no records to display at this time.',
  action = null,
}) {
  return (
    <div className="flex flex-col items-center justify-center p-12 text-center rounded-xl border border-dashed border-zinc-800 bg-zinc-950/40 my-4">
      <div className="h-12 w-12 rounded-xl bg-zinc-900 border border-zinc-800 flex items-center justify-center text-zinc-400 mb-4">
        <Icon className="h-6 w-6" />
      </div>
      <h3 className="text-sm font-semibold text-zinc-200 mb-1">{title}</h3>
      <p className="text-xs text-zinc-500 max-w-sm mb-5 leading-relaxed">{description}</p>
      {action && <div>{action}</div>}
    </div>
  );
}

export default EmptyState;
