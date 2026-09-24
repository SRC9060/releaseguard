import React, { useState, useRef, useEffect } from 'react';
import { Building2, ChevronDown, Check, Plus, Shield } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';

export function TenantSelector() {
  const { tenants, selectedTenant, selectTenant, createTenant } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [newTenantName, setNewTenantName] = useState('');
  const [createError, setCreateError] = useState(null);
  const dropdownRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
        setIsCreating(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleCreateTenant = async (e) => {
    e.preventDefault();
    if (!newTenantName.trim()) return;

    setCreateError(null);
    try {
      await createTenant(newTenantName.trim());
      setNewTenantName('');
      setIsCreating(false);
      setIsOpen(false);
    } catch (err) {
      setCreateError(err.message || 'Failed to create organization');
    }
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-zinc-200 bg-zinc-900/90 hover:bg-zinc-800/90 border border-zinc-700/80 rounded-lg transition shadow-xs cursor-pointer"
      >
        <div className="p-1 rounded bg-indigo-500/10 text-indigo-400">
          <Building2 className="h-3.5 w-3.5" />
        </div>
        <span className="max-w-[130px] truncate font-semibold">
          {selectedTenant ? selectedTenant.name : 'Select Org'}
        </span>
        {selectedTenant?.role && (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-mono uppercase font-semibold bg-zinc-800 text-indigo-300 border border-zinc-700">
            {selectedTenant.role}
          </span>
        )}
        <ChevronDown className="h-3.5 w-3.5 text-zinc-400 ml-0.5" />
      </button>

      {isOpen && (
        <div className="absolute left-0 mt-1.5 w-64 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl z-50 overflow-hidden animate-in fade-in zoom-in-95 duration-100">
          <div className="p-2 border-b border-zinc-800/80">
            <span className="text-[11px] font-medium uppercase tracking-wider text-zinc-400 px-2">
              Organizations
            </span>
          </div>

          <div className="max-h-60 overflow-y-auto p-1">
            {tenants.map((t) => {
              const isSelected = selectedTenant?.id === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => {
                    selectTenant(t.id);
                    setIsOpen(false);
                  }}
                  className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs transition cursor-pointer ${
                    isSelected
                      ? 'bg-indigo-600/15 text-indigo-300 font-medium'
                      : 'text-zinc-300 hover:bg-zinc-800/60'
                  }`}
                >
                  <div className="flex items-center gap-2 truncate">
                    <Building2 className={`h-3.5 w-3.5 ${isSelected ? 'text-indigo-400' : 'text-zinc-500'}`} />
                    <span className="truncate">{t.name}</span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className="text-[10px] text-zinc-400 uppercase font-mono">{t.role}</span>
                    {isSelected && <Check className="h-3.5 w-3.5 text-indigo-400" />}
                  </div>
                </button>
              );
            })}
          </div>

          {isCreating ? (
            <form onSubmit={handleCreateTenant} className="p-2 border-t border-zinc-800 bg-zinc-950/60 space-y-2">
              <input
                type="text"
                placeholder="Organization name..."
                value={newTenantName}
                onChange={(e) => setNewTenantName(e.target.value)}
                autoFocus
                className="w-full px-2.5 py-1 text-xs bg-zinc-900 border border-zinc-700 rounded text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-indigo-500"
              />
              {createError && <p className="text-[10px] text-rose-400 m-0">{createError}</p>}
              <div className="flex items-center justify-end gap-1.5">
                <button
                  type="button"
                  onClick={() => setIsCreating(false)}
                  className="px-2 py-0.5 text-[11px] text-zinc-400 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-2.5 py-0.5 text-[11px] bg-indigo-600 hover:bg-indigo-500 text-white font-medium rounded"
                >
                  Create
                </button>
              </div>
            </form>
          ) : (
            <div className="p-1.5 border-t border-zinc-800/80 bg-zinc-950/40">
              <button
                type="button"
                onClick={() => setIsCreating(true)}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-indigo-400 hover:text-indigo-300 hover:bg-indigo-500/10 rounded-lg transition font-medium cursor-pointer"
              >
                <Plus className="h-3.5 w-3.5" />
                <span>New Organization</span>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default TenantSelector;
