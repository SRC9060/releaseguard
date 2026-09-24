import React, { useState } from 'react';
import { Menu, Sparkles, Terminal, Bell } from 'lucide-react';
import ProjectSelector from '../projects/ProjectSelector';
import TestEventModal from '../events/TestEventModal';

export function Header({ onOpenMobile, onEventIngested }) {
  const [isTestModalOpen, setIsTestModalOpen] = useState(false);

  return (
    <>
      <header className="h-16 px-4 md:px-8 border-b border-zinc-800/80 bg-[#090a0f]/90 backdrop-blur-md sticky top-0 z-30 flex items-center justify-between">
        {/* Left side: mobile toggle + project selector */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onOpenMobile}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60 md:hidden transition"
          >
            <Menu className="h-5 w-5" />
          </button>

          <ProjectSelector />
        </div>

        {/* Right side actions */}
        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={() => setIsTestModalOpen(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-indigo-600/15 hover:bg-indigo-600/25 text-indigo-300 border border-indigo-500/30 transition shadow-xs"
          >
            <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
            <span className="hidden sm:inline">Simulate Error</span>
          </button>

          <a
            href="http://127.0.0.1:8000/docs"
            target="_blank"
            rel="noreferrer"
            className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60 border border-zinc-800 transition"
          >
            <Terminal className="h-3.5 w-3.5 text-zinc-400" />
            <span>API Docs</span>
          </a>
        </div>
      </header>

      <TestEventModal
        isOpen={isTestModalOpen}
        onClose={() => setIsTestModalOpen(false)}
        onEventSent={(res) => {
          if (onEventIngested) onEventIngested(res);
        }}
      />
    </>
  );
}

export default Header;
