import React, { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  Search,
  SlidersHorizontal,
  ArrowUpDown,
  AlertOctagon,
  Copy,
  Check,
  ArrowRight,
  RefreshCw,
  FolderGit2,
  Sparkles,
} from 'lucide-react';
import { useProject } from '../context/ProjectContext';
import api from '../services/api';
import {
  formatRelativeTime,
  formatExactTimestamp,
  formatNumber,
  formatFingerprint,
} from '../utils/formatters';
import { Badge } from '../components/common/Badge';
import { SkeletonRow } from '../components/common/LoadingState';
import { EmptyState } from '../components/common/EmptyState';
import { ErrorState } from '../components/common/ErrorState';
import TestEventModal from '../components/events/TestEventModal';

export function IssuesPage() {
  const { selectedProject, isLoading: isProjectLoading } = useProject();
  const [issues, setIssues] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState('last_seen_desc');
  const [copiedFp, setCopiedFp] = useState(null);
  const [isTestModalOpen, setIsTestModalOpen] = useState(false);

  const fetchIssues = async () => {
    if (!selectedProject) {
      setIssues([]);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const data = await api.getIssues(selectedProject.id);
      setIssues(data);
    } catch (err) {
      console.error('Failed to fetch issues:', err);
      setError(err.message || 'Failed to fetch issues');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchIssues();
  }, [selectedProject?.id]);

  const handleCopyFingerprint = (e, fp) => {
    e.stopPropagation();
    navigator.clipboard.writeText(fp);
    setCopiedFp(fp);
    setTimeout(() => setCopiedFp(null), 2000);
  };

  // Filter and sort issues
  const filteredIssues = useMemo(() => {
    let result = [...issues];

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      result = result.filter(
        (issue) =>
          issue.title.toLowerCase().includes(q) ||
          issue.fingerprint.toLowerCase().includes(q)
      );
    }

    result.sort((a, b) => {
      switch (sortBy) {
        case 'count_desc':
          return b.count - a.count;
        case 'count_asc':
          return a.count - b.count;
        case 'first_seen_desc':
          return new Date(b.first_seen) - new Date(a.first_seen);
        case 'last_seen_asc':
          return new Date(a.last_seen) - new Date(b.last_seen);
        case 'last_seen_desc':
        default:
          return new Date(b.last_seen) - new Date(a.last_seen);
      }
    });

    return result;
  }, [issues, searchQuery, sortBy]);

  if (isProjectLoading) {
    return (
      <div className="space-y-4">
        <div className="h-8 bg-zinc-900 rounded w-1/4 animate-pulse"></div>
        <div className="h-64 bg-zinc-900 rounded animate-pulse"></div>
      </div>
    );
  }

  if (!selectedProject) {
    return (
      <EmptyState
        icon={FolderGit2}
        title="No Project Selected"
        description="Select or create a project to inspect captured issues."
      />
    );
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-150">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-zinc-800/80">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h1 className="text-xl font-bold tracking-tight text-white m-0">Issues</h1>
            <Badge variant="mono">{filteredIssues.length} total</Badge>
          </div>
          <p className="text-xs text-zinc-400">
            Deduplicated failure clusters grouped by stable error fingerprint.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={fetchIssues}
            disabled={isLoading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-zinc-300 hover:text-white bg-zinc-900 hover:bg-zinc-800 border border-zinc-700/80 transition"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>

          <button
            type="button"
            onClick={() => setIsTestModalOpen(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white transition shadow-sm"
          >
            <Sparkles className="h-3.5 w-3.5" />
            <span>Simulate Error</span>
          </button>
        </div>
      </div>

      {/* Search and Sort Toolbar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-3 rounded-xl bg-[#0f1118] border border-zinc-800/80">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-zinc-500" />
          <input
            type="text"
            placeholder="Search by title or fingerprint..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 text-xs bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-indigo-500 transition"
          />
        </div>

        <div className="flex items-center gap-2 self-end sm:self-auto">
          <span className="text-[11px] text-zinc-500 whitespace-nowrap">Sort by:</span>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="px-2.5 py-1.5 text-xs bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-200 focus:outline-none focus:border-indigo-500 transition cursor-pointer"
          >
            <option value="last_seen_desc">Last Seen (Newest)</option>
            <option value="last_seen_asc">Last Seen (Oldest)</option>
            <option value="count_desc">Occurrences (Highest)</option>
            <option value="count_asc">Occurrences (Lowest)</option>
            <option value="first_seen_desc">First Seen (Newest)</option>
          </select>
        </div>
      </div>

      {/* Main Table / States */}
      {error ? (
        <ErrorState message={error} onRetry={fetchIssues} />
      ) : isLoading ? (
        <div className="rounded-xl border border-zinc-800/80 bg-[#0f1118] overflow-hidden">
          <table className="w-full text-left">
            <tbody>
              <SkeletonRow cols={5} />
              <SkeletonRow cols={5} />
              <SkeletonRow cols={5} />
              <SkeletonRow cols={5} />
            </tbody>
          </table>
        </div>
      ) : filteredIssues.length === 0 ? (
        <EmptyState
          icon={AlertOctagon}
          title={searchQuery ? 'No Matching Issues' : 'No Issues Found'}
          description={
            searchQuery
              ? `No issues matched query "${searchQuery}". Try adjusting your search.`
              : `Project ${selectedProject.name} has no recorded issues yet.`
          }
          action={
            searchQuery ? (
              <button
                onClick={() => setSearchQuery('')}
                className="px-3 py-1.5 rounded-lg text-xs font-medium bg-zinc-800 text-zinc-200 hover:bg-zinc-700 transition"
              >
                Clear Search Filter
              </button>
            ) : (
              <button
                onClick={() => setIsTestModalOpen(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white transition"
              >
                <Sparkles className="h-3.5 w-3.5" />
                Simulate First Error
              </button>
            )
          }
        />
      ) : (
        <div className="rounded-xl border border-zinc-800/80 bg-[#0f1118] overflow-hidden shadow-xs">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-zinc-800 text-[11px] font-medium uppercase tracking-wider text-zinc-400 bg-zinc-950/40">
                  <th className="py-3 px-4">Issue</th>
                  <th className="py-3 px-4">Fingerprint</th>
                  <th className="py-3 px-4 text-right">Occurrences</th>
                  <th className="py-3 px-4">First Seen</th>
                  <th className="py-3 px-4">Last Seen</th>
                  <th className="py-3 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60 text-xs">
                {filteredIssues.map((issue) => (
                  <tr
                    key={issue.id}
                    className="group hover:bg-zinc-800/30 transition cursor-pointer"
                  >
                    {/* Title */}
                    <td className="py-3.5 px-4 font-medium text-zinc-200 max-w-sm">
                      <Link
                        to={`/issues/${issue.id}`}
                        className="hover:text-indigo-300 block truncate"
                        title={issue.title}
                      >
                        <div className="flex items-center gap-2 truncate">
                          <span className="text-[10px] font-mono text-zinc-500">#{issue.id}</span>
                          <span className="truncate">{issue.title}</span>
                        </div>
                      </Link>
                    </td>

                    {/* Fingerprint */}
                    <td className="py-3.5 px-4 whitespace-nowrap">
                      <button
                        onClick={(e) => handleCopyFingerprint(e, issue.fingerprint)}
                        title="Click to copy full fingerprint"
                        className="inline-flex items-center gap-1 font-mono text-[11px] text-zinc-400 hover:text-zinc-200 bg-zinc-950 px-2 py-0.5 rounded border border-zinc-800/90 hover:border-zinc-700 transition"
                      >
                        <span>{formatFingerprint(issue.fingerprint, 10)}</span>
                        {copiedFp === issue.fingerprint ? (
                          <Check className="h-3 w-3 text-emerald-400" />
                        ) : (
                          <Copy className="h-3 w-3 text-zinc-500 group-hover:text-zinc-400" />
                        )}
                      </button>
                    </td>

                    {/* Occurrence count */}
                    <td className="py-3.5 px-4 text-right whitespace-nowrap">
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-rose-500/10 text-rose-300 border border-rose-500/20 font-mono">
                        {formatNumber(issue.count)}
                      </span>
                    </td>

                    {/* First seen */}
                    <td
                      className="py-3.5 px-4 text-zinc-400 whitespace-nowrap"
                      title={formatExactTimestamp(issue.first_seen)}
                    >
                      {formatRelativeTime(issue.first_seen)}
                    </td>

                    {/* Last seen */}
                    <td
                      className="py-3.5 px-4 text-zinc-400 whitespace-nowrap"
                      title={formatExactTimestamp(issue.last_seen)}
                    >
                      {formatRelativeTime(issue.last_seen)}
                    </td>

                    {/* Action */}
                    <td className="py-3.5 px-4 text-right whitespace-nowrap">
                      <Link
                        to={`/issues/${issue.id}`}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded text-[11px] font-medium text-zinc-300 hover:text-white bg-zinc-900 hover:bg-zinc-800 border border-zinc-700/80 transition"
                      >
                        <span>Details</span>
                        <ArrowRight className="h-3 w-3" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <TestEventModal
        isOpen={isTestModalOpen}
        onClose={() => setIsTestModalOpen(false)}
        onEventSent={() => fetchIssues()}
      />
    </div>
  );
}

export default IssuesPage;
