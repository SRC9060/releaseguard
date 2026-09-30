import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useProject } from '../context/ProjectContext';
import api from '../services/api';
import {
  Flame,
  ArrowLeft,
  AlertTriangle,
  Clock,
  ShieldCheck,
  AlertOctagon,
  RefreshCw,
  Send,
  CheckCircle,
  Eye,
  Link2,
  Unlink,
  Plus,
  RotateCcw,
  ZapOff,
  ChevronDown,
  ChevronUp,
  Activity,
  Layers,
} from 'lucide-react';
import { formatRelativeTime, formatExactTimestamp } from '../utils/formatters';
import IncidentCopilotSection from '../components/IncidentCopilotSection';

function formatDuration(startedAt, resolvedAt) {
  if (!startedAt) return null;
  const start = new Date(startedAt).getTime();
  const end = resolvedAt ? new Date(resolvedAt).getTime() : Date.now();
  const diffSec = Math.max(0, Math.floor((end - start) / 1000));
  const hours = Math.floor(diffSec / 3600);
  const minutes = Math.floor((diffSec % 3600) / 60);
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m`;
}

export default function IncidentDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { selectedTenant } = useAuth();
  const { selectedProject: currentProject } = useProject();

  const userRole = selectedTenant?.role || 'member';
  const canManage = userRole === 'owner' || userRole === 'admin';

  const [incident, setIncident] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Status Action Loading
  const [isUpdatingStatus, setIsUpdatingStatus] = useState(false);
  const [statusFeedback, setStatusFeedback] = useState(null);

  // Severity Edit State
  const [selectedSeverity, setSelectedSeverity] = useState('');

  // Link Issue Modal State
  const [showLinkModal, setShowLinkModal] = useState(false);
  const [projectIssues, setProjectIssues] = useState([]);
  const [selectedIssueId, setSelectedIssueId] = useState('');
  const [isLinkingIssue, setIsLinkingIssue] = useState(false);
  const [linkError, setLinkError] = useState(null);

  // Apply Mitigation Modal State
  const [showMitigationModal, setShowMitigationModal] = useState(false);
  const [projectFlags, setProjectFlags] = useState([]);
  const [selectedFlagId, setSelectedFlagId] = useState('');
  const [selectedEnvId, setSelectedEnvId] = useState('');
  const [mitigationReason, setMitigationReason] = useState('');
  const [isApplyingMitigation, setIsApplyingMitigation] = useState(false);
  const [mitigationError, setMitigationError] = useState(null);

  // Revert Confirmation Modal State
  const [mitigationToRevert, setMitigationToRevert] = useState(null);
  const [isReverting, setIsReverting] = useState(false);

  // Approval Modal State
  const [selectedMitigation, setSelectedMitigation] = useState(null);
  const [showApprovalModal, setShowApprovalModal] = useState(false);
  const [isApproving, setIsApproving] = useState(false);
  const [approvalError, setApprovalError] = useState(null);

  // Timeline Note State
  const [newNote, setNewNote] = useState('');
  const [isSubmittingNote, setIsSubmittingNote] = useState(false);
  const [expandedEvents, setExpandedEvents] = useState({});

  const toggleEventDetail = (eventId) => {
    setExpandedEvents((prev) => ({ ...prev, [eventId]: !prev[eventId] }));
  };

  const fetchIncident = useCallback(async () => {
    if (!selectedTenant || !currentProject || !id) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.getIncident(selectedTenant.id, currentProject.id, id);
      setIncident(data);
      setSelectedSeverity(data.severity);
    } catch (err) {
      setError(err.message || 'Failed to load incident details');
    } finally {
      setLoading(false);
    }
  }, [selectedTenant, currentProject, id]);

  useEffect(() => {
    fetchIncident();
  }, [fetchIncident]);

  // Load project issues & flags for modals
  const loadProjectResources = async () => {
    if (!selectedTenant || !currentProject) return;
    try {
      const [issuesData, flagsData] = await Promise.allSettled([
        api.getTenantIssues(selectedTenant.id, currentProject.id),
        api.getFeatureFlags ? api.getFeatureFlags(selectedTenant.id, currentProject.id) : Promise.resolve([]),
      ]);
      if (issuesData.status === 'fulfilled') setProjectIssues(issuesData.value || []);
      if (flagsData.status === 'fulfilled') setProjectFlags(flagsData.value || []);
    } catch (e) {
      console.warn('Could not preload project resources for modal', e);
    }
  };

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

  const handleResolveIncident = async () => {
    if (!selectedTenant || !currentProject || !incident) return;
    setIsUpdatingStatus(true);
    setStatusFeedback(null);
    try {
      const updated = await api.resolveIncident(selectedTenant.id, currentProject.id, incident.id);
      setIncident(updated);
      setStatusFeedback({ type: 'success', text: 'Incident successfully resolved.' });
    } catch (err) {
      setStatusFeedback({ type: 'error', text: err.message || 'Failed to resolve incident' });
    } finally {
      setIsUpdatingStatus(false);
    }
  };

  const handleSeverityChange = async (e) => {
    const newSev = e.target.value;
    setSelectedSeverity(newSev);
    if (!selectedTenant || !currentProject || !incident || newSev === incident.severity) return;
    setStatusFeedback(null);
    try {
      const updated = await api.updateIncident(selectedTenant.id, currentProject.id, incident.id, {
        severity: newSev,
      });
      setIncident(updated);
      setStatusFeedback({ type: 'success', text: `Severity changed to '${newSev}'.` });
    } catch (err) {
      setStatusFeedback({ type: 'error', text: err.message || 'Failed to update severity' });
    }
  };

  const handleLinkIssue = async (e) => {
    e.preventDefault();
    if (!selectedIssueId || !selectedTenant || !currentProject || !incident) return;
    setIsLinkingIssue(true);
    setLinkError(null);
    try {
      const updated = await api.linkIncidentIssue(
        selectedTenant.id,
        currentProject.id,
        incident.id,
        parseInt(selectedIssueId, 10)
      );
      setIncident(updated);
      setShowLinkModal(false);
      setSelectedIssueId('');
      setStatusFeedback({ type: 'success', text: 'Issue linked successfully.' });
    } catch (err) {
      setLinkError(err.message || 'Failed to link issue');
    } finally {
      setIsLinkingIssue(false);
    }
  };

  const handleUnlinkIssue = async (issueId) => {
    if (!window.confirm(`Unlink Issue #${issueId} from this incident? The issue itself will remain intact.`)) {
      return;
    }
    try {
      const updated = await api.unlinkIncidentIssue(
        selectedTenant.id,
        currentProject.id,
        incident.id,
        issueId
      );
      setIncident(updated);
      setStatusFeedback({ type: 'success', text: `Issue #${issueId} unlinked from incident.` });
    } catch (err) {
      setStatusFeedback({ type: 'error', text: err.message || 'Failed to unlink issue' });
    }
  };

  const handleApplyMitigation = async (e) => {
    e.preventDefault();
    if (!selectedFlagId || !selectedTenant || !currentProject || !incident) return;
    setIsApplyingMitigation(true);
    setMitigationError(null);
    try {
      const result = await api.applyIncidentMitigation(
        selectedTenant.id,
        currentProject.id,
        incident.id,
        {
          target_flag_id: parseInt(selectedFlagId, 10),
          target_environment_id: selectedEnvId ? parseInt(selectedEnvId, 10) : null,
          reason: mitigationReason.trim() || undefined,
        }
      );
      setShowMitigationModal(false);
      setSelectedFlagId('');
      setSelectedEnvId('');
      setMitigationReason('');
      setStatusFeedback({
        type: 'success',
        text: `Mitigation applied: ${result.message || 'Flag disabled and rollout set to 0%.'}`,
      });
      fetchIncident();
    } catch (err) {
      setMitigationError(err.message || 'Failed to apply mitigation');
    } finally {
      setIsApplyingMitigation(false);
    }
  };

  const handleRevertMitigation = async () => {
    if (!mitigationToRevert || !selectedTenant || !currentProject || !incident) return;
    setIsReverting(true);
    try {
      const result = await api.revertIncidentMitigation(
        selectedTenant.id,
        currentProject.id,
        incident.id,
        mitigationToRevert.id
      );
      setMitigationToRevert(null);
      setStatusFeedback({
        type: 'success',
        text: `Mitigation reverted: ${result.message || 'Previous flag state successfully restored.'}`,
      });
      fetchIncident();
    } catch (err) {
      setStatusFeedback({ type: 'error', text: err.message || 'Failed to revert mitigation' });
    } finally {
      setIsReverting(false);
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
      await api.approveMitigation(
        selectedTenant.id,
        currentProject.id,
        incident.id,
        selectedMitigation.id
      );
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
      case 'open':
      case 'triggered':
        return 'bg-rose-500/10 text-rose-400 border-rose-500/30 animate-pulse font-semibold';
      case 'monitoring':
      case 'investigating':
        return 'bg-amber-500/10 text-amber-400 border-amber-500/30 font-semibold';
      case 'mitigated':
        return 'bg-indigo-500/10 text-indigo-400 border-indigo-500/30 font-semibold';
      case 'resolved':
        return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30 font-semibold';
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
        Loading incident details...
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
          className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 text-slate-200 rounded-lg text-xs hover:bg-slate-700 transition cursor-pointer"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to Incidents
        </button>
      </div>
    );
  }

  const duration = formatDuration(incident.started_at, incident.resolved_at);
  const totalEventsCount = incident.linked_issues?.reduce((acc, l) => acc + (l.event_count || 0), 0) || 0;
  const activeMitigationsCount = incident.mitigations?.filter((m) => m.status === 'executed').length || 0;

  return (
    <div className="space-y-5">
      {/* Top Header & Status Bar */}
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

              {/* Severity with inline selector */}
              {canManage ? (
                <div className="relative inline-block">
                  <select
                    value={selectedSeverity}
                    onChange={handleSeverityChange}
                    aria-label="Incident Severity"
                    className={`px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wider border font-mono cursor-pointer bg-slate-900 ${getSeverityBadge(
                      incident.severity
                    )}`}
                    title="Change Severity"
                  >
                    <option value="critical">Critical</option>
                    <option value="high">High</option>
                    <option value="medium">Medium</option>
                    <option value="low">Low</option>
                  </select>
                </div>
              ) : (
                <span
                  className={`px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wider border font-mono ${getSeverityBadge(
                    incident.severity
                  )}`}
                >
                  {incident.severity}
                </span>
              )}

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
              {duration && (
                <span className="text-[11px] text-slate-400 font-mono px-2 py-0.5 bg-slate-800/60 rounded border border-slate-700/60">
                  {incident.resolved_at ? `Resolved in ${duration}` : `Active for ${duration}`}
                </span>
              )}
            </div>
            <h1 className="text-xl font-bold text-slate-100 tracking-tight">{incident.title}</h1>
          </div>
        </div>

        {/* Status Lifecycle Actions */}
        <div className="flex items-center gap-2 flex-wrap">
          {canManage && incident.status !== 'monitoring' && incident.status !== 'resolved' && incident.status !== 'closed' && (
            <button
              onClick={() => handleStatusChange('monitoring')}
              disabled={isUpdatingStatus}
              className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-medium transition cursor-pointer disabled:opacity-50 flex items-center gap-1.5"
            >
              <Eye className="w-3.5 h-3.5" />
              Move to Monitoring
            </button>
          )}

          {canManage && incident.status !== 'resolved' && incident.status !== 'closed' && (
            <button
              onClick={handleResolveIncident}
              disabled={isUpdatingStatus}
              className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-medium transition cursor-pointer disabled:opacity-50 flex items-center gap-1.5"
            >
              <CheckCircle className="w-3.5 h-3.5" />
              Resolve Incident
            </button>
          )}

          {canManage && (incident.status === 'resolved' || incident.status === 'mitigated') && (
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
            aria-label="Refresh incident"
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
          <button onClick={() => setStatusFeedback(null)} className="text-slate-400 hover:text-white cursor-pointer">
            ✕
          </button>
        </div>
      )}

      {/* COMPACT SUMMARY CARDS / STATUS HIGHLIGHTS */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {/* Card 1: Status & Severity */}
        <div className="p-3 bg-slate-900 border border-slate-800 rounded-xl space-y-1">
          <span className="text-[10px] uppercase font-mono text-slate-500 font-semibold tracking-wider block">
            Status & Severity
          </span>
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`px-2 py-0.5 rounded text-[11px] font-bold font-mono uppercase ${getSeverityBadge(incident.severity)}`}>
              {incident.severity}
            </span>
            <span className={`px-2 py-0.5 rounded text-[11px] font-medium font-mono uppercase ${getStatusBadge(incident.status)}`}>
              {incident.status}
            </span>
          </div>
        </div>

        {/* Card 2: Environment & Lifetime */}
        <div className="p-3 bg-slate-900 border border-slate-800 rounded-xl space-y-1">
          <span className="text-[10px] uppercase font-mono text-slate-500 font-semibold tracking-wider block">
            Environment & Lifetime
          </span>
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-slate-800 text-slate-300 border border-slate-700 uppercase">
              {incident.environment}
            </span>
            <span className="text-xs text-slate-300 font-mono">
              {duration || 'Active'}
            </span>
          </div>
        </div>

        {/* Card 3: Correlated Scope */}
        <div className="p-3 bg-slate-900 border border-slate-800 rounded-xl space-y-1">
          <span className="text-[10px] uppercase font-mono text-slate-500 font-semibold tracking-wider block">
            Scope & Impact
          </span>
          <div className="text-xs text-slate-200 font-medium">
            <span className="font-semibold text-rose-400">{incident.linked_issues?.length || 0}</span> linked issues · <span className="font-semibold text-slate-300">{totalEventsCount}</span> events
          </div>
        </div>

        {/* Card 4: Mitigations */}
        <div className="p-3 bg-slate-900 border border-slate-800 rounded-xl space-y-1">
          <span className="text-[10px] uppercase font-mono text-slate-500 font-semibold tracking-wider block">
            Mitigation State
          </span>
          <div className="text-xs text-slate-200">
            {activeMitigationsCount > 0 ? (
              <span className="text-emerald-400 font-medium font-mono">
                {activeMitigationsCount} kill switch active
              </span>
            ) : (
              <span className="text-slate-400 italic">No active mitigation</span>
            )}
          </div>
        </div>
      </div>

      {/* Incident Description */}
      {incident.description && (
        <div className="p-3.5 bg-slate-900/60 border border-slate-800 rounded-xl text-xs text-slate-300 space-y-1">
          <span className="text-[10px] uppercase font-mono text-slate-500 font-semibold tracking-wider block">
            Incident Description
          </span>
          <p className="leading-relaxed">{incident.description}</p>
        </div>
      )}

      {/* INVESTIGATION WORKSPACE: Linked Issues & Mitigations (Left) + Timeline (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column (2 Cols): Linked Issues & Feature-Flag Mitigations */}
        <div className="lg:col-span-2 space-y-5">
          {/* LINKED ISSUES */}
          <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-rose-400 text-xs font-bold uppercase tracking-wider">
                <Link2 className="w-4 h-4" />
                Linked Issues ({incident.linked_issues?.length || 0})
              </div>
              {canManage && (
                <button
                  onClick={() => {
                    loadProjectResources();
                    setShowLinkModal(true);
                  }}
                  className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg text-xs font-medium flex items-center gap-1 transition cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5 text-rose-400" />
                  Link Issue
                </button>
              )}
            </div>
            <p className="text-xs text-slate-400">
              Error issues identified as contributing or directly related to this incident.
            </p>

            {incident.linked_issues && incident.linked_issues.length > 0 ? (
              <div className="space-y-2 pt-1">
                {incident.linked_issues.map((link) => (
                  <div
                    key={link.id}
                    className="p-3 bg-slate-800/50 border border-slate-700/70 rounded-lg flex items-center justify-between gap-3 text-xs"
                  >
                    <div className="space-y-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <AlertOctagon className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                        <Link
                          to={`/issues/${link.issue_id}`}
                          className="font-semibold text-slate-100 hover:text-rose-400 transition truncate"
                        >
                          Issue #{link.issue_id}: {link.title}
                        </Link>
                        <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-700 text-slate-300 font-mono">
                          {link.status}
                        </span>
                      </div>
                      <div className="text-[11px] text-slate-400 font-mono flex items-center gap-3">
                        <span>Fingerprint: {link.fingerprint}</span>
                        <span>Events: {link.event_count || 0}</span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <Link
                        to={`/issues/${link.issue_id}`}
                        className="px-2.5 py-1 bg-slate-700/80 hover:bg-slate-600 text-slate-200 rounded text-xs transition"
                      >
                        View
                      </Link>
                      {canManage && (
                        <button
                          onClick={() => handleUnlinkIssue(link.issue_id)}
                          className="p-1 text-slate-400 hover:text-rose-400 transition rounded hover:bg-slate-700 cursor-pointer"
                          title="Unlink Issue"
                          aria-label={`Unlink Issue ${link.issue_id}`}
                        >
                          <Unlink className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-3 bg-slate-800/40 rounded-lg text-center text-xs text-slate-500 italic">
                No issues currently linked to this incident.
              </div>
            )}
          </div>

          {/* FEATURE-FLAG MITIGATIONS */}
          <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-amber-400 text-xs font-bold uppercase tracking-wider">
                <ShieldCheck className="w-4 h-4" />
                Feature-Flag Mitigations ({incident.mitigations?.length || 0})
              </div>
              {canManage && (
                <button
                  onClick={() => {
                    loadProjectResources();
                    setShowMitigationModal(true);
                  }}
                  className="px-2.5 py-1 bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 border border-rose-500/30 rounded-lg text-xs font-medium flex items-center gap-1 transition cursor-pointer"
                >
                  <ZapOff className="w-3.5 h-3.5 text-rose-400" />
                  Apply Mitigation
                </button>
              )}
            </div>

            <p className="text-xs text-slate-400">
              Controlled kill-switch with reversible rollback to isolate regressions.
            </p>

            {incident.mitigations && incident.mitigations.length > 0 ? (
              <div className="space-y-3">
                {incident.mitigations.map((mit) => (
                  <div
                    key={mit.id}
                    className="p-3.5 bg-slate-800/50 border border-slate-700 rounded-lg space-y-2.5"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <ZapOff className="w-3.5 h-3.5 text-rose-400" />
                        <span className="font-semibold text-slate-100 text-xs font-mono">
                          Flag: {mit.target_flag_key || mit.target_flag_id}
                        </span>
                        {mit.target_environment_key && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-700 text-slate-300">
                            {mit.target_environment_key}
                          </span>
                        )}
                      </div>
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-mono font-medium border self-start sm:self-center ${
                          mit.status === 'executed'
                            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                            : mit.status === 'reverted'
                            ? 'bg-blue-500/10 text-blue-400 border-blue-500/30'
                            : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                        }`}
                      >
                        {mit.status.toUpperCase()}
                      </span>
                    </div>

                    <p className="text-xs text-slate-300">{mit.reason}</p>

                    {/* Pre-mitigation state snapshot */}
                    {mit.previous_state && (
                      <div className="p-2 bg-slate-900/80 rounded border border-slate-700/60 text-[11px] font-mono text-slate-400">
                        <span className="text-slate-500 font-semibold mr-2">Pre-Mitigation:</span>
                        <span>
                          Enabled: <strong className="text-slate-200">{String(mit.previous_state.enabled)}</strong>
                          {' · '}
                          Rollout: <strong className="text-slate-200">{mit.previous_state.rollout_percentage ?? 100}%</strong>
                        </span>
                      </div>
                    )}

                    <div className="flex items-center justify-between pt-1 border-t border-slate-700/50">
                      <span className="text-[10px] text-slate-500 font-mono">
                        {mit.executed_at && `Executed: ${formatExactTimestamp(mit.executed_at)}`}
                      </span>

                      <div className="flex items-center gap-2">
                        {mit.status === 'executed' && canManage && (
                          <button
                            onClick={() => setMitigationToRevert(mit)}
                            className="px-2.5 py-1 bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border border-blue-500/30 rounded text-xs font-semibold flex items-center gap-1 transition cursor-pointer"
                          >
                            <RotateCcw className="w-3 h-3" />
                            Revert Mitigation (Restore Flag)
                          </button>
                        )}

                        {mit.status === 'pending' && canManage && (
                          <button
                            onClick={() => {
                              setSelectedMitigation(mit);
                              setShowApprovalModal(true);
                            }}
                            className="px-2.5 py-1 bg-rose-600 hover:bg-rose-500 text-white rounded text-xs font-semibold transition cursor-pointer flex items-center gap-1"
                          >
                            <ZapOff className="w-3 h-3" />
                            Approve Kill Switch
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-3 bg-slate-800/40 rounded-lg text-center text-xs text-slate-500 italic">
                No feature flag mitigations recorded for this incident.
              </div>
            )}
          </div>
        </div>

        {/* Right Column (1 Col): Activity Timeline */}
        <div className="space-y-5">
          <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl space-y-3">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-200 flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-indigo-400" />
              Activity Timeline ({incident.timeline?.length || 0})
            </h2>

            {/* Timeline Stream: timestamp ↓ event type ↓ short description */}
            <div className="relative pl-5 space-y-3.5 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-800 max-h-[380px] overflow-y-auto pr-1">
              {incident.timeline && incident.timeline.length > 0 ? (
                incident.timeline.map((ev) => {
                  const isLong = ev.message && ev.message.length > 100;
                  const isExpanded = !!expandedEvents[ev.id];

                  return (
                    <div key={ev.id} className="relative text-xs space-y-1">
                      <span
                        className={`absolute -left-[1.35rem] top-1 w-2.5 h-2.5 rounded-full border-2 border-slate-900 ${
                          ev.event_type === 'incident_resolved'
                            ? 'bg-emerald-400'
                            : ev.event_type?.includes('mitigation')
                            ? 'bg-rose-500'
                            : ev.event_type?.includes('issue')
                            ? 'bg-amber-400'
                            : 'bg-indigo-500'
                        }`}
                      />
                      <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono">
                        <span title={formatExactTimestamp(ev.created_at)}>
                          {formatRelativeTime(ev.created_at)}
                        </span>
                        <span className="truncate max-w-[100px]">{ev.actor_email || 'System'}</span>
                      </div>
                      <div className="text-[10px] uppercase font-mono font-semibold text-slate-400">
                        {ev.event_type?.replace(/_/g, ' ')}
                      </div>
                      <div className="text-slate-200 font-medium leading-snug">
                        {isLong && !isExpanded ? `${ev.message.slice(0, 100)}...` : ev.message}
                      </div>
                      {isLong && (
                        <button
                          type="button"
                          onClick={() => toggleEventDetail(ev.id)}
                          className="text-[10px] text-indigo-400 hover:text-indigo-300 cursor-pointer"
                        >
                          {isExpanded ? 'Less' : 'More'}
                        </button>
                      )}
                    </div>
                  );
                })
              ) : (
                <div className="text-xs text-slate-500 italic">No timeline events recorded.</div>
              )}
            </div>

            {/* Add Investigation Note */}
            <form onSubmit={handleAddNote} className="pt-2 border-t border-slate-800 space-y-2">
              <label htmlFor="timeline-note-input" className="block text-[11px] font-semibold text-slate-400">Add Timeline Note</label>
              <textarea
                id="timeline-note-input"
                rows={2}
                value={newNote}
                onChange={(e) => setNewNote(e.target.value)}
                placeholder="Log observation or root-cause finding..."
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-rose-500"
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

      {/* AI INCIDENT COPILOT WORKBENCH */}
      <IncidentCopilotSection
        tenantId={selectedTenant?.id}
        projectId={currentProject?.id}
        incidentId={incident.id}
      />

      {/* Link Issue Modal */}
      {showLinkModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs">
          <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-md p-6 shadow-2xl space-y-4">
            <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
              <Link2 className="w-5 h-5 text-rose-500" />
              Link Issue to Incident
            </h2>
            <p className="text-xs text-slate-400">
              Select an existing error issue from this project to associate with the incident.
            </p>

            {linkError && (
              <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-lg text-xs text-rose-400">
                {linkError}
              </div>
            )}

            <form onSubmit={handleLinkIssue} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Project Issue *
                </label>
                {projectIssues.length > 0 ? (
                  <select
                    value={selectedIssueId}
                    onChange={(e) => setSelectedIssueId(e.target.value)}
                    required
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:ring-1 focus:ring-rose-500"
                  >
                    <option value="">Select an issue...</option>
                    {projectIssues.map((iss) => (
                      <option key={iss.id} value={iss.id}>
                        #{iss.id} - {iss.title} ({iss.status})
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="number"
                    required
                    value={selectedIssueId}
                    onChange={(e) => setSelectedIssueId(e.target.value)}
                    placeholder="Enter Issue ID (e.g. 1)"
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:ring-1 focus:ring-rose-500"
                  />
                )}
              </div>

              <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowLinkModal(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-sm font-medium transition cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isLinkingIssue || !selectedIssueId}
                  className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white rounded-lg text-sm font-medium transition shadow-sm disabled:opacity-50 cursor-pointer"
                >
                  {isLinkingIssue ? 'Linking...' : 'Link Issue'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Apply Mitigation Modal */}
      {showMitigationModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs">
          <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-md p-6 shadow-2xl space-y-4">
            <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
              <ZapOff className="w-5 h-5 text-rose-500" />
              Apply Feature-Flag Mitigation
            </h2>
            <p className="text-xs text-slate-400">
              Disables the target feature flag and reduces rollout to 0% in {incident.environment}.
              The previous configuration will be safely preserved for reversible rollback.
            </p>

            {mitigationError && (
              <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-lg text-xs text-rose-400">
                {mitigationError}
              </div>
            )}

            <form onSubmit={handleApplyMitigation} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Target Feature Flag *
                </label>
                {projectFlags.length > 0 ? (
                  <select
                    value={selectedFlagId}
                    onChange={(e) => setSelectedFlagId(e.target.value)}
                    required
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:ring-1 focus:ring-rose-500"
                  >
                    <option value="">Select a feature flag...</option>
                    {projectFlags.map((fl) => (
                      <option key={fl.id} value={fl.id}>
                        {fl.name} ({fl.key})
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="number"
                    required
                    value={selectedFlagId}
                    onChange={(e) => setSelectedFlagId(e.target.value)}
                    placeholder="Enter Flag ID"
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:ring-1 focus:ring-rose-500"
                  />
                )}
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Mitigation Reason
                </label>
                <textarea
                  rows={2}
                  value={mitigationReason}
                  onChange={(e) => setMitigationReason(e.target.value)}
                  placeholder="e.g. Disabling flag to stop checkout gateway timeouts..."
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:ring-1 focus:ring-rose-500"
                />
              </div>

              <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowMitigationModal(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-sm font-medium transition cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isApplyingMitigation || !selectedFlagId}
                  className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white rounded-lg text-sm font-semibold transition shadow-sm disabled:opacity-50 cursor-pointer"
                >
                  {isApplyingMitigation ? 'Applying...' : 'Apply Kill Switch'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Revert Mitigation Confirmation Modal */}
      {mitigationToRevert && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs">
          <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-md p-6 shadow-2xl space-y-4">
            <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
              <RotateCcw className="w-5 h-5 text-blue-400" />
              Confirm Mitigation Reversal
            </h2>
            <p className="text-xs text-slate-300">
              Are you sure you want to revert mitigation #{mitigationToRevert.id} on feature flag{' '}
              <strong className="text-slate-100">'{mitigationToRevert.target_flag_key}'</strong>?
            </p>

            {mitigationToRevert.previous_state && (
              <div className="p-3 bg-slate-800/80 rounded-lg text-xs space-y-1">
                <span className="font-semibold text-slate-300 block">Configuration to restore:</span>
                <div className="text-slate-400 font-mono text-[11px]">
                  Enabled: {String(mitigationToRevert.previous_state.enabled)}
                  <br />
                  Rollout: {mitigationToRevert.previous_state.rollout_percentage ?? 100}%
                </div>
              </div>
            )}

            <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setMitigationToRevert(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-sm font-medium transition cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isReverting}
                onClick={handleRevertMitigation}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-semibold transition shadow-sm disabled:opacity-50 cursor-pointer"
              >
                {isReverting ? 'Restoring...' : 'Confirm & Restore Flag'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Advisory Mitigation Approval Modal */}
      {showApprovalModal && selectedMitigation && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs">
          <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-lg p-6 shadow-2xl space-y-4">
            <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
              <ZapOff className="w-5 h-5 text-rose-500" />
              Approve Mitigation Recommendation
            </h2>

            <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-xs text-amber-300">
              <strong>Human Authorization Required:</strong> Approving will immediately disable the feature flag
              and set rollout to 0% in {incident.environment}.
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
                <span className="text-slate-500 block">Environment</span>
                <span className="font-mono text-slate-200">{incident.environment}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Action</span>
                <span className="font-mono text-slate-200">
                  kill_feature_flag (enabled=False, rollout=0%)
                </span>
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
