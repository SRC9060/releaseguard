import React, { useState } from 'react';
import { Menu, Sparkles, Terminal, LogOut, User as UserIcon } from 'lucide-react';
import ProjectSelector from '../projects/ProjectSelector';
import TenantSelector from '../tenants/TenantSelector';
import TestEventModal from '../events/TestEventModal';
import { useAuth } from '../../context/AuthContext';
import { BASE_URL } from '../../services/api';

export function Header({ onOpenMobile, onEventIngested }) {
  const [isTestModalOpen, setIsTestModalOpen] = useState(false);
  const { user, logout, isAuthenticated } = useAuth();

  return (
    <>
      <header className="h-16 px-4 md:px-8 border-b border-zinc-800/80 bg-[#090a0f]/90 backdrop-blur-md sticky top-0 z-30 flex items-center justify-between">
        {/* Left side: mobile toggle + tenant selector + project selector */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onOpenMobile}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60 md:hidden transition"
          >
            <Menu className="h-5 w-5" />
          </button>

          {isAuthenticated && <TenantSelector />}
          <ProjectSelector />
        </div>

        {/* Right side actions */}
        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={() => setIsTestModalOpen(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-indigo-600/15 hover:bg-indigo-600/25 text-indigo-300 border border-indigo-500/30 transition shadow-xs cursor-pointer"
          >
            <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
            <span className="hidden sm:inline">Simulate Error</span>
          </button>

          <a
            href={`${BASE_URL}/docs`}
            target="_blank"
            rel="noreferrer"
            className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60 border border-zinc-800 transition"
          >
            <Terminal className="h-3.5 w-3.5 text-zinc-400" />
            <span>API Docs</span>
          </a>

          {/* User profile & Logout */}
          {isAuthenticated && user && (
            <div className="flex items-center gap-2 pl-2 border-l border-zinc-800">
              <div className="hidden lg:flex items-center gap-1.5 text-xs text-zinc-300">
                <UserIcon className="h-3.5 w-3.5 text-zinc-400" />
                <span className="max-w-[120px] truncate">{user.email}</span>
              </div>
              <button
                type="button"
                onClick={logout}
                title="Log out of ReleaseGuard"
                className="p-1.5 rounded-lg text-zinc-400 hover:text-rose-400 hover:bg-rose-500/10 transition cursor-pointer"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          )}
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
