import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  ArrowLeft,
  AlertOctagon,
  Copy,
  Check,
  Clock,
  Activity,
  GitBranch,
  Brain,
  ShieldCheck,
  FileCode,
  Sparkles,
} from 'lucide-react';
import { useProject } from '../context/ProjectContext';
import api from '../services/api';
import {
  formatRelativeTime,
  formatExactTimestamp,
  formatNumber,
} from '../utils/formatters';
import { Badge } from '../components/common/Badge';
import { LoadingSpinner } from '../components/common/LoadingState';
import { ErrorState } from '../components/common/ErrorState';

export function IssueDetailPage() {
  const { id } = useParams();
  const { selectedProject } = useProject();
  const [issue, setIssue] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [copiedFp, setCopiedFp] = useState(false);

  const fetchIssue = async () => {
    if (!selectedProject || !id) return;

    setIsLoading(true);
    setError(null);
    try {
      const data = await api.getIssue(selectedProject.id, id);
      setIssue(data);
    } catch (err) {
      console.error('Failed to fetch issue details:', err);
      setError(err.message || 'Issue not found');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchIssue();
  }, [selectedProject?.id, id]);

  const handleCopyFingerprint = () => {
    if (!issue?.fingerprint) return;
    navigator.clipboard.writeText(issue.fingerprint);
    setCopiedFp(true);
    setTimeout(() => setCopiedFp(false), 2000);
  };

  if (isLoading) {
    return <LoadingSpinner text="Fetching issue details..." />;
  }

  if (error || !issue) {
    return (
      <div className="space-y-4">
        <Link
          to="/issues"
          className="inline-flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200 transition"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          <span>Back to Issues</span>
        </Link>
        <ErrorState
          title="Issue Not Found"
          message={error || `Could not find issue #${id} in project ${selectedProject?.name}.`}
          onRetry={fetchIssue}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-150">
      {/* Back button */}
      <div>
        <Link
          to="/issues"
          className="inline-flex items-center gap-1.5 text-xs font-medium text-zinc-400 hover:text-zinc-200 transition group"
        >
          <ArrowLeft className="h-3.5 w-3.5 group-hover:-translate-x-0.5 transition-transform" />
          <span>Back to Issues</span>
        </Link>
      </div>

      {/* Main Issue Header Card */}
      <div className="p-6 rounded-xl bg-[#0f1118] border border-zinc-800/80 shadow-xs space-y-4">
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
          <div className="space-y-2 max-w-3xl">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-zinc-700">
                Issue #{issue.id}
              </span>
              <Badge variant="primary" className="font-mono">
                Project #{issue.project_id || selectedProject?.id}
              </Badge>
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-rose-500/10 text-rose-300 border border-rose-500/20 font-mono">
                {formatNumber(issue.count)} occurrences
              </span>
            </div>

            <h1 className="text-xl md:text-2xl font-bold tracking-tight text-white m-0 break-words">
              {issue.title}
            </h1>
          </div>

          {/* Action buttons (Placeholders) */}
          <div className="flex items-center gap-2 self-start">
            <button
              disabled
              title="Resolution workflow coming in v0.2"
              className="px-3 py-1.5 rounded-lg text-xs font-medium bg-zinc-900 border border-zinc-800 text-zinc-500 cursor-not-allowed"
            >
              Resolve Issue
            </button>
            <button
              disabled
              title="Silence / Mute coming in v0.2"
              className="px-3 py-1.5 rounded-lg text-xs font-medium bg-zinc-900 border border-zinc-800 text-zinc-500 cursor-not-allowed"
            >
              Mute
            </button>
          </div>
        </div>

        {/* Timestamps & Quick Stats */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-3 border-t border-zinc-800/80 text-xs">
          <div>
            <span className="text-[11px] text-zinc-500 block mb-0.5">First Observed</span>
            <span className="text-zinc-200 font-medium">{formatRelativeTime(issue.first_seen)}</span>
            <span className="text-[10px] text-zinc-500 block font-mono">
              {formatExactTimestamp(issue.first_seen)}
            </span>
          </div>

          <div>
            <span className="text-[11px] text-zinc-500 block mb-0.5">Last Observed</span>
            <span className="text-zinc-200 font-medium">{formatRelativeTime(issue.last_seen)}</span>
            <span className="text-[10px] text-zinc-500 block font-mono">
              {formatExactTimestamp(issue.last_seen)}
            </span>
          </div>

          <div>
            <span className="text-[11px] text-zinc-500 block mb-0.5">Total Deduplicated Events</span>
            <span className="text-zinc-200 font-semibold">{formatNumber(issue.count)}</span>
            <span className="text-[10px] text-zinc-500 block">Identical error events</span>
          </div>
        </div>
      </div>

      {/* Fingerprint Card */}
      <div className="p-5 rounded-xl bg-[#0f1118] border border-zinc-800/80 shadow-xs">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <FileCode className="h-4 w-4 text-indigo-400" />
            <h2 className="text-sm font-semibold text-zinc-200 m-0">Stable Error Fingerprint</h2>
          </div>
          <button
            onClick={handleCopyFingerprint}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium text-zinc-300 hover:text-white bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 transition"
          >
            {copiedFp ? (
              <>
                <Check className="h-3.5 w-3.5 text-emerald-400" />
                <span className="text-emerald-400">Copied</span>
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5" />
                <span>Copy Hash</span>
              </>
            )}
          </button>
        </div>

        <p className="text-[11px] text-zinc-500 mb-3">
          ReleaseGuard generates a normalized SHA-256 hash across the exception type and call frames.
          Dynamic identifiers, hex memory addresses, and line numbers are normalized to prevent duplicate issue sprawl.
        </p>

        <div className="p-3 rounded-lg bg-zinc-950 border border-zinc-800/90 font-mono text-xs text-indigo-300 break-all select-all">
          {issue.fingerprint}
        </div>
      </div>

      {/* Future Capabilities Architecture Cards (Honest placeholders) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Stack Trace Placeholder */}
        <div className="p-5 rounded-xl bg-[#0f1118] border border-zinc-800/80 shadow-xs space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-zinc-400" />
              <h2 className="text-sm font-semibold text-zinc-200 m-0">Event Timeline & Stack Trace</h2>
            </div>
            <span className="text-[10px] uppercase font-semibold text-zinc-500 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">
              v0.2 Roadmap
            </span>
          </div>

          <div className="p-4 rounded-lg bg-zinc-950/60 border border-dashed border-zinc-800 text-center py-8">
            <p className="text-xs text-zinc-400 font-medium mb-1">
              Detailed event information will appear here.
            </p>
            <p className="text-[11px] text-zinc-500 max-w-sm mx-auto">
              Per-event stack traces, HTTP context breadcrumbs, and raw frame inspector will be enabled in v0.2.
            </p>
          </div>
        </div>

        {/* Release Correlation Placeholder */}
        <div className="p-5 rounded-xl bg-[#0f1118] border border-zinc-800/80 shadow-xs space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <GitBranch className="h-4 w-4 text-zinc-400" />
              <h2 className="text-sm font-semibold text-zinc-200 m-0">Release Correlation</h2>
            </div>
            <span className="text-[10px] uppercase font-semibold text-zinc-500 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">
              v0.2 Roadmap
            </span>
          </div>

          <div className="p-4 rounded-lg bg-zinc-950/60 border border-dashed border-zinc-800 text-center py-8">
            <p className="text-xs text-zinc-400 font-medium mb-1">
              Deployment and version regression tracking.
            </p>
            <p className="text-[11px] text-zinc-500 max-w-sm mx-auto">
              Correlating failures to specific deploy SHAs and release versions will appear here.
            </p>
          </div>
        </div>

        {/* AI Incident Analysis Placeholder */}
        <div className="p-5 rounded-xl bg-[#0f1118] border border-zinc-800/80 shadow-xs space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Brain className="h-4 w-4 text-indigo-400" />
              <h2 className="text-sm font-semibold text-zinc-200 m-0">AI Incident Analysis</h2>
            </div>
            <span className="text-[10px] uppercase font-semibold text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20">
              v0.3 Roadmap
            </span>
          </div>

          <div className="p-4 rounded-lg bg-zinc-950/60 border border-dashed border-zinc-800 text-center py-8">
            <p className="text-xs text-zinc-400 font-medium mb-1">
              Automated Root-Cause Diagnostic
            </p>
            <p className="text-[11px] text-zinc-500 max-w-sm mx-auto">
              AI incident assistant will synthesize stack traces and recent commits to propose fix pull requests.
            </p>
          </div>
        </div>

        {/* Automated Mitigations Placeholder */}
        <div className="p-5 rounded-xl bg-[#0f1118] border border-zinc-800/80 shadow-xs space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-emerald-400" />
              <h2 className="text-sm font-semibold text-zinc-200 m-0">Automated Mitigations</h2>
            </div>
            <span className="text-[10px] uppercase font-semibold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
              v0.3 Roadmap
            </span>
          </div>

          <div className="p-4 rounded-lg bg-zinc-950/60 border border-dashed border-zinc-800 text-center py-8">
            <p className="text-xs text-zinc-400 font-medium mb-1">
              Deterministic Feature Flag Kill-Switches
            </p>
            <p className="text-[11px] text-zinc-500 max-w-sm mx-auto">
              Automatic circuit breakers and feature-flag disablement upon error threshold breaches.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default IssueDetailPage;
