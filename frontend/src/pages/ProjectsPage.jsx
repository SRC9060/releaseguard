import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useProject } from '../context/ProjectContext';
import api from '../services/api';
import {
  FolderGit2,
  Plus,
  RefreshCw,
  AlertCircle,
  Check,
  Copy,
  Key,
  Layers,
  Tag,
  AlertOctagon,
  ArrowRight,
  ShieldAlert,
  Loader2,
  ExternalLink,
} from 'lucide-react';

export default function ProjectsPage() {
  const navigate = useNavigate();
  const { selectedTenant } = useAuth();
  const {
    projects,
    selectedProject,
    selectProject,
    refreshProjects,
    isLoading: isProjectLoading,
  } = useProject();

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [projectName, setProjectName] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState(null);
  const [copiedKeyId, setCopiedKeyId] = useState(null);
  const [copyError, setCopyError] = useState(null);

  // Check RBAC permission for project creation and credential access (owner or admin)
  const userRole = selectedTenant?.role || 'member';
  const canCreate = userRole === 'owner' || userRole === 'admin';

  const handleCopyKey = async (e, project) => {
    e.stopPropagation();
    if (!canCreate) {
      setCopyError('Permission denied: Only organization owners and administrators can copy ingestion credentials.');
      setTimeout(() => setCopyError(null), 4000);
      return;
    }
    setCopyError(null);
    try {
      const keyData = await api.getProjectKey(selectedTenant.id, project.id);
      if (keyData?.api_key) {
        navigator.clipboard.writeText(keyData.api_key);
        setCopiedKeyId(project.id);
        setTimeout(() => setCopiedKeyId(null), 2000);
      }
    } catch (err) {
      setCopyError(err.message || 'Permission denied: Insufficient permissions to copy credentials.');
      setTimeout(() => setCopyError(null), 4000);
    }
  };

  const handleCreateProject = async (e) => {
    e.preventDefault();
    if (!projectName.trim() || !selectedTenant) return;

    setCreating(true);
    setCreateError(null);
    try {
      const created = await api.createTenantProject(selectedTenant.id, projectName.trim());
      await refreshProjects();
      selectProject(created);
      setShowCreateModal(false);
      setProjectName('');
      // Navigate to integration tab of new project
      navigate(`/projects/${created.id}?tab=integration`);
    } catch (err) {
      setCreateError(err.message || 'Failed to create project');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 tracking-tight flex items-center gap-2.5">
            <FolderGit2 className="w-6 h-6 text-indigo-400" />
            Projects
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Manage software projects, API credentials, and integration onboarding for{' '}
            <span className="font-semibold text-slate-300">{selectedTenant?.name || 'Workspace'}</span>.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => refreshProjects()}
            className="p-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg border border-slate-700 transition"
            title="Refresh Projects"
          >
            <RefreshCw className={`w-4 h-4 ${isProjectLoading ? 'animate-spin' : ''}`} />
          </button>
          
          <button
            onClick={() => setShowCreateModal(true)}
            disabled={!canCreate}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition shadow-lg ${
              canCreate
                ? 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-600/20'
                : 'bg-slate-800 text-slate-500 border border-slate-700/80 cursor-not-allowed'
            }`}
            title={canCreate ? 'Create new project' : 'Requires Tenant Admin or Owner permission'}
          >
            <Plus className="w-4 h-4" />
            Create Project
          </button>
        </div>
      </div>

      {!canCreate && (
        <div className="p-3 bg-indigo-950/20 border border-indigo-800/30 rounded-xl text-xs text-indigo-300 flex items-center gap-2.5">
          <ShieldAlert className="w-4 h-4 text-indigo-400 shrink-0" />
          <span>You have <strong>{userRole}</strong> permissions in this workspace. Only Admins and Owners can create or modify projects.</span>
        </div>
      )}

      {copyError && (
        <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-xs text-rose-300 flex items-center gap-2.5 animate-in fade-in">
          <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
          <span>{copyError}</span>
        </div>
      )}

      {error && (
        <div className="p-4 bg-rose-500/10 border border-rose-500/20 rounded-xl text-sm text-rose-400 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 shrink-0" />
          {error}
        </div>
      )}

      {/* Projects List */}
      {isProjectLoading ? (
        <div className="flex flex-col items-center justify-center p-16 bg-slate-900/40 rounded-xl border border-slate-800/80">
          <Loader2 className="w-8 h-8 text-indigo-400 animate-spin mb-3" />
          <p className="text-sm text-slate-400">Loading workspace projects...</p>
        </div>
      ) : projects.length === 0 ? (
        <div className="text-center p-16 bg-slate-900/40 rounded-xl border border-slate-800/80">
          <FolderGit2 className="w-12 h-12 text-slate-600 mx-auto mb-3" />
          <h3 className="text-base font-semibold text-slate-200">No projects in this workspace yet</h3>
          <p className="text-sm text-slate-400 max-w-sm mx-auto mt-1 mb-6">
            Create your first project to receive an ingestion API key and connect your applications.
          </p>
          {canCreate && (
            <button
              onClick={() => setShowCreateModal(true)}
              className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium transition shadow-lg shadow-indigo-600/20"
            >
              <Plus className="w-4 h-4" />
              Create First Project
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {projects.map((project) => {
            const isSelected = selectedProject?.id === project.id;
            return (
              <div
                key={project.id}
                onClick={() => selectProject(project)}
                className={`relative flex flex-col justify-between p-5 rounded-xl border transition cursor-pointer group ${
                  isSelected
                    ? 'bg-slate-900/90 border-indigo-500/60 shadow-lg shadow-indigo-500/10'
                    : 'bg-slate-900/50 border-slate-800 hover:border-slate-700 hover:bg-slate-900/80'
                }`}
              >
                <div>
                  {/* Top Bar with Badge & Active indicator */}
                  <div className="flex items-center justify-between gap-2 mb-3">
                    <span className="font-mono text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                      #{project.id}
                    </span>
                    {isSelected ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded-full border border-indigo-500/30">
                        <Check className="w-3 h-3" /> Active Project
                      </span>
                    ) : (
                      <span className="text-[11px] font-medium text-slate-500 group-hover:text-slate-400">
                        Click to activate
                      </span>
                    )}
                  </div>

                  {/* Project Name */}
                  <h3 className="text-base font-semibold text-slate-100 group-hover:text-indigo-300 transition truncate">
                    {project.name}
                  </h3>

                  {/* API Key preview (masked) */}
                  <div className="mt-3 flex items-center justify-between p-2 rounded-lg bg-slate-950/60 border border-slate-800/80 text-xs font-mono text-slate-400">
                    <div className="flex items-center gap-1.5 truncate">
                      <Key className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                      <span className="truncate">
                        {project.api_key
                          ? `${project.api_key.slice(0, 10)}••••••••••••`
                          : 'Credential protected'}
                      </span>
                    </div>
                    {project.api_key && (
                      <button
                        onClick={(e) => handleCopyKey(e, project)}
                        className="p-1 hover:text-slate-200 text-slate-500 transition rounded"
                        title="Copy API Key"
                      >
                        {copiedKeyId === project.id ? (
                          <Check className="w-3.5 h-3.5 text-emerald-400" />
                        ) : (
                          <Copy className="w-3.5 h-3.5" />
                        )}
                      </button>
                    )}
                  </div>

                  {/* Metrics & Summaries */}
                  <div className="mt-4 grid grid-cols-3 gap-2 py-3 border-y border-slate-800/80 text-center">
                    <div>
                      <div className="text-[11px] text-slate-500 uppercase tracking-wider font-medium flex items-center justify-center gap-1">
                        <AlertOctagon className="w-3 h-3" /> Issues
                      </div>
                      <div className="text-sm font-semibold text-slate-200 mt-0.5">
                        {project.issues_count ?? 0}
                      </div>
                    </div>
                    <div>
                      <div className="text-[11px] text-slate-500 uppercase tracking-wider font-medium flex items-center justify-center gap-1">
                        <Layers className="w-3 h-3" /> Envs
                      </div>
                      <div className="text-sm font-semibold text-slate-200 mt-0.5">
                        {project.environments_count ?? 3}
                      </div>
                    </div>
                    <div>
                      <div className="text-[11px] text-slate-500 uppercase tracking-wider font-medium flex items-center justify-center gap-1">
                        <Tag className="w-3 h-3" /> Release
                      </div>
                      <div className="text-xs font-semibold text-slate-300 mt-1 truncate" title={project.recent_release || 'None'}>
                        {project.recent_release || '—'}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Footer Actions */}
                <div className="mt-4 pt-2 flex items-center justify-between gap-3">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(`/projects/${project.id}?tab=integration`);
                    }}
                    className="inline-flex items-center gap-1.5 text-xs font-medium text-indigo-400 hover:text-indigo-300 transition"
                  >
                    <span>Integration SDK</span>
                    <ExternalLink className="w-3.5 h-3.5" />
                  </button>

                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(`/projects/${project.id}`);
                    }}
                    className="inline-flex items-center gap-1 text-xs font-medium px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
                  >
                    <span>Settings</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Create Project Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
          <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl animate-in fade-in zoom-in-95 duration-150">
            <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
              <FolderGit2 className="w-5 h-5 text-indigo-400" />
              Create New Project
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Add a new project to <span className="font-semibold text-slate-300">{selectedTenant?.name}</span> to generate an ingestion key.
            </p>

            {createError && (
              <div className="mt-4 p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl text-xs text-rose-400 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{createError}</span>
              </div>
            )}

            <form onSubmit={handleCreateProject} className="mt-5 space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Project Name <span className="text-rose-400">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="e.g. Payments Microservice, Web App"
                  className="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-3">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  disabled={creating}
                  className="px-4 py-2 rounded-xl text-sm font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800/80 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating || !projectName.trim()}
                  className="flex items-center gap-2 px-5 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl text-sm font-medium transition shadow-lg shadow-indigo-600/20"
                >
                  {creating && <Loader2 className="w-4 h-4 animate-spin" />}
                  <span>{creating ? 'Creating...' : 'Create Project'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
