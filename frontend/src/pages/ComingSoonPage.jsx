import React from 'react';
import { Clock, ArrowLeft } from 'lucide-react';
import { Link } from 'react-router-dom';

export function ComingSoonPage({ title, description, roadmapVersion = 'v0.2' }) {
  return (
    <div className="space-y-6 animate-in fade-in duration-150">
      <div className="flex items-center gap-2 pb-2 border-b border-zinc-800/80">
        <h1 className="text-xl font-bold tracking-tight text-white m-0">{title}</h1>
        <span className="text-[10px] uppercase font-semibold text-zinc-400 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">
          Planned for {roadmapVersion}
        </span>
      </div>

      <div className="p-12 rounded-xl bg-[#0f1118] border border-dashed border-zinc-800 text-center max-w-2xl mx-auto my-12">
        <div className="h-12 w-12 rounded-xl bg-zinc-900 border border-zinc-800 flex items-center justify-center text-indigo-400 mx-auto mb-4">
          <Clock className="h-6 w-6" />
        </div>

        <h2 className="text-base font-semibold text-zinc-100 mb-2">{title} is Coming Soon</h2>
        <p className="text-xs text-zinc-400 leading-relaxed max-w-md mx-auto mb-6">
          {description}
        </p>

        <div className="inline-flex items-center gap-2">
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-medium bg-zinc-900 hover:bg-zinc-800 text-zinc-200 border border-zinc-700 transition"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Return to Overview</span>
          </Link>
          <Link
            to="/issues"
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white transition"
          >
            <span>Explore Active Issues</span>
          </Link>
        </div>
      </div>
    </div>
  );
}

export default ComingSoonPage;
