import React, { useState, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import {
  ShieldAlert,
  LayoutDashboard,
  AlertOctagon,
  GitBranch,
  Sliders,
  Flame,
  FolderGit2,
  Settings,
  Circle,
  Activity,
  Layers,
} from 'lucide-react';
import api from '../../services/api';

const NAV_ITEMS = [
  { name: 'Overview', path: '/', icon: LayoutDashboard, isFunctional: true },
  { name: 'Issues', path: '/issues', icon: AlertOctagon, isFunctional: true },
  { name: 'Releases', path: '/releases', icon: GitBranch, isFunctional: false },
  { name: 'Feature Flags', path: '/feature-flags', icon: Sliders, isFunctional: false },
  { name: 'Incidents', path: '/incidents', icon: Flame, isFunctional: false },
  { name: 'Projects', path: '/projects', icon: FolderGit2, isFunctional: false },
  { name: 'Settings', path: '/settings', icon: Settings, isFunctional: false },
];

export function Sidebar({ mobileOpen, onCloseMobile }) {
  const [isBackendHealthy, setIsBackendHealthy] = useState(null);

  useEffect(() => {
    let mounted = true;
    const checkBackend = async () => {
      try {
        await api.checkHealth();
        if (mounted) setIsBackendHealthy(true);
      } catch {
        if (mounted) setIsBackendHealthy(false);
      }
    };

    checkBackend();
    const interval = setInterval(checkBackend, 15000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <>
      {/* Mobile backdrop */}
      {mobileOpen && (
        <div
          onClick={onCloseMobile}
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-xs md:hidden"
        />
      )}

      <aside
        className={`fixed md:sticky top-0 left-0 z-40 h-screen w-64 flex flex-col bg-[#0d0e15] border-r border-zinc-800/80 transition-transform duration-200 ease-in-out md:translate-x-0 ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Brand / Logo */}
        <div className="h-16 flex items-center gap-3 px-6 border-b border-zinc-800/80">
          <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-indigo-500 to-indigo-700 flex items-center justify-center text-white shadow-md shadow-indigo-500/20">
            <ShieldAlert className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-sm tracking-tight text-white">ReleaseGuard</span>
              <span className="px-1.5 py-0.2 rounded text-[10px] font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                v0.1
              </span>
            </div>
            <span className="text-[11px] text-zinc-500 font-medium block">
              Reliability Platform
            </span>
          </div>
        </div>

        {/* Navigation list */}
        <div className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
          <div className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
            Platform
          </div>
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.name}
                to={item.path}
                onClick={onCloseMobile}
                className={({ isActive }) =>
                  `flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium transition group ${
                    isActive
                      ? 'bg-indigo-600/15 text-indigo-300 border border-indigo-500/30 shadow-xs'
                      : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/60'
                  }`
                }
              >
                <div className="flex items-center gap-2.5">
                  <Icon className="h-4 w-4 shrink-0 transition-colors group-hover:text-zinc-200" />
                  <span>{item.name}</span>
                </div>
                {!item.isFunctional && (
                  <span className="text-[9px] uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded bg-zinc-900 text-zinc-500 border border-zinc-800">
                    Soon
                  </span>
                )}
              </NavLink>
            );
          })}
        </div>

        {/* Bottom System Status & User Area */}
        <div className="p-3 border-t border-zinc-800/80 bg-zinc-950/40 space-y-3">
          {/* Backend Status indicator */}
          <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-zinc-900/80 border border-zinc-800/60">
            <div className="flex items-center gap-2 text-xs">
              <span className="relative flex h-2 w-2">
                {isBackendHealthy === true ? (
                  <>
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                  </>
                ) : isBackendHealthy === false ? (
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-rose-500"></span>
                ) : (
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500 animate-pulse"></span>
                )}
              </span>
              <span className="text-zinc-400 font-medium">Backend API</span>
            </div>
            <span
              className={`text-[10px] font-mono uppercase font-semibold ${
                isBackendHealthy === true
                  ? 'text-emerald-400'
                  : isBackendHealthy === false
                  ? 'text-rose-400'
                  : 'text-amber-400'
              }`}
            >
              {isBackendHealthy === true
                ? 'Online'
                : isBackendHealthy === false
                ? 'Offline'
                : 'Connecting'}
            </span>
          </div>

          {/* User profile placeholder */}
          <div className="flex items-center gap-2.5 px-3 py-2 rounded-lg hover:bg-zinc-900/50 transition cursor-default">
            <div className="h-7 w-7 rounded-lg bg-zinc-800 border border-zinc-700/80 flex items-center justify-center text-zinc-300 font-semibold text-xs">
              RG
            </div>
            <div className="flex-1 truncate">
              <div className="text-xs font-medium text-zinc-200 truncate">DevOps Team</div>
              <div className="text-[10px] text-zinc-500 truncate font-mono">admin@releaseguard.local</div>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}

export default Sidebar;
