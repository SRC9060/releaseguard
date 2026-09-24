import React, { useState } from 'react';
import { X, FolderPlus, Loader2 } from 'lucide-react';
import { useProject } from '../../context/ProjectContext';

export function CreateProjectModal({ isOpen, onClose }) {
  const { createProject } = useProject();
  const [name, setName] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;

    setIsSubmitting(true);
    setError(null);
    try {
      await createProject(name.trim());
      setName('');
      onClose();
    } catch (err) {
      setError(err.message || 'Failed to create project');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4">
      <div className="w-full max-w-md bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-md bg-indigo-500/10 text-indigo-400">
              <FolderPlus className="h-4 w-4" />
            </div>
            <h3 className="text-sm font-semibold text-zinc-100">Create New Project</h3>
          </div>
          <button
            onClick={onClose}
            className="text-zinc-500 hover:text-zinc-300 p-1 rounded-md transition"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5">
          {error && (
            <div className="mb-4 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-xs text-rose-300">
              {error}
            </div>
          )}

          <div className="mb-4">
            <label className="block text-xs font-medium text-zinc-400 mb-1.5">
              Project Name
            </label>
            <input
              type="text"
              required
              autoFocus
              placeholder="e.g. checkout-service, api-gateway"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 text-sm bg-zinc-950 border border-zinc-700/80 rounded-lg text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
            />
            <p className="mt-1.5 text-[11px] text-zinc-500">
              ReleaseGuard isolates error grouping, releases, and metrics by project.
            </p>
          </div>

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-zinc-800/80">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-3 py-1.5 text-xs font-medium text-zinc-400 hover:text-zinc-200 transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || !name.trim()}
              className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-medium bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg transition"
            >
              {isSubmitting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Create Project
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default CreateProjectModal;
