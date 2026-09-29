import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  ArrowLeft,
  AlertOctagon,
  Copy,
  Check,
  Clock,
  Activity,
  CheckCircle2,
  VolumeX,
  RotateCcw,
  FileCode,
  Terminal,
  Calendar,
  Tag,
  RefreshCw,
  AlertTriangle,
} from 'lucide-react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { useProject } from '../context/ProjectContext';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import {
  formatRelativeTime,
  formatExactTimestamp,
  parseUtcDate,
  formatNumber,
  formatFingerprint,
} from '../utils/formatters';
import { Badge } from '../components/common/Badge';
import { LoadingSpinner } from '../components/common/LoadingState';
import { ErrorState } from '../components/common/ErrorState';

export function IssueDetailPage() {
  const { id } = useParams();
  const { selectedTenant } = useAuth();
  const { selectedProject } = useProject();

  // Issue Metadata
  const [issue, setIssue] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  // Status Action State
  const [isActionLoading, setIsActionLoading] = useState(false);
  const [feedback, setFeedback] = useState(null);

  // Event Timeline & Selected Event
  const [events, setEvents] = useState([]);
  const [totalEvents, setTotalEvents] = useState(0);
  const [eventsOffset, setEventsOffset] = useState(0);
  const [hasMoreEvents, setHasMoreEvents] = useState(false);
  const [isLoadingEvents, setIsLoadingEvents] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState(null);

  // Time-Series Analytics
  const [trendRange, setTrendRange] = useState('24h');
  const [trendData, setTrendData] = useState(null);
  const [isLoadingTrend, setIsLoadingTrend] = useState(false);

  // Clipboard feedback
  const [copiedFp, setCopiedFp] = useState(false);
  const [copiedEventId, setCopiedEventId] = useState(false);
  const [copiedStackTrace, setCopiedStackTrace] = useState(false);

  // Issue Releases Correlation (Phase 8)
  const [issueReleases, setIssueReleases] = useState(null);
  const [isLoadingReleases, setIsLoadingReleases] = useState(false);

  // 1. Fetch Issue Data
  const fetchIssue = useCallback(async () => {
    if (!selectedProject || !id) return;

    setIsLoading(true);
    setError(null);
    try {
      let data = null;
      if (selectedTenant) {
        data = await api.getTenantIssue(selectedTenant.id, selectedProject.id, id);
      } else {
        data = await api.getIssue(selectedProject.id, id);
      }
      setIssue(data);
    } catch (err) {
      console.error('Failed to fetch issue details:', err);
      setError(err.message || 'Issue not found');
    } finally {
      setIsLoading(false);
    }
  }, [selectedProject?.id, selectedTenant?.id, id]);

  // 2. Fetch Events
  const fetchEvents = useCallback(
    async (offset = 0, append = false) => {
      if (!selectedProject || !id) return;

      if (append) {
        setIsLoadingMore(true);
      } else {
        setIsLoadingEvents(true);
      }

      try {
        let resp = null;
        if (selectedTenant) {
          resp = await api.getTenantIssueEvents(selectedTenant.id, selectedProject.id, id, 50, offset);
        } else {
          resp = await api.getIssueEvents(selectedProject.id, id, 50, offset);
        }
        if (append) {
          setEvents((prev) => [...prev, ...resp.items]);
        } else {
          setEvents(resp.items);
          if (resp.items.length > 0 && !selectedEvent) {
            setSelectedEvent(resp.items[0]);
          }
        }
        setTotalEvents(resp.total);
        setEventsOffset(offset);
        setHasMoreEvents(resp.has_more);
      } catch (err) {
        console.error('Failed to fetch issue events:', err);
      } finally {
        setIsLoadingEvents(false);
        setIsLoadingMore(false);
      }
    },
    [selectedProject?.id, selectedTenant?.id, id, selectedEvent]
  );

  // 3. Fetch Time-Series Trend
  const fetchTrend = useCallback(
    async (range) => {
      if (!selectedProject || !id) return;

      setIsLoadingTrend(true);
      try {
        let data = null;
        if (selectedTenant) {
          data = await api.getTenantIssueTimeseries(selectedTenant.id, selectedProject.id, id, range);
        } else {
          data = await api.getIssueTimeseries(selectedProject.id, id, range);
        }
        setTrendData(data);
      } catch (err) {
        console.error('Failed to fetch issue timeseries:', err);
      } finally {
        setIsLoadingTrend(false);
      }
    },
    [selectedProject?.id, selectedTenant?.id, id]
  );

  // 4. Fetch Release Correlation (Phase 8)
  const fetchReleasesCorrelation = useCallback(async () => {
    if (!selectedProject || !id || !selectedTenant) return;
    setIsLoadingReleases(true);
    try {
      const data = await api.getIssueReleases(selectedTenant.id, selectedProject.id, id);
      setIssueReleases(data);
    } catch (err) {
      console.error('Failed to fetch issue releases:', err);
    } finally {
      setIsLoadingReleases(false);
    }
  }, [selectedProject?.id, selectedTenant?.id, id]);

  useEffect(() => {
    fetchIssue();
    fetchEvents(0, false);
    fetchReleasesCorrelation();
  }, [fetchIssue, fetchEvents, fetchReleasesCorrelation]);

  useEffect(() => {
    fetchTrend(trendRange);
  }, [fetchTrend, trendRange]);

  // Status Lifecycle Action Handler
  const handleStatusChange = async (action) => {
    if (!selectedProject || !issue) return;

    setIsActionLoading(true);
    setFeedback(null);
    try {
      let updated = null;
      if (action === 'resolve') {
        if (selectedTenant) {
          updated = await api.resolveTenantIssue(selectedTenant.id, selectedProject.id, issue.id);
        } else {
          updated = await api.resolveIssue(selectedProject.id, issue.id);
        }
        setFeedback({ type: 'success', text: 'Issue marked as resolved.' });
      } else if (action === 'mute') {
        if (selectedTenant) {
          updated = await api.muteTenantIssue(selectedTenant.id, selectedProject.id, issue.id);
        } else {
          updated = await api.muteIssue(selectedProject.id, issue.id);
        }
        setFeedback({ type: 'success', text: 'Issue muted.' });
      } else if (action === 'unresolve') {
        if (selectedTenant) {
          updated = await api.unresolveTenantIssue(selectedTenant.id, selectedProject.id, issue.id);
        } else {
          updated = await api.unresolveIssue(selectedProject.id, issue.id);
        }
        setFeedback({ type: 'success', text: 'Issue restored to unresolved.' });
      }
      if (updated) {
        setIssue(updated);
      }
    } catch (err) {
      console.error(`Failed to ${action} issue:`, err);
      setFeedback({ type: 'error', text: err.message || `Failed to ${action} issue.` });
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleCopyFingerprint = () => {
    if (!issue?.fingerprint) return;
    navigator.clipboard.writeText(issue.fingerprint);
    setCopiedFp(true);
    setTimeout(() => setCopiedFp(false), 2000);
  };

  const handleCopyEventId = () => {
    if (!selectedEvent?.event_id) return;
    navigator.clipboard.writeText(selectedEvent.event_id);
    setCopiedEventId(true);
    setTimeout(() => setCopiedEventId(false), 2000);
  };

  const handleCopyStackTrace = () => {
    if (!selectedEvent?.stack_trace) return;
    navigator.clipboard.writeText(selectedEvent.stack_trace);
    setCopiedStackTrace(true);
    setTimeout(() => setCopiedStackTrace(false), 2000);
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

  // Format chart buckets for rendering
  const formattedBuckets =
    trendData?.buckets?.map((b) => {
      const dt = parseUtcDate(b.timestamp);
      let label = '';
      if (trendRange === '1h') {
        label = dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
      } else if (trendRange === '24h') {
        label = dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
      } else {
        label = dt.toLocaleDateString([], { month: 'short', day: 'numeric' });
      }
      return {
        timestamp: b.timestamp,
        label,
        count: b.count,
      };
    }) || [];

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

              {/* Status Badge */}
              {issue.status === 'resolved' ? (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-xs font-semibold bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-mono">
                  <CheckCircle2 className="h-3 w-3" />
                  Resolved
                </span>
              ) : issue.status === 'muted' ? (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-xs font-semibold bg-zinc-800 text-zinc-400 border border-zinc-700 font-mono">
                  <VolumeX className="h-3 w-3" />
                  Muted
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-xs font-semibold bg-amber-500/10 text-amber-300 border border-amber-500/20 font-mono">
                  <AlertOctagon className="h-3 w-3" />
                  Unresolved
                </span>
              )}

              {/* Regression Badge */}
              {issue.is_regression && (
                <span
                  className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-xs font-semibold bg-rose-500/10 text-rose-300 border border-rose-500/30 font-mono animate-pulse"
                  title={
                    issue.regressed_at
                      ? `Regressed ${formatRelativeTime(issue.regressed_at)}`
                      : 'Regression detected'
                  }
                >
                  <AlertTriangle className="h-3 w-3 text-rose-400" />
                  Regression
                </span>
              )}

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

          {/* Action buttons (Active Status Lifecycle) */}
          <div className="flex items-center gap-2 self-start flex-wrap">
            {issue.status === 'unresolved' && (
              <>
                <button
                  type="button"
                  onClick={() => handleStatusChange('resolve')}
                  disabled={isActionLoading}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-600 hover:bg-emerald-500 text-white transition shadow-sm disabled:opacity-50 cursor-pointer"
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  <span>Resolve</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleStatusChange('mute')}
                  disabled={isActionLoading}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 transition disabled:opacity-50 cursor-pointer"
                >
                  <VolumeX className="h-3.5 w-3.5" />
                  <span>Mute</span>
                </button>
              </>
            )}

            {(issue.status === 'resolved' || issue.status === 'muted') && (
              <button
                type="button"
                onClick={() => handleStatusChange('unresolve')}
                disabled={isActionLoading}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition disabled:opacity-50 cursor-pointer"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                <span>Unresolve</span>
              </button>
            )}
          </div>
        </div>

        {/* Feedback Alert */}
        {feedback && (
          <div
            className={`p-3 rounded-lg text-xs border flex items-center justify-between ${
              feedback.type === 'success'
                ? 'bg-emerald-950/40 border-emerald-800 text-emerald-300'
                : 'bg-rose-950/40 border-rose-800 text-rose-300'
            }`}
          >
            <span>{feedback.text}</span>
            <button
              onClick={() => setFeedback(null)}
              className="text-xs text-zinc-400 hover:text-white"
            >
              ✕
            </button>
          </div>
        )}

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
            <span className="text-[11px] text-zinc-500 block mb-0.5">Status Lifecycle</span>
            {issue.status === 'resolved' && issue.resolved_at ? (
              <span className="text-emerald-400 font-medium">
                Resolved {formatRelativeTime(issue.resolved_at)}
              </span>
            ) : issue.status === 'muted' && issue.muted_at ? (
              <span className="text-zinc-400 font-medium">
                Muted {formatRelativeTime(issue.muted_at)}
              </span>
            ) : issue.is_regression && issue.regressed_at ? (
              <span className="text-rose-400 font-medium">
                Regressed {formatRelativeTime(issue.regressed_at)}
              </span>
            ) : (
              <span className="text-zinc-300 font-medium">Active investigation</span>
            )}
            <span className="text-[10px] text-zinc-500 block">
              {formatNumber(issue.count)} total deduplicated occurrences
            </span>
          </div>
        </div>

        {/* Release Correlation (Phase 8) */}
        <div className="pt-3 border-t border-zinc-800/80">
          <div className="flex items-center gap-2 mb-2">
            <Tag className="h-3.5 w-3.5 text-indigo-400" />
            <span className="text-xs font-semibold text-zinc-300">Release Correlation</span>
            {issueReleases && issueReleases.release_count > 0 && (
              <span className="px-1.5 py-0.5 rounded text-[10px] bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-mono">
                {issueReleases.release_count} affected
              </span>
            )}
          </div>
          {isLoadingReleases ? (
            <span className="text-xs text-zinc-500">Checking correlated releases...</span>
          ) : issueReleases && issueReleases.affected_releases && issueReleases.affected_releases.length > 0 ? (
            <div className="flex flex-wrap items-center gap-4 text-xs">
              <div>
                <span className="text-[11px] text-zinc-500 block mb-0.5">First Seen in</span>
                <span className="px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 font-mono text-xs border border-zinc-700">
                  {issueReleases.first_seen_release || 'N/A'}
                </span>
              </div>
              <div>
                <span className="text-[11px] text-zinc-500 block mb-0.5">Latest Seen in</span>
                <span className="px-2 py-0.5 rounded bg-indigo-950/40 text-indigo-300 font-mono text-xs border border-indigo-800/50">
                  {issueReleases.latest_release || 'N/A'}
                </span>
              </div>
              <div>
                <span className="text-[11px] text-zinc-500 block mb-0.5">All Affected Releases</span>
                <div className="flex flex-wrap gap-1">
                  {issueReleases.affected_releases.map((rel) => (
                    <span
                      key={rel}
                      className="px-1.5 py-0.5 rounded bg-zinc-800/80 text-zinc-400 font-mono text-[11px] border border-zinc-700/60"
                    >
                      {rel}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <span className="text-xs text-zinc-500 italic">
              No releases tagged in error events for this issue yet.
            </span>
          )}
        </div>
      </div>

      {/* Time-Series Trend Chart Card */}
      <div className="p-5 rounded-xl bg-[#0f1118] border border-zinc-800/80 shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-indigo-400" />
            <div>
              <h2 className="text-sm font-semibold text-zinc-200 m-0">Occurrence Trend</h2>
              <p className="text-[11px] text-zinc-500 m-0">
                Aggregated event distribution over selected time window
              </p>
            </div>
          </div>

          {/* Range Selector Controls */}
          <div className="flex items-center gap-1 bg-zinc-950 p-1 rounded-lg border border-zinc-800 self-start sm:self-auto">
            {['1h', '24h', '7d'].map((r) => (
              <button
                key={r}
                onClick={() => setTrendRange(r)}
                className={`px-2.5 py-1 text-xs font-medium rounded-md transition cursor-pointer ${
                  trendRange === r
                    ? 'bg-indigo-600 text-white shadow-xs'
                    : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-850'
                }`}
              >
                {r.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        {/* Chart Body */}
        {isLoadingTrend ? (
          <div className="h-48 flex items-center justify-center text-xs text-zinc-500">
            <RefreshCw className="h-4 w-4 animate-spin mr-2" />
            Loading trend data...
          </div>
        ) : trendData?.total_events === 0 ? (
          <div className="h-48 flex flex-col items-center justify-center text-center p-4 border border-dashed border-zinc-800 rounded-lg">
            <Activity className="h-6 w-6 text-zinc-600 mb-1" />
            <p className="text-xs text-zinc-400 font-medium">No events recorded</p>
            <p className="text-[11px] text-zinc-500">
              No occurrences of this issue arrived in the last {trendRange}.
            </p>
          </div>
        ) : (
          <div className="h-48 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={formattedBuckets}
                margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
              >
                <defs>
                  <linearGradient id="issueTrendGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="label"
                  stroke="#52525b"
                  fontSize={10}
                  tickLine={false}
                  axisLine={{ stroke: '#27272a' }}
                />
                <YAxis
                  stroke="#52525b"
                  fontSize={10}
                  tickLine={false}
                  axisLine={{ stroke: '#27272a' }}
                  allowDecimals={false}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload;
                      return (
                        <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-700 shadow-xl text-xs space-y-1">
                          <p className="text-zinc-400 font-mono text-[10px]">{data.timestamp}</p>
                          <p className="text-indigo-300 font-semibold font-mono">
                            Events: <span className="font-bold">{formatNumber(data.count)}</span>
                          </p>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="count"
                  stroke="#6366f1"
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#issueTrendGrad)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
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
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium text-zinc-300 hover:text-white bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 transition cursor-pointer"
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
        </p>

        <div className="p-3 rounded-lg bg-zinc-950 border border-zinc-800/90 font-mono text-xs text-indigo-300 break-all select-all">
          {issue.fingerprint}
        </div>
      </div>

      {/* Event Timeline & Stack Trace Inspector (Two-Column Master-Detail) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Event Timeline (5 cols) */}
        <div className="lg:col-span-5 p-5 rounded-xl bg-[#0f1118] border border-zinc-800/80 shadow-xs space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-zinc-400" />
              <h2 className="text-sm font-semibold text-zinc-200 m-0">Event Timeline</h2>
            </div>
            <span className="text-[11px] font-mono text-zinc-400 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">
              {totalEvents} total
            </span>
          </div>

          <p className="text-[11px] text-zinc-500">
            Real ingested error occurrences ordered by newest first. Click an event to inspect its
            complete stack trace.
          </p>

          {isLoadingEvents ? (
            <div className="py-12 flex justify-center items-center text-xs text-zinc-500">
              <RefreshCw className="h-4 w-4 animate-spin mr-2" />
              Loading events...
            </div>
          ) : events.length === 0 ? (
            <div className="py-8 text-center border border-dashed border-zinc-800 rounded-lg text-xs text-zinc-500">
              No events found for this issue.
            </div>
          ) : (
            <div className="space-y-2">
              <div className="max-h-[500px] overflow-y-auto space-y-2 pr-1">
                {events.map((ev) => {
                  const isSelected = selectedEvent?.id === ev.id;
                  return (
                    <div
                      key={ev.id}
                      onClick={() => setSelectedEvent(ev)}
                      className={`p-3 rounded-lg border transition cursor-pointer text-left ${
                        isSelected
                          ? 'bg-indigo-950/30 border-indigo-500/60 shadow-xs'
                          : 'bg-zinc-950/70 border-zinc-800/80 hover:bg-zinc-900/60 hover:border-zinc-700'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span className="font-mono text-[11px] font-semibold text-zinc-200 truncate">
                          {ev.exception_type}
                        </span>
                        <span className="text-[10px] text-zinc-400 whitespace-nowrap">
                          {formatRelativeTime(ev.received_at)}
                        </span>
                      </div>

                      <p className="text-xs text-zinc-400 truncate mb-1.5">{ev.message}</p>

                      <div className="flex items-center gap-2 text-[10px] font-mono text-zinc-500">
                        <span>ID: {formatFingerprint(ev.event_id, 8)}</span>
                        {ev.release && (
                          <span className="px-1.5 py-0.2 rounded bg-zinc-900 border border-zinc-800 text-zinc-400">
                            {ev.release}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>

              {hasMoreEvents && (
                <button
                  type="button"
                  onClick={() => fetchEvents(eventsOffset + 50, true)}
                  disabled={isLoadingMore}
                  className="w-full py-2 rounded-lg text-xs font-medium text-zinc-300 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 transition cursor-pointer disabled:opacity-50"
                >
                  {isLoadingMore ? 'Loading more events...' : 'Load Older Events'}
                </button>
              )}
            </div>
          )}
        </div>

        {/* Right Column: Selected Event Inspector (7 cols) */}
        <div className="lg:col-span-7 p-5 rounded-xl bg-[#0f1118] border border-zinc-800/80 shadow-xs space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Terminal className="h-4 w-4 text-indigo-400" />
              <h2 className="text-sm font-semibold text-zinc-200 m-0">Event Inspector</h2>
            </div>

            {selectedEvent && (
              <button
                type="button"
                onClick={handleCopyStackTrace}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium text-zinc-300 hover:text-white bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 transition cursor-pointer"
              >
                {copiedStackTrace ? (
                  <>
                    <Check className="h-3.5 w-3.5 text-emerald-400" />
                    <span className="text-emerald-400">Copied Trace</span>
                  </>
                ) : (
                  <>
                    <Copy className="h-3.5 w-3.5" />
                    <span>Copy Stack Trace</span>
                  </>
                )}
              </button>
            )}
          </div>

          {!selectedEvent ? (
            <div className="p-8 text-center border border-dashed border-zinc-800 rounded-lg text-xs text-zinc-500">
              Select an event from the timeline to view its stack trace and metadata.
            </div>
          ) : (
            <div className="space-y-4">
              {/* Event Metadata Strip */}
              <div className="p-3 rounded-lg bg-zinc-950 border border-zinc-800/80 grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                <div>
                  <span className="text-[10px] text-zinc-500 block mb-0.5">Event ID</span>
                  <div className="flex items-center gap-1 font-mono text-[11px] text-zinc-300 break-all">
                    <span>{formatFingerprint(selectedEvent.event_id, 10)}</span>
                    <button
                      onClick={handleCopyEventId}
                      title="Copy full Event ID"
                      className="text-zinc-500 hover:text-zinc-200"
                    >
                      {copiedEventId ? (
                        <Check className="h-3 w-3 text-emerald-400" />
                      ) : (
                        <Copy className="h-3 w-3" />
                      )}
                    </button>
                  </div>
                </div>

                <div>
                  <span className="text-[10px] text-zinc-500 block mb-0.5">Release</span>
                  <span className="font-mono text-zinc-300 text-xs">
                    {selectedEvent.release || 'Unspecified'}
                  </span>
                </div>

                <div>
                  <span className="text-[10px] text-zinc-500 block mb-0.5">Received At</span>
                  <span className="text-zinc-300 text-xs font-mono">
                    {formatExactTimestamp(selectedEvent.received_at)}
                  </span>
                </div>
              </div>

              {/* Exception & Message */}
              <div className="p-3.5 rounded-lg bg-zinc-950 border border-zinc-800/80 space-y-1">
                <span className="text-[10px] font-mono text-rose-400 uppercase tracking-wider font-semibold block">
                  {selectedEvent.exception_type}
                </span>
                <p className="text-sm font-medium text-white break-words m-0">
                  {selectedEvent.message}
                </p>
              </div>

              {/* Stack Trace Box */}
              <div>
                <div className="flex items-center justify-between text-xs text-zinc-400 mb-1.5">
                  <span className="font-medium text-[11px] uppercase tracking-wider text-zinc-400">
                    Call Stack
                  </span>
                  <span className="text-[10px] text-zinc-500 font-mono">Plaintext execution trace</span>
                </div>

                <div className="relative">
                  <pre className="p-4 rounded-lg bg-zinc-950 border border-zinc-800/90 text-zinc-300 font-mono text-xs leading-relaxed overflow-x-auto whitespace-pre max-h-[420px] select-all">
                    <code>{selectedEvent.stack_trace}</code>
                  </pre>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default IssueDetailPage;
