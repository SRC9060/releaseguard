import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { useProject } from '../context/ProjectContext';
import api from '../services/api';
import { Tag, Plus, GitCommit, Calendar, Filter, AlertCircle, CheckCircle, RefreshCw } from 'lucide-react';

export default function ReleasesPage() {
  const { selectedTenant } = useAuth();
  const { selectedProject: currentProject } = useProject();

  const [releases, setReleases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [envFilter, setEnvFilter] = useState('');

  // Create Release Modal State
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newVersion, setNewVersion] = useState('');
  const [newEnv, setNewEnv] = useState('production');
  const [newCommitSha, setNewCommitSha] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  const fetchReleases = async () => {
    if (!selectedTenant || !currentProject) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.getReleases(
        selectedTenant.id,
        currentProject.id,
        envFilter || null
      );
      setReleases(data);
    } catch (err) {
      setError(err.message || 'Failed to load releases');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReleases();
  }, [selectedTenant, currentProject, envFilter]);

  const handleCreateRelease = async (e) => {
    e.preventDefault();
    if (!newVersion.trim()) return;
    setSubmitting(true);
    setFormError(null);
    try {
      await api.createRelease(selectedTenant.id, currentProject.id, {
        version: newVersion.trim(),
        environment: newEnv,
        commit_sha: newCommitSha.trim() || null,
      });
      setShowCreateModal(false);
      setNewVersion('');
      setNewCommitSha('');
      fetchReleases();
    } catch (err) {
      setFormError(err.message || 'Failed to create release');
    } finally {
      setSubmitting(false);
    }
  };

  const getEnvBadgeClass = (env) => {
    switch (env?.toLowerCase()) {
      case 'production':
        return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
      case 'staging':
        return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
      default:
        return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 tracking-tight flex items-center gap-2.5">
            <Tag className="w-6 h-6 text-indigo-400" />
            Release Tracking
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Track and correlate software deployment versions across environments
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={fetchReleases}
            className="p-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg border border-slate-700 transition"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium transition shadow-lg shadow-indigo-600/20"
          >
            <Plus className="w-4 h-4" />
            Create Release
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 bg-slate-900/60 p-3 rounded-xl border border-slate-800">
        <Filter className="w-4 h-4 text-slate-400 ml-1" />
        <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Environment:</span>
        <div className="flex items-center gap-1.5">
          {['', 'production', 'staging', 'development'].map((env) => (
            <button
              key={env}
              onClick={() => setEnvFilter(env)}
              className={`px-3 py-1 rounded-md text-xs font-medium transition capitalize ${
                envFilter === env
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              {env || 'All'}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      {error && (
        <div className="p-4 bg-rose-500/10 border border-rose-500/20 rounded-xl text-sm text-rose-400 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center p-16">
          <RefreshCw className="w-8 h-8 text-indigo-400 animate-spin" />
        </div>
      ) : releases.length === 0 ? (
        <div className="text-center p-16 bg-slate-900/40 rounded-xl border border-slate-800/80">
          <Tag className="w-12 h-12 text-slate-600 mx-auto mb-3" />
          <h3 className="text-base font-semibold text-slate-200">No releases deployed yet</h3>
          <p className="text-sm text-slate-400 max-w-sm mx-auto mt-1 mb-6">
            Register your first release build or capture error events containing release metadata.
          </p>
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium transition"
          >
            Create Release
          </button>
        </div>
      ) : (
        <div className="bg-slate-900/60 rounded-xl border border-slate-800 overflow-hidden shadow-xl">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-300">
              <thead className="bg-slate-800/60 text-xs uppercase tracking-wider text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="px-6 py-3.5">Version</th>
                  <th className="px-6 py-3.5">Environment</th>
                  <th className="px-6 py-3.5">Commit SHA</th>
                  <th className="px-6 py-3.5">Deployed At</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {releases.map((rel) => (
                  <tr key={rel.id} className="hover:bg-slate-800/30 transition">
                    <td className="px-6 py-4 font-semibold text-slate-100 flex items-center gap-2">
                      <Tag className="w-4 h-4 text-indigo-400" />
                      {rel.version}
                    </td>
                    <td className="px-6 py-4">
                      <span className={`px-2.5 py-1 rounded-full text-xs font-medium border ${getEnvBadgeClass(rel.environment)}`}>
                        {rel.environment}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-slate-400 font-mono text-xs">
                      {rel.commit_sha ? (
                        <span className="flex items-center gap-1.5">
                          <GitCommit className="w-3.5 h-3.5 text-slate-500" />
                          {rel.commit_sha.slice(0, 8)}
                        </span>
                      ) : (
                        <span className="text-slate-600">—</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-slate-400 text-xs">
                      <span className="flex items-center gap-1.5">
                        <Calendar className="w-3.5 h-3.5 text-slate-500" />
                        {new Date(rel.created_at).toLocaleString()}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Create Release Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md p-6 shadow-2xl space-y-5 animate-in fade-in zoom-in-95 duration-150">
            <div>
              <h2 className="text-lg font-bold text-slate-100">Create New Release</h2>
              <p className="text-xs text-slate-400 mt-0.5">Register a deployment version for {currentProject?.name}</p>
            </div>

            {formError && (
              <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-lg text-xs text-rose-400">
                {formError}
              </div>
            )}

            <form onSubmit={handleCreateRelease} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">Version String *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. 1.4.0 or v2026.09.24"
                  value={newVersion}
                  onChange={(e) => setNewVersion(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-slate-800/80 border border-slate-700/80 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">Environment *</label>
                <select
                  value={newEnv}
                  onChange={(e) => setNewEnv(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-slate-800/80 border border-slate-700/80 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                >
                  <option value="production">Production</option>
                  <option value="staging">Staging</option>
                  <option value="development">Development</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">Commit SHA (optional)</label>
                <input
                  type="text"
                  placeholder="e.g. 7f9a1c8b"
                  value={newCommitSha}
                  onChange={(e) => setNewCommitSha(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-slate-800/80 border border-slate-700/80 rounded-lg text-sm font-mono text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-3">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-sm transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition"
                >
                  {submitting ? 'Creating...' : 'Register Release'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
