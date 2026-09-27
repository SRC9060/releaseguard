import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useProject } from '../context/ProjectContext';
import api from '../services/api';
import {
  Flame,
  AlertTriangle,
  Plus,
  RefreshCw,
  Clock,
  CheckCircle2,
  ChevronRight,
  Filter,
  ShieldAlert,
  Sliders,
  Tag,
  AlertOctagon,
} from 'lucide-react';
import { formatRelativeTime } from '../utils/formatters';

export default function IncidentsPage() {
  const navigate = useNavigate();
  const { selectedTenant } = useAuth();
  const { selectedProject: currentProject } = useProject();

  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState('');
  const [severityFilter, setSeverityFilter] = useState('');
  const [envFilter, setEnvFilter] = useState('');

  // Create Modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newSeverity, setNewSeverity] = useState('high');
  const [newEnv, setNewEnv] = useState('production');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  const fetchIncidents = async () => {
    if (!selectedTenant || !currentProject) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.getIncidents(selectedTenant.id, currentProject.id, {
        status: statusFilter || null,
        severity: severityFilter || null,
        environment: envFilter || null,
      });
      setIncidents(data);
    } catch (err) {
      setError(err.message || 'Failed to load incidents');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIncidents();
  }, [selectedTenant, currentProject, statusFilter, severityFilter, envFilter]);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setSubmitting(true);
    setFormError(null);
    try {
      const created = await api.createIncident(selectedTenant.id, currentProject.id, {
        title: newTitle.trim(),
        description: newDesc.trim() || null,
        severity: newSeverity,
        environment: newEnv,
      });
      setShowCreateModal(false);
      setNewTitle('');
      setNewDesc('');
      navigate(`/incidents/${created.id}`);
    } catch (err) {
      setFormError(err.message || 'Failed to create incident');
    } finally {
      setSubmitting(false);
    }
  };

  const getSeverityBadge = (sev) => {
    switch (sev?.toLowerCase()) {
      case 'critical':
        return 'bg-rose-500/10 text-rose-400 border-rose-500/20';
      case 'high':
        return 'bg-orange-500/10 text-orange-400 border-orange-500/20';
      case 'medium':
        return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
      default:
        return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
    }
  };

  const getStatusBadge = (st) => {
    switch (st?.toLowerCase()) {
      case 'triggered':
        return 'bg-rose-500/10 text-rose-400 border-rose-500/30 animate-pulse';
      case 'investigating':
        return 'bg-amber-500/10 text-amber-400 border-amber-500/30';
      case 'mitigated':
        return 'bg-indigo-500/10 text-indigo-400 border-indigo-500/30';
      case 'resolved':
        return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
      case 'closed':
        return 'bg-slate-500/10 text-slate-400 border-slate-500/30';
      default:
        return 'bg-slate-500/10 text-slate-400 border-slate-500/20';
    }
  };

  // Quick metrics
  const activeCount = incidents.filter(
    (i) => i.status === 'triggered' || i.status === 'investigating'
  ).length;
  const criticalCount = incidents.filter(
    (i) => (i.severity === 'critical' || i.severity === 'high') && i.status !== 'closed'
  ).length;
  const mitigatedCount = incidents.filter(
    (i) => i.status === 'mitigated' || i.status === 'resolved'
  ).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 tracking-tight flex items-center gap-2.5">
            <Flame className="w-6 h-6 text-rose-500" />
            Incident Response & Mitigation
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Detect error velocity spikes, correlate recent deployments, and execute controlled mitigations
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={fetchIncidents}
            className="p-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg border border-slate-700 transition cursor-pointer"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="inline-flex items-center gap-2 px-3.5 py-2 bg-rose-600 hover:bg-rose-500 text-white rounded-lg text-sm font-medium transition shadow-sm cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            Trigger Incident
          </button>
        </div>
      </div>

      {/* Metrics Banner */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-xl">
          <div className="text-xs font-medium text-slate-400">Active Incidents</div>
          <div className="text-2xl font-bold text-slate-100 mt-1 flex items-center gap-2">
            {activeCount}
            {activeCount > 0 && (
              <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-ping inline-block" />
            )}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">Triggered or currently under investigation</div>
        </div>
        <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-xl">
          <div className="text-xs font-medium text-slate-400">Critical / High Severity</div>
          <div className="text-2xl font-bold text-orange-400 mt-1">{criticalCount}</div>
          <div className="text-[11px] text-slate-500 mt-1">High-impact active failure events</div>
        </div>
        <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-xl">
          <div className="text-xs font-medium text-slate-400">Mitigated / Resolved</div>
          <div className="text-2xl font-bold text-emerald-400 mt-1">{mitigatedCount}</div>
          <div className="text-[11px] text-slate-500 mt-1">Safely mitigated with feature kill switch</div>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="flex flex-wrap items-center gap-3 bg-slate-900/40 p-3 rounded-xl border border-slate-800">
        <Filter className="w-4 h-4 text-slate-400" />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded-lg px-2.5 py-1.5 focus:ring-1 focus:ring-rose-500"
        >
          <option value="">All Statuses</option>
          <option value="triggered">Triggered</option>
          <option value="investigating">Investigating</option>
          <option value="mitigated">Mitigated</option>
          <option value="resolved">Resolved</option>
          <option value="closed">Closed</option>
        </select>

        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
          className="bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded-lg px-2.5 py-1.5 focus:ring-1 focus:ring-rose-500"
        >
          <option value="">All Severities</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>

        <select
          value={envFilter}
          onChange={(e) => setEnvFilter(e.target.value)}
          className="bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded-lg px-2.5 py-1.5 focus:ring-1 focus:ring-rose-500"
        >
          <option value="">All Environments</option>
          <option value="production">production</option>
          <option value="staging">staging</option>
          <option value="development">development</option>
        </select>

        {(statusFilter || severityFilter || envFilter) && (
          <button
            onClick={() => {
              setStatusFilter('');
              setSeverityFilter('');
              setEnvFilter('');
            }}
            className="text-xs text-rose-400 hover:text-rose-300 ml-auto"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Incidents Table / List */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
        {loading ? (
          <div className="p-12 text-center text-slate-400">
            <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-rose-500" />
            Loading incidents...
          </div>
        ) : error ? (
          <div className="p-8 text-center text-rose-400">
            <AlertTriangle className="w-6 h-6 mx-auto mb-2" />
            {error}
          </div>
        ) : incidents.length === 0 ? (
          <div className="p-12 text-center text-slate-500">
            <ShieldAlert className="w-10 h-10 mx-auto mb-3 opacity-30 text-rose-400" />
            <h3 className="text-sm font-semibold text-slate-300">No active incidents found</h3>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              System is operating within error baseline thresholds. Create a manual incident or simulate an error spike.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-slate-800/80">
            {incidents.map((inc) => (
              <div
                key={inc.id}
                onClick={() => navigate(`/incidents/${inc.id}`)}
                className="p-4 hover:bg-slate-800/40 transition cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-3 group"
              >
                <div className="space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wider border font-mono ${getSeverityBadge(
                        inc.severity
                      )}`}
                    >
                      {inc.severity}
                    </span>
                    <span
                      className={`px-2 py-0.5 rounded text-[11px] font-medium border font-mono ${getStatusBadge(
                        inc.status
                      )}`}
                    >
                      {inc.status}
                    </span>
                    <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-slate-800 text-slate-300 border border-slate-700">
                      {inc.environment}
                    </span>
                    <span className="text-xs text-slate-500 flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {formatRelativeTime(inc.started_at)}
                    </span>
                  </div>

                  <h3 className="text-base font-semibold text-slate-200 group-hover:text-rose-400 transition">
                    #{inc.id} {inc.title}
                  </h3>

                  {inc.description && (
                    <p className="text-xs text-slate-400 line-clamp-1">{inc.description}</p>
                  )}

                  {/* Connected Resources Badges */}
                  <div className="flex flex-wrap items-center gap-2 pt-1 text-xs">
                    {inc.related_issue_id && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 font-mono text-[11px]">
                        <AlertOctagon className="w-3 h-3 text-rose-400" />
                        Issue #{inc.related_issue_id}
                      </span>
                    )}
                    {inc.related_release_version && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 font-mono text-[11px]">
                        <Tag className="w-3 h-3 text-indigo-400" />
                        Release v{inc.related_release_version}
                      </span>
                    )}
                    {inc.related_feature_flag_key && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 font-mono text-[11px]">
                        <Sliders className="w-3 h-3 text-amber-400" />
                        Flag: {inc.related_feature_flag_key}
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2 self-end sm:self-center">
                  <span className="text-xs text-slate-400 group-hover:text-slate-200 transition flex items-center gap-1">
                    Investigate
                    <ChevronRight className="w-4 h-4" />
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Create Incident Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs">
          <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-lg p-6 shadow-2xl space-y-4">
            <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
              <Flame className="w-5 h-5 text-rose-500" />
              Declare New Incident
            </h2>
            <p className="text-xs text-slate-400">
              Declare an incident to track error velocity surges, review correlated deployments, and recommend controlled mitigations.
            </p>

            {formError && (
              <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-lg text-xs text-rose-400">
                {formError}
              </div>
            )}

            <form onSubmit={handleCreate} className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Incident Title *
                </label>
                <input
                  type="text"
                  required
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder="e.g. Payment Gateway Error Spike after v2.4.1"
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-1 focus:ring-rose-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    Severity Level
                  </label>
                  <select
                    value={newSeverity}
                    onChange={(e) => setNewSeverity(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:ring-1 focus:ring-rose-500"
                  >
                    <option value="critical">Critical (Outage)</option>
                    <option value="high">High (Elevated Errors)</option>
                    <option value="medium">Medium (Degraded)</option>
                    <option value="low">Low (Minor Impact)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    Target Environment
                  </label>
                  <select
                    value={newEnv}
                    onChange={(e) => setNewEnv(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:ring-1 focus:ring-rose-500"
                  >
                    <option value="production">production</option>
                    <option value="staging">staging</option>
                    <option value="development">development</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Initial Summary / Observations
                </label>
                <textarea
                  rows={3}
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  placeholder="Describe observed failure symptoms, impacted customers, or initial hypothesis..."
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-1 focus:ring-rose-500"
                />
              </div>

              <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-sm font-medium transition cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting || !newTitle.trim()}
                  className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white rounded-lg text-sm font-medium transition shadow-sm disabled:opacity-50 cursor-pointer"
                >
                  {submitting ? 'Triggering...' : 'Trigger Incident'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
