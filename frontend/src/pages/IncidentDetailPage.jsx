import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useProject } from '../context/ProjectContext';
import api from '../services/api';
import {
  Flame,
  ArrowLeft,
  AlertTriangle,
  CheckCircle2,
  Clock,
  ShieldAlert,
  Sliders,
  Tag,
  AlertOctagon,
  RefreshCw,
  Send,
  UserCheck,
  Check,
  ChevronRight,
  ShieldCheck,
  ZapOff,
} from 'lucide-react';
import { formatRelativeTime, formatExactTimestamp } from '../utils/formatters';

export default function IncidentDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { selectedTenant, user: currentUser } = useAuth();
  const { selectedProject: currentProject } = useProject();

  const [incident, setIncident] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Status Action Loading
  const [isUpdatingStatus, setIsUpdatingStatus] = useState(false);
  const [statusFeedback, setStatusFeedback] = useState(null);

  // Approval Modal State
  const [selectedMitigation, setSelectedMitigation] = useState(null);
  const [showApprovalModal, setShowApprovalModal] = useState(false);
  const [isApproving, setIsApproving] = useState(false);
  const [approvalError, setApprovalError] = useState(null);
  const [approvalSuccess, setApprovalSuccess] = useState(null);

  // Timeline Note State
  const [newNote, setNewNote] = useState('');
  const [isSubmittingNote, setIsSubmittingNote] = useState(false);

  const fetchIncident = useCallback(async () => {
    if (!selectedTenant || !currentProject || !id) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.getIncident(selectedTenant.id, currentProject.id, id);
      setIncident(data);
    } catch (err) {
      setError(err.message || 'Failed to load incident details');
    } finally {
      setLoading(false);
    }
  }, [selectedTenant, currentProject, id]);

  useEffect(() => {
    fetchIncident();
  }, [fetchIncident]);

  const handleStatusChange = async (newStatus) => {
    if (!selectedTenant || !currentProject || !incident) return;
    setIsUpdatingStatus(true);
    setStatusFeedback(null);
    try {
      const updated = await api.updateIncident(selectedTenant.id, currentProject.id, incident.id, {
        status: newStatus,
      });
      setIncident(updated);
      setStatusFeedback({ type: 'success', text: `Incident status updated to '${newStatus}'.` });
    } catch (err) {
      setStatusFeedback({ type: 'error', text: err.message || 'Failed to update status' });
    } finally {
      setIsUpdatingStatus(false);
    }
  };

  const handleAddNote = async (e) => {
    e.preventDefault();
    if (!newNote.trim() || !selectedTenant || !currentProject || !incident) return;
    setIsSubmittingNote(true);
    try {
      await api.addIncidentTimelineNote(selectedTenant.id, currentProject.id, incident.id, {
        message: newNote.trim(),
        event_type: 'note_added',
      });
      setNewNote('');
      fetchIncident();
    } catch (err) {
      console.error('Failed to add note:', err);
    } finally {
      setIsSubmittingNote(false);
    }
  };

  const handleApproveMitigation = async () => {
    if (!selectedTenant || !currentProject || !incident || !selectedMitigation) return;
    setIsApproving(true);
    setApprovalError(null);
    try {
      const result = await api.approveMitigation(
        selectedTenant.id,
        currentProject.id,
        incident.id,
        selectedMitigation.id
      );
      setApprovalSuccess(result);
      setShowApprovalModal(false);
      fetchIncident();
    } catch (err) {
      setApprovalError(err.message || 'Mitigation approval failed');
    } finally {
      setIsApproving(false);
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

  if (loading) {
    return (
      <div className="p-16 text-center text-slate-400">
        <RefreshCw className="w-8 h-8 animate-spin mx-auto mb-3 text-rose-500" />
        Loading incident response dashboard...
      </div>
    );
  }

  if (error || !incident) {
    return (
      <div className="p-12 text-center text-rose-400 space-y-3">
        <AlertTriangle className="w-8 h-8 mx-auto" />
        <h3 className="text-base font-semibold">Incident Not Found</h3>
        <p className="text-xs text-slate-400">{error || 'Could not locate the requested incident.'}</p>
        <button
          onClick={() => navigate('/incidents')}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 text-slate-200 rounded-lg text-xs hover:bg-slate-700 transition"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to Incidents
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Top Navigation & Status Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-800/80 pb-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/incidents')}
            className="p-1.5 text-slate-400 hover:text-slate-200 rounded-lg hover:bg-slate-800 transition cursor-pointer"
            title="Back to Incidents"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <div className="flex flex-wrap items-center gap-2 mb-1">
              <span className="font-mono text-xs text-slate-400 font-semibold">
                INCIDENT #{incident.id}
              </span>
              <span
                className={`px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wider border font-mono ${getSeverityBadge(
                  incident.severity
                )}`}
              >
                {incident.severity}
              </span>
              <span
                className={`px-2 py-0.5 rounded text-[11px] font-medium border font-mono ${getStatusBadge(
                  incident.status
                )}`}
              >
                {incident.status}
              </span>
              <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-slate-800 text-slate-300 border border-slate-700">
                {incident.environment}
              </span>
            </div>
            <h1 className="text-xl font-bold text-slate-100 tracking-tight">{incident.title}</h1>
          </div>
        </div>

        {/* Status Lifecycle Actions */}
        <div className="flex items-center gap-2 flex-wrap">
          {incident.status === 'triggered' && (
            <button
              onClick={() => handleStatusChange('investigating')}
              disabled={isUpdatingStatus}
              className="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 text-white rounded-lg text-xs font-medium transition cursor-pointer disabled:opacity-50"
            >
              Start Investigation
            </button>
          )}

          {incident.status === 'investigating' && (
            <>
              <button
                onClick={() => handleStatusChange('mitigated')}
                disabled={isUpdatingStatus}
                className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-medium transition cursor-pointer disabled:opacity-50"
              >
                Mark Mitigated
              </button>
              <button
                onClick={() => handleStatusChange('resolved')}
                disabled={isUpdatingStatus}
                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-medium transition cursor-pointer disabled:opacity-50"
              >
                Mark Resolved
              </button>
            </>
          )}

          {incident.status === 'mitigated' && (
            <button
              onClick={() => handleStatusChange('resolved')}
              disabled={isUpdatingStatus}
              className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-medium transition cursor-pointer disabled:opacity-50"
            >
              Mark Resolved
            </button>
          )}

          {(incident.status === 'resolved' || incident.status === 'mitigated') && (
            <button
              onClick={() => handleStatusChange('closed')}
              disabled={isUpdatingStatus}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 rounded-lg text-xs font-medium transition cursor-pointer disabled:opacity-50"
            >
              Close Incident
            </button>
          )}

          <button
            onClick={fetchIncident}
            className="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg border border-slate-700 transition cursor-pointer"
            title="Refresh incident"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {statusFeedback && (
        <div
          className={`p-3 rounded-lg text-xs border flex items-center justify-between ${
            statusFeedback.type === 'success'
              ? 'bg-emerald-950/40 border-emerald-800 text-emerald-300'
              : 'bg-rose-950/40 border-rose-800 text-rose-300'
          }`}
        >
          <span>{statusFeedback.text}</span>
          <button onClick={() => setStatusFeedback(null)} className="text-slate-400 hover:text-white">
            ✕
          </button>
        </div>
      )}

      {approvalSuccess && (
        <div className="p-4 bg-emerald-950/40 border border-emerald-800 rounded-xl text-xs text-emerald-300 space-y-1">
          <div className="font-semibold flex items-center gap-1.5 text-sm">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            Mitigation Executed Successfully
          </div>
          <div>{approvalSuccess.message}</div>
          <div className="text-[11px] text-emerald-400 font-mono">
            Status: {approvalSuccess.status} | Idempotent: {String(approvalSuccess.idempotent)}
          </div>
        </div>
      )}

      {/* Structured Sections (Requirement 10) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Analysis, Correlation & Mitigation */}
        <div className="lg:col-span-2 space-y-6">
          {/* SECTION 1: WHAT HAPPENED */}
          <div className="p-5 bg-slate-900 border border-slate-800 rounded-xl space-y-3">
            <div className="flex items-center gap-2 text-rose-400 text-xs font-bold uppercase tracking-wider">
              <Flame className="w-4 h-4" />
              1. What Happened
            </div>
            <p className="text-sm text-slate-200">
              {incident.description || 'No detailed incident description recorded.'}
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 text-xs border-t border-slate-800">
              <div>
                <span className="text-slate-500 block text-[11px]">Started At</span>
                <span className="text-slate-300 font-mono">
                  {formatExactTimestamp(incident.started_at)}
                </span>
                <span className="text-[10px] text-slate-500 block">
                  {formatRelativeTime(incident.started_at)}
                </span>
              </div>

              <div>
                <span className="text-slate-500 block text-[11px]">Linked Error Issue</span>
                {incident.related_issue_id ? (
                  <Link
                    to={`/issues/${incident.related_issue_id}`}
                    className="text-rose-400 hover:text-rose-300 font-mono inline-flex items-center gap-1 mt-0.5"
                  >
                    <AlertOctagon className="w-3.5 h-3.5" />
                    Issue #{incident.related_issue_id}
                  </Link>
                ) : (
                  <span className="text-slate-500 italic">None linked</span>
                )}
                {incident.related_issue_title && (
                  <span className="text-[10px] text-slate-400 block truncate">
                    {incident.related_issue_title}
                  </span>
                )}
              </div>

              <div>
                <span className="text-slate-500 block text-[11px]">Reported / Created By</span>
                <span className="text-slate-300 font-mono text-[11px]">
                  {incident.created_by_email || 'System Detector'}
                </span>
              </div>
            </div>
          </div>

          {/* SECTION 2: WHAT CHANGED RECENTLY (Correlated Candidates) */}
          <div className="p-5 bg-slate-900 border border-slate-800 rounded-xl space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-indigo-400 text-xs font-bold uppercase tracking-wider">
                <Tag className="w-4 h-4" />
                2. What Changed Recently (Correlated Candidates)
              </div>
              <span className="text-[11px] text-slate-500">24-hour lookback window</span>
            </div>
            <p className="text-xs text-slate-400">
              Recent releases and feature flag updates affecting {incident.environment}.
              Correlated candidates are identified without assuming causal certainty.
            </p>

            {incident.correlated_changes && incident.correlated_changes.length > 0 ? (
              <div className="space-y-2 pt-1">
                {incident.correlated_changes.map((change, idx) => (
                  <div
                    key={idx}
                    className="p-3 bg-slate-800/60 border border-slate-700/80 rounded-lg flex items-start justify-between gap-3 text-xs"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        {change.type === 'release' ? (
                          <Tag className="w-3.5 h-3.5 text-indigo-400" />
                        ) : (
                          <Sliders className="w-3.5 h-3.5 text-amber-400" />
                        )}
                        <span className="font-semibold text-slate-200">{change.title}</span>
                        <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-700/80 text-slate-300 font-mono">
                          {change.relationship}
                        </span>
                      </div>
                      <p className="text-slate-400 text-[11px]">{change.description}</p>
                    </div>
                    <span className="text-[11px] text-slate-500 font-mono shrink-0">
                      {formatRelativeTime(change.changed_at)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-4 bg-slate-800/40 rounded-lg text-center text-xs text-slate-500 italic">
                No releases or flag changes detected within the 24-hour lookback window.
              </div>
            )}
          </div>

          {/* SECTION 3: WHAT ACTION IS RECOMMENDED & WHAT WILL HAPPEN */}
          <div className="p-5 bg-slate-900 border border-slate-800 rounded-xl space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-amber-400 text-xs font-bold uppercase tracking-wider">
                <ShieldCheck className="w-4 h-4" />
                3. Recommended Action & Safety Model
              </div>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-amber-500/10 text-amber-400 border border-amber-500/20">
                Advisory Only
              </span>
            </div>

            {incident.mitigations && incident.mitigations.length > 0 ? (
              <div className="space-y-3">
                {incident.mitigations.map((mit) => (
                  <div
                    key={mit.id}
                    className="p-4 bg-slate-800/50 border border-slate-700 rounded-xl space-y-3"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <ZapOff className="w-4 h-4 text-rose-400" />
                        <span className="font-semibold text-slate-100 text-sm">
                          Safe Kill Switch: Flag '{mit.target_flag_key || mit.target_flag_id}'
                        </span>
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                          {Math.round(mit.confidence * 100)}% Confidence
                        </span>
                      </div>
                      <span
                        className={`px-2 py-0.5 rounded text-[11px] font-mono font-medium border self-start sm:self-center ${
                          mit.status === 'executed'
                            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                            : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                        }`}
                      >
                        {mit.status.toUpperCase()}
                      </span>
                    </div>

                    <p className="text-xs text-slate-300">{mit.reason}</p>

                    {/* What will happen explanation */}
                    <div className="p-3 bg-slate-900/80 border border-slate-700/60 rounded-lg text-xs space-y-1">
                      <span className="font-semibold text-slate-300 block">
                        What will happen if approved:
                      </span>
                      <ul className="list-disc list-inside text-slate-400 text-[11px] space-y-0.5">
                        <li>
                          Feature flag <strong className="text-slate-200">{mit.target_flag_key}</strong> will be
                          immediately disabled in <strong className="text-slate-200">{incident.environment}</strong>.
                        </li>
                        <li>Rollout percentage will be forced to 0%.</li>
                        <li>Safe fallback default variant will be delivered deterministically to all users.</li>
                        <li>An immutable audit log and incident timeline entry will record your approval.</li>
                        <li>
                          <strong className="text-emerald-400">Safety Guarantee:</strong> No arbitrary shell,
                          deployment, or database commands will ever be run.
                        </li>
                      </ul>
                    </div>

                    {mit.status === 'executed' ? (
                      <div className="flex items-center gap-2 text-xs text-emerald-400 font-mono">
                        <Check className="w-4 h-4" />
                        Executed at {formatExactTimestamp(mit.executed_at)} by {mit.approved_by_email || 'Authorized Admin'}
                      </div>
                    ) : (
                      <button
                        onClick={() => {
                          setSelectedMitigation(mit);
                          setShowApprovalModal(true);
                        }}
                        className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white rounded-lg text-xs font-semibold transition shadow-sm flex items-center gap-1.5 cursor-pointer"
                      >
                        <ZapOff className="w-3.5 h-3.5" />
                        Review & Approve Kill Switch
                      </button>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-4 bg-slate-800/40 rounded-lg text-center text-xs text-slate-500 italic">
                No active feature flag mitigations currently recommended for this incident.
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Timeline & Notes */}
        <div className="space-y-6">
          <div className="p-5 bg-slate-900 border border-slate-800 rounded-xl space-y-4">
            <h2 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Clock className="w-4 h-4 text-indigo-400" />
              Incident Timeline
            </h2>

            {/* Timeline Stream */}
            <div className="relative pl-5 space-y-4 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-800">
              {incident.timeline && incident.timeline.length > 0 ? (
                incident.timeline.map((ev) => (
                  <div key={ev.id} className="relative text-xs space-y-1">
                    <span className="absolute -left-[1.35rem] top-1 w-2.5 h-2.5 rounded-full bg-indigo-500 border-2 border-slate-900" />
                    <div className="flex items-center justify-between text-[11px] text-slate-500">
                      <span className="font-mono">{formatRelativeTime(ev.created_at)}</span>
                      <span>{ev.actor_email || 'System'}</span>
                    </div>
                    <div className="text-slate-200 font-medium">{ev.message}</div>
                  </div>
                ))
              ) : (
                <div className="text-xs text-slate-500 italic">No timeline events recorded.</div>
              )}
            </div>

            {/* Add Investigation Note */}
            <form onSubmit={handleAddNote} className="pt-3 border-t border-slate-800 space-y-2">
              <label className="block text-xs font-semibold text-slate-400">Add Investigation Note</label>
              <textarea
                rows={2}
                value={newNote}
                onChange={(e) => setNewNote(e.target.value)}
                placeholder="Log observation, root-cause findings, or mitigation status..."
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-rose-500"
              />
              <button
                type="submit"
                disabled={isSubmittingNote || !newNote.trim()}
                className="w-full py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-medium transition flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50"
              >
                <Send className="w-3.5 h-3.5" />
                {isSubmittingNote ? 'Posting...' : 'Post Timeline Note'}
              </button>
            </form>
          </div>
        </div>
      </div>

      {/* Explicit Mitigation Approval Modal */}
      {showApprovalModal && selectedMitigation && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs">
          <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-lg p-6 shadow-2xl space-y-4">
            <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
              <ZapOff className="w-5 h-5 text-rose-500" />
              Confirm Mitigation Approval
            </h2>

            <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-xs text-amber-300">
              <strong>Explicit Human Authorization:</strong> Automatic mitigation is disabled by policy.
              Approving will immediately trigger the feature flag kill switch.
            </div>

            {approvalError && (
              <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-lg text-xs text-rose-400">
                {approvalError}
              </div>
            )}

            <div className="space-y-2 text-xs text-slate-300">
              <div>
                <span className="text-slate-500 block">Target Flag</span>
                <span className="font-mono text-sm font-semibold text-slate-100">
                  {selectedMitigation.target_flag_key || selectedMitigation.target_flag_id}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block">Target Environment</span>
                <span className="font-mono text-slate-200">{incident.environment}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Action</span>
                <span className="font-mono text-slate-200">
                  kill_feature_flag (enabled=False, rollout=0%)
                </span>
              </div>
              <div>
                <span className="text-slate-500 block">Approving Operator</span>
                <span className="font-mono text-slate-200">{currentUser?.email}</span>
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setShowApprovalModal(false)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-sm font-medium transition cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isApproving}
                onClick={handleApproveMitigation}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white rounded-lg text-sm font-semibold transition shadow-sm disabled:opacity-50 cursor-pointer"
              >
                {isApproving ? 'Executing...' : 'Approve & Execute Kill Switch'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
