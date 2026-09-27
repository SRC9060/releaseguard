import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronDown, Check, Plus, Folder, Loader2 } from 'lucide-react';
import { useProject } from '../../context/ProjectContext';
import CreateProjectModal from './CreateProjectModal';

export function ProjectSelector() {
  const navigate = useNavigate();
  const { projects, selectedProject, selectProject, isLoading } = useProject();
  const [isOpen, setIsOpen] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const dropdownRef = useRef(null);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <>
      <div className="relative" ref={dropdownRef}>
        <button
          type="button"
          onClick={() => setIsOpen(!isOpen)}
          className="flex items-center gap-2.5 px-3 py-1.5 text-xs font-medium text-zinc-200 bg-zinc-900/90 hover:bg-zinc-800/90 border border-zinc-700/80 rounded-lg transition shadow-xs"
        >
          <div className="p-1 rounded bg-indigo-500/10 text-indigo-400">
            <Folder className="h-3.5 w-3.5" />
          </div>
          <span className="max-w-[140px] truncate font-semibold">
            {isLoading ? (
              <span className="flex items-center gap-1.5 text-zinc-400">
                <Loader2 className="h-3 w-3 animate-spin" /> Loading...
              </span>
            ) : selectedProject ? (
              selectedProject.name
            ) : (
              'Select Project'
            )}
          </span>
          {selectedProject && (
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-zinc-800 text-zinc-400 border border-zinc-700">
              #{selectedProject.id}
            </span>
          )}
          <ChevronDown className="h-3.5 w-3.5 text-zinc-400 ml-0.5" />
        </button>

        {isOpen && (
          <div className="absolute left-0 mt-1.5 w-64 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl z-50 overflow-hidden animate-in fade-in zoom-in-95 duration-100">
            <div className="p-2 border-b border-zinc-800/80">
              <span className="text-[11px] font-medium uppercase tracking-wider text-zinc-400 px-2">
                Projects
              </span>
            </div>

            <div className="max-h-60 overflow-y-auto p-1">
              {projects.length === 0 ? (
                <div className="px-3 py-3 text-center text-xs text-zinc-500">
                  No projects found. Create one below.
                </div>
              ) : (
                projects.map((proj) => {
                  const isSelected = selectedProject?.id === proj.id;
                  return (
                    <button
                      key={proj.id}
                      onClick={() => {
                        selectProject(proj);
                        setIsOpen(false);
                      }}
                      className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs transition ${
                        isSelected
                          ? 'bg-indigo-600/15 text-indigo-300 font-medium'
                          : 'text-zinc-300 hover:bg-zinc-800/60'
                      }`}
                    >
                      <div className="flex items-center gap-2 truncate">
                        <Folder className={`h-3.5 w-3.5 ${isSelected ? 'text-indigo-400' : 'text-zinc-500'}`} />
                        <span className="truncate">{proj.name}</span>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <span className="font-mono text-[10px] text-zinc-400">#{proj.id}</span>
                        {isSelected && <Check className="h-3.5 w-3.5 text-indigo-400" />}
                      </div>
                    </button>
                  );
                })
              )}
            </div>

            <div className="p-1.5 border-t border-zinc-800/80 bg-zinc-950/40 space-y-1">
              <button
                type="button"
                onClick={() => {
                  setIsOpen(false);
                  navigate('/projects');
                }}
                className="w-full flex items-center justify-between px-3 py-1.5 text-xs text-zinc-300 hover:text-white hover:bg-zinc-800/60 rounded-lg transition"
              >
                <span>Manage All Projects</span>
                <span className="text-[10px] text-zinc-500 font-mono">→</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  setIsOpen(false);
                  setIsModalOpen(true);
                }}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-indigo-400 hover:text-indigo-300 hover:bg-indigo-500/10 rounded-lg transition font-medium"
              >
                <Plus className="h-3.5 w-3.5" />
                <span>Create New Project</span>
              </button>
            </div>
          </div>
        )}
      </div>

      <CreateProjectModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
      />
    </>
  );
}

export default ProjectSelector;
