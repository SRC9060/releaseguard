import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertOctagon,
  Activity,
  Flame,
  Clock,
  ArrowRight,
  TrendingUp,
  FolderGit2,
  Copy,
  Check,
  Sparkles,
  RefreshCw,
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
  formatNumber,
  formatFingerprint,
} from '../utils/formatters';
import { Badge } from '../components/common/Badge';
import { LoadingSpinner, SkeletonCard, SkeletonRow } from '../components/common/LoadingState';
import { EmptyState } from '../components/common/EmptyState';
import { ErrorState } from '../components/common/ErrorState';
import TestEventModal from '../components/events/TestEventModal';

export function OverviewPage() {
  const { selectedTenant } = useAuth();
  const { selectedProject, isLoading: isProjectLoading } = useProject();
  const [issues, setIssues] = useState([]);
  const [isLoadingIssues, setIsLoadingIssues] = useState(true);
  const [error, setError] = useState(null);

  // Time-Series Analytics for Project Error Volume
  const [trendRange, setTrendRange] = useState('24h');
  const [trendData, setTrendData] = useState(null);
  const [isLoadingTrend, setIsLoadingTrend] = useState(false);

  const [copiedFp, setCopiedFp] = useState(null);
  const [isTestModalOpen, setIsTestModalOpen] = useState(false);

  const fetchOverviewData = useCallback(async () => {
    if (!selectedProject) {
      setIssues([]);
      setIsLoadingIssues(false);
      return;
    }

    setIsLoadingIssues(true);
    setError(null);
    try {
      let issuesData = [];
      if (selectedTenant) {
        issuesData = await api.getTenantIssues(selectedTenant.id, selectedProject.id);
      } else {
        issuesData = await api.getIssues(selectedProject.id);
      }
      setIssues(issuesData);
    } catch (err) {
      console.error('Failed to fetch issues:', err);
      setError(err.message || 'Failed to fetch issues');
    } finally {
      setIsLoadingIssues(false);
    }
  }, [selectedProject?.id, selectedTenant?.id]);

  const fetchTimeseries = useCallback(
    async (range) => {
      if (!selectedProject) return;

      setIsLoadingTrend(true);
      try {
        let data = null;
        if (selectedTenant) {
          data = await api.getTenantProjectTimeseries(selectedTenant.id, selectedProject.id, range);
        } else {
          data = await api.getProjectTimeseries(selectedProject.id, range);
        }
        setTrendData(data);
      } catch (err) {
        console.error('Failed to fetch project timeseries:', err);
      } finally {
        setIsLoadingTrend(false);
      }
    },
    [selectedProject?.id, selectedTenant?.id]
  );

  useEffect(() => {
    fetchOverviewData();
  }, [fetchOverviewData]);

  useEffect(() => {
    fetchTimeseries(trendRange);
  }, [fetchTimeseries, trendRange]);

  const handleCopyFingerprint = (e, fp) => {
    e.stopPropagation();
    navigator.clipboard.writeText(fp);
    setCopiedFp(fp);
    setTimeout(() => setCopiedFp(null), 2000);
  };

  if (isProjectLoading) {
    return <LoadingSpinner text="Connecting to workspace..." />;
  }

  if (!selectedProject) {
    return (
      <EmptyState
        icon={FolderGit2}
        title="No Project Selected"
        description="Select or create a project from the top bar to inspect error analytics and reliability issues."
      />
    );
  }

  // Calculate honest metrics from actual API data
  const totalIssues = issues.length;
  const totalOccurrences = issues.reduce((acc, curr) => acc + (curr.count || 0), 0);

  const sortedByOccurrences = [...issues].sort((a, b) => b.count - a.count);
  const topFailure = sortedByOccurrences[0] || null;

  const sortedByLastSeen = [...issues].sort(
    (a, b) => new Date(b.last_seen) - new Date(a.last_seen)
  );
  const recentIssues = sortedByLastSeen.slice(0, 5);

  // Format chart buckets for rendering
  const formattedBuckets =
    trendData?.buckets?.map((b) => {
      const dt = new Date(b.timestamp);
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
      {/* Page Title & Context */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-zinc-800/80">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h1 className="text-xl font-bold tracking-tight text-white m-0">Overview</h1>
            <Badge variant="primary" className="font-mono">
              {selectedProject.name}
            </Badge>
          </div>
          <p className="text-xs text-zinc-400">
            Real-time error capture, fingerprint clustering, and historical reliability volume.
          </p>
        </div>

        <button
          type="button"
          onClick={() => setIsTestModalOpen(true)}
          className="inline-flex items-center justify-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white transition shadow-sm self-start sm:self-auto cursor-pointer"
        >
          <Sparkles className="h-3.5 w-3.5" />
          <span>Simulate Error Event</span>
        </button>
      </div>

      {error ? (
        <ErrorState message={error} onRetry={fetchOverviewData} />
      ) : (
        <>
          {/* Top Metric Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {isLoadingIssues ? (
              <>
                <SkeletonCard />
                <SkeletonCard />
                <SkeletonCard />
                <SkeletonCard />
              </>
            ) : (
              <>
                {/* Total Unique Issues */}
                <div className="p-4 rounded-xl bg-[#0f1118] border border-zinc-800/80 shadow-xs">
                  <div className="flex items-center justify-between text-zinc-400 mb-2">
                    <span className="text-xs font-medium">Total Issues</span>
                    <AlertOctagon className="h-4 w-4 text-indigo-400" />
                  </div>
                  <div className="text-2xl font-bold text-white tracking-tight">
                    {formatNumber(totalIssues)}
                  </div>
                  <p className="text-[11px] text-zinc-500 mt-1">
                    Distinct fingerprint clusters
                  </p>
                </div>

                {/* Total Error Occurrences */}
                <div className="p-4 rounded-xl bg-[#0f1118] border border-zinc-800/80 shadow-xs">
                  <div className="flex items-center justify-between text-zinc-400 mb-2">
                    <span className="text-xs font-medium">Error Occurrences</span>
                    <Activity className="h-4 w-4 text-rose-400" />
                  </div>
                  <div className="text-2xl font-bold text-white tracking-tight">
                    {formatNumber(totalOccurrences)}
                  </div>
                  <p className="text-[11px] text-zinc-500 mt-1">
                    Total ingested failure events
                  </p>
                </div>

                {/* Highest Frequency Issue */}
                <div className="p-4 rounded-xl bg-[#0f1118] border border-zinc-800/80 shadow-xs">
                  <div className="flex items-center justify-between text-zinc-400 mb-2">
                    <span className="text-xs font-medium">Highest Volume Failure</span>
                    <Flame className="h-4 w-4 text-amber-400" />
                  </div>
                  <div className="text-sm font-semibold text-zinc-200 truncate">
                    {topFailure ? topFailure.title : '—'}
                  </div>
                  <p className="text-[11px] text-zinc-500 mt-1">
                    {topFailure ? `${formatNumber(topFailure.count)} occurrences` : 'No errors recorded'}
                  </p>
                </div>

                {/* Latest Failure Activity */}
                <div className="p-4 rounded-xl bg-[#0f1118] border border-zinc-800/80 shadow-xs">
                  <div className="flex items-center justify-between text-zinc-400 mb-2">
                    <span className="text-xs font-medium">Latest Failure</span>
                    <Clock className="h-4 w-4 text-emerald-400" />
                  </div>
                  <div className="text-sm font-semibold text-zinc-200">
                    {sortedByLastSeen[0] ? formatRelativeTime(sortedByLastSeen[0].last_seen) : '—'}
                  </div>
                  <p className="text-[11px] text-zinc-500 mt-1 truncate">
                    {sortedByLastSeen[0] ? sortedByLastSeen[0].title : 'System healthy'}
                  </p>
                </div>
              </>
            )}
          </div>

          {/* Historical Error Volume Time-Series Chart */}
          <div className="p-5 rounded-xl bg-[#0f1118] border border-zinc-800/80 shadow-xs space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-indigo-400" />
                  <h2 className="text-sm font-semibold text-zinc-200 m-0">
                    Historical Error Volume
                  </h2>
                </div>
                <p className="text-[11px] text-zinc-500 mt-0.5 mb-0">
                  Total project failure events aggregated across all active issues
                </p>
              </div>

              {/* Range Selector Controls */}
              <div className="flex items-center gap-1 bg-zinc-950 p-1 rounded-lg border border-zinc-800 self-start sm:self-auto">
                {['1h', '24h', '7d'].map((r) => (
                  <button
                    key={r}
                    type="button"
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

            {/* Chart Area */}
            {isLoadingTrend ? (
              <div className="h-56 flex items-center justify-center text-xs text-zinc-500">
                <RefreshCw className="h-4 w-4 animate-spin mr-2" />
                Loading error volume trend...
              </div>
            ) : trendData?.total_events === 0 ? (
              <div className="h-56 flex flex-col items-center justify-center text-center p-6 border border-dashed border-zinc-800 rounded-lg">
                <Activity className="h-7 w-7 text-zinc-600 mb-2" />
                <p className="text-xs text-zinc-300 font-semibold mb-1">
                  Zero Errors In Last {trendRange}
                </p>
                <p className="text-[11px] text-zinc-500 max-w-sm">
                  No ingested error events were recorded for project {selectedProject.name} during this
                  time interval.
                </p>
              </div>
            ) : (
              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart
                    data={formattedBuckets}
                    margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
                  >
                    <defs>
                      <linearGradient id="projectTrendGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="#6366f1" stopOpacity={0.0} />
                      </linearGradient>
                    </defs>
                    <XAxis
                      dataKey="label"
                      stroke="#52525b"
                      fontSize={11}
                      tickLine={false}
                      axisLine={{ stroke: '#27272a' }}
                    />
                    <YAxis
                      stroke="#52525b"
                      fontSize={11}
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
                                Ingested Events:{' '}
                                <span className="font-bold text-white">
                                  {formatNumber(data.count)}
                                </span>
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
                      fill="url(#projectTrendGrad)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {/* Recent Issues Table */}
          <div className="p-5 rounded-xl bg-[#0f1118] border border-zinc-800/80 shadow-xs">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-sm font-semibold text-zinc-200 m-0">Recent Issues</h2>
                <p className="text-[11px] text-zinc-500">
                  Recently active fingerprint clusters in {selectedProject.name}
                </p>
              </div>

              <Link
                to="/issues"
                className="inline-flex items-center gap-1 text-xs font-medium text-indigo-400 hover:text-indigo-300 transition"
              >
                <span>View all issues</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>

            {isLoadingIssues ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <tbody>
                    <SkeletonRow cols={4} />
                    <SkeletonRow cols={4} />
                    <SkeletonRow cols={4} />
                  </tbody>
                </table>
              </div>
            ) : issues.length === 0 ? (
              <EmptyState
                icon={AlertOctagon}
                title="No Issues Captured Yet"
                description={`Project ${selectedProject.name} has not recorded any error events yet. Ingest an error event using our API or test simulator.`}
                action={
                  <button
                    onClick={() => setIsTestModalOpen(true)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white transition cursor-pointer"
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    Simulate First Error
                  </button>
                }
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-zinc-800 text-[11px] font-medium uppercase tracking-wider text-zinc-400">
                      <th className="py-2.5 px-3">Issue Title</th>
                      <th className="py-2.5 px-3">Fingerprint</th>
                      <th className="py-2.5 px-3 text-right">Occurrences</th>
                      <th className="py-2.5 px-3">Last Seen</th>
                      <th className="py-2.5 px-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/60 text-xs">
                    {recentIssues.map((issue) => (
                      <tr
                        key={issue.id}
                        className="group hover:bg-zinc-800/40 transition cursor-pointer"
                      >
                        <td className="py-3 px-3 font-medium text-zinc-200 max-w-xs truncate">
                          <Link
                            to={`/issues/${issue.id}`}
                            className="hover:text-indigo-300 block truncate"
                          >
                            {issue.title}
                          </Link>
                        </td>

                        <td className="py-3 px-3">
                          <button
                            onClick={(e) => handleCopyFingerprint(e, issue.fingerprint)}
                            title="Click to copy full fingerprint"
                            className="inline-flex items-center gap-1 font-mono text-[11px] text-zinc-400 hover:text-zinc-200 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800 transition cursor-pointer"
                          >
                            <span>{formatFingerprint(issue.fingerprint, 8)}</span>
                            {copiedFp === issue.fingerprint ? (
                              <Check className="h-3 w-3 text-emerald-400" />
                            ) : (
                              <Copy className="h-3 w-3 text-zinc-500 group-hover:text-zinc-400" />
                            )}
                          </button>
                        </td>

                        <td className="py-3 px-3 text-right">
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-rose-500/10 text-rose-300 border border-rose-500/20 font-mono">
                            {formatNumber(issue.count)}
                          </span>
                        </td>

                        <td className="py-3 px-3 text-zinc-400 text-xs whitespace-nowrap">
                          {formatRelativeTime(issue.last_seen)}
                        </td>

                        <td className="py-3 px-3 text-right">
                          <Link
                            to={`/issues/${issue.id}`}
                            className="inline-flex items-center gap-1 text-[11px] text-zinc-400 group-hover:text-indigo-400 font-medium transition"
                          >
                            <span>Inspect</span>
                            <ArrowRight className="h-3 w-3" />
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      <TestEventModal
        isOpen={isTestModalOpen}
        onClose={() => setIsTestModalOpen(false)}
        onEventSent={() => {
          fetchOverviewData();
          fetchTimeseries(trendRange);
        }}
      />
    </div>
  );
}

export default OverviewPage;
