import React, { useState, useEffect } from 'react';
import { useParams, useSearchParams, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useProject } from '../context/ProjectContext';
import api from '../services/api';
import {
  FolderGit2,
  Key,
  Layers,
  Terminal,
  Tag,
  Sliders,
  Check,
  Copy,
  Eye,
  EyeOff,
  AlertCircle,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Plus,
  ArrowLeft,
  ExternalLink,
  ShieldCheck,
  ShieldAlert,
  Send,
  HelpCircle,
  Flame,
  FileCode,
} from 'lucide-react';

export default function ProjectDetailPage() {
  const { projectId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { selectedTenant } = useAuth();
  const { selectedProject, selectProject, refreshProjects } = useProject();

  const activeTab = searchParams.get('tab') || 'overview';
  const setActiveTab = (tab) => {
    setSearchParams({ tab });
  };

  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Rename Project
  const [isEditingName, setIsEditingName] = useState(false);
  const [newName, setNewName] = useState('');
  const [savingName, setSavingName] = useState(false);

  // Credentials Tab
  const [revealKey, setRevealKey] = useState(false);
  const [copiedKey, setCopiedKey] = useState(false);
  const [unmaskedKey, setUnmaskedKey] = useState(null);
  const [keyPermissionDenied, setKeyPermissionDenied] = useState(null);
  const [fetchingKey, setFetchingKey] = useState(false);

  // Environments Tab
  const [environments, setEnvironments] = useState([]);
  const [loadingEnvs, setLoadingEnvs] = useState(false);
  const [showAddEnvModal, setShowAddEnvModal] = useState(false);
  const [envKey, setEnvKey] = useState('');
  const [envName, setEnvName] = useState('');
  const [savingEnv, setSavingEnv] = useState(false);
  const [copiedEnvKey, setCopiedEnvKey] = useState(null);

  // Releases Tab
  const [releases, setReleases] = useState([]);
  const [loadingReleases, setLoadingReleases] = useState(false);

  // Flags Tab
  const [flags, setFlags] = useState([]);
  const [loadingFlags, setLoadingFlags] = useState(false);

  // Send Test Event State
  const [sendingTestEvent, setSendingTestEvent] = useState(false);
  const [testEventStatus, setTestEventStatus] = useState('idle'); // 'idle' | 'queued' | 'completed' | 'timeout' | 'failed'
  const [testEventData, setTestEventData] = useState(null);
  const [testEventError, setTestEventError] = useState(null);

  // Copied code snippets
  const [copiedSnippet, setCopiedSnippet] = useState(null);

  const userRole = selectedTenant?.role || 'member';
  const canAdminister = userRole === 'owner' || userRole === 'admin';

  const fetchProjectDetails = async () => {
    if (!selectedTenant || !projectId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.getTenantProject(selectedTenant.id, projectId);
      setProject(data);
      setNewName(data.name);
    } catch (err) {
      setError(err.message || 'Failed to load project details');
    } finally {
      setLoading(false);
    }
  };

  const fetchEnvironments = async () => {
    if (!selectedTenant || !projectId) return;
    setLoadingEnvs(true);
    try {
      const envs = await api.getEnvironments(selectedTenant.id, projectId);
      setEnvironments(envs);
    } catch (err) {
      console.error('Failed to load environments:', err);
    } finally {
      setLoadingEnvs(false);
    }
  };

  const fetchReleases = async () => {
    if (!selectedTenant || !projectId) return;
    setLoadingReleases(true);
    try {
      const rels = await api.getReleases(selectedTenant.id, projectId);
      setReleases(rels);
    } catch (err) {
      console.error('Failed to load releases:', err);
    } finally {
      setLoadingReleases(false);
    }
  };

  const fetchFlags = async () => {
    if (!selectedTenant || !projectId) return;
    setLoadingFlags(true);
    try {
      const f = await api.getFeatureFlags(selectedTenant.id, projectId);
      setFlags(f);
    } catch (err) {
      console.error('Failed to load flags:', err);
    } finally {
      setLoadingFlags(false);
    }
  };

  useEffect(() => {
    fetchProjectDetails();
  }, [selectedTenant?.id, projectId]);

  useEffect(() => {
    if (activeTab === 'environments') {
      fetchEnvironments();
    } else if (activeTab === 'releases') {
      fetchReleases();
    } else if (activeTab === 'flags') {
      fetchFlags();
    }
  }, [activeTab, selectedTenant?.id, projectId]);

  const handleUpdateName = async (e) => {
    e.preventDefault();
    if (!newName.trim() || !canAdminister) return;
    setSavingName(true);
    try {
      const updated = await api.updateTenantProject(selectedTenant.id, projectId, newName.trim());
      setProject(updated);
      setIsEditingName(false);
      await refreshProjects();
    } catch (err) {
      alert(err.message || 'Failed to update project name');
    } finally {
      setSavingName(false);
    }
  };

  const handleRevealKey = async () => {
    if (revealKey) {
      setRevealKey(false);
      return;
    }
    if (!canAdminister) {
      setKeyPermissionDenied('Permission denied: Only organization owners and administrators can reveal project ingestion credentials.');
      return;
    }
    setKeyPermissionDenied(null);
    if (!unmaskedKey) {
      setFetchingKey(true);
      try {
        const res = await api.getProjectKey(selectedTenant.id, projectId);
        setUnmaskedKey(res.api_key);
        setRevealKey(true);
      } catch (err) {
        setKeyPermissionDenied(err.message || 'Permission denied: Insufficient permissions to retrieve credentials.');
      } finally {
        setFetchingKey(false);
      }
    } else {
      setRevealKey(true);
    }
  };

  const handleCopyKey = async () => {
    if (!canAdminister) {
      setKeyPermissionDenied('Permission denied: Only organization owners and administrators can copy project ingestion credentials.');
      return;
    }
    setKeyPermissionDenied(null);
    let keyToCopy = unmaskedKey;
    if (!keyToCopy) {
      setFetchingKey(true);
      try {
        const res = await api.getProjectKey(selectedTenant.id, projectId);
        setUnmaskedKey(res.api_key);
        keyToCopy = res.api_key;
      } catch (err) {
        setKeyPermissionDenied(err.message || 'Permission denied: Insufficient permissions to copy credentials.');
        setFetchingKey(false);
        return;
      } finally {
        setFetchingKey(false);
      }
    }
    if (keyToCopy) {
      navigator.clipboard.writeText(keyToCopy);
      setCopiedKey(true);
      setTimeout(() => setCopiedKey(false), 2000);
    }
  };

  const handleCreateEnvironment = async (e) => {
    e.preventDefault();
    if (!envKey.trim() || !envName.trim() || !selectedTenant) return;
    setSavingEnv(true);
    try {
      await api.createEnvironment(selectedTenant.id, projectId, {
        key: envKey.trim().toLowerCase(),
        name: envName.trim(),
      });
      setShowAddEnvModal(false);
      setEnvKey('');
      setEnvName('');
      fetchEnvironments();
    } catch (err) {
      alert(err.message || 'Failed to create environment');
    } finally {
      setSavingEnv(false);
    }
  };

  const handleCopySnippet = (snippetKey, text) => {
    navigator.clipboard.writeText(text);
    setCopiedSnippet(snippetKey);
    setTimeout(() => setCopiedSnippet(null), 2000);
  };

  const handleSendTestEvent = async () => {
    if (!selectedTenant || !projectId || sendingTestEvent) return;
    setSendingTestEvent(true);
    setTestEventError(null);
    setTestEventStatus('queued');
    setTestEventData(null);

    let eventId = null;
    try {
      // 1. Enqueue event to Redis stream via POST (returns 202 Accepted with status: pending)
      const initial = await api.sendProjectTestEvent(selectedTenant.id, projectId);
      eventId = initial.event_id;
      setTestEventData(initial);

      if (initial.status === 'completed') {
        setTestEventStatus('completed');
        setSendingTestEvent(false);
        fetchProjectDetails();
        return;
      }

      // 2. Poll status endpoint to verify real worker & database processing
      let attempts = 0;
      const maxAttempts = 20; // 20 * 1500ms = 30 seconds
      const poll = async () => {
        if (attempts >= maxAttempts) {
          setTestEventStatus('timeout');
          setTestEventError('Worker processing timed out after 30 seconds. Ensure the ingestion worker process is running.');
          setSendingTestEvent(false);
          return;
        }
        attempts++;
        try {
          const pollRes = await api.getProjectTestEvent(selectedTenant.id, projectId, eventId);
          setTestEventData(pollRes);
          if (pollRes.status === 'completed') {
            setTestEventStatus('completed');
            setSendingTestEvent(false);
            fetchProjectDetails();
          } else {
            // Still queued / pending in worker pipeline
            setTimeout(poll, 1500);
          }
        } catch (pollErr) {
          setTestEventStatus('failed');
          setTestEventError(pollErr.message || 'Error polling event processing status');
          setSendingTestEvent(false);
        }
      };

      setTimeout(poll, 1200);
    } catch (err) {
      setTestEventStatus('failed');
      setTestEventError(err.message || 'Failed to dispatch test verification event to queue');
      setSendingTestEvent(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center p-20">
        <Loader2 className="w-8 h-8 text-indigo-400 animate-spin mb-3" />
        <p className="text-sm text-slate-400">Loading project details...</p>
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="p-8 bg-slate-900/60 border border-slate-800 rounded-2xl text-center">
        <AlertCircle className="w-10 h-10 text-rose-400 mx-auto mb-3" />
        <h2 className="text-lg font-bold text-slate-100">Project Not Found</h2>
        <p className="text-sm text-slate-400 mt-1 mb-6">
          {error || 'The requested project could not be found or does not belong to this organization.'}
        </p>
        <Link
          to="/projects"
          className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-sm font-medium transition"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Projects
        </Link>
      </div>
    );
  }

  const isCurrentActive = selectedProject?.id === project.id;

  const pythonInstallSnippet = `pip install releaseguard-sdk`;

  const pythonEnvSnippet = `# In your production environment (.env / system variables)
RELEASEGUARD_API_KEY="${project.api_key || 'rg_live_••••••••••••'}"
RELEASEGUARD_ENDPOINT="${window.location.origin.includes('localhost') ? 'http://127.0.0.1:8000' : window.location.origin}"
RELEASEGUARD_ENVIRONMENT="production"`;

  const pythonInitSnippet = `import os
import releaseguard_sdk

# Initialize ReleaseGuard at application startup
releaseguard_sdk.init(
    project_id=${project.id},
    base_url=os.environ.get("RELEASEGUARD_ENDPOINT", "http://127.0.0.1:8000"),
    api_key=os.environ["RELEASEGUARD_API_KEY"],
    release=os.environ.get("RELEASEGUARD_RELEASE", "v1.0.0"),
    environment=os.environ.get("RELEASEGUARD_ENVIRONMENT", "production"),
)`;

  const pythonCaptureSnippet = `try:
    # Execute critical business logic
    process_transaction()
except Exception:
    # Captures stack trace, exception type, and metadata asynchronously
    releaseguard_sdk.capture_exception()
    raise`;

  return (
    <div className="space-y-6">
      {/* Top Breadcrumb & Actions Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <Link
            to="/projects"
            className="p-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-800 transition"
            title="Back to all projects"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>

          <div>
            <div className="flex items-center gap-2.5">
              {isEditingName ? (
                <form onSubmit={handleUpdateName} className="flex items-center gap-2">
                  <input
                    type="text"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    className="px-2.5 py-1 bg-slate-950 border border-indigo-500 rounded-lg text-lg font-bold text-slate-100 focus:outline-none"
                    autoFocus
                  />
                  <button
                    type="submit"
                    disabled={savingName || !newName.trim()}
                    className="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-500 text-xs font-medium text-white rounded-lg transition"
                  >
                    {savingName ? 'Saving...' : 'Save'}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setIsEditingName(false);
                      setNewName(project.name);
                    }}
                    className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-xs text-slate-300 rounded-lg transition"
                  >
                    Cancel
                  </button>
                </form>
              ) : (
                <div className="flex items-center gap-2.5">
                  <h1 className="text-2xl font-bold text-slate-100 tracking-tight">
                    {project.name}
                  </h1>
                  {canAdminister && (
                    <button
                      onClick={() => setIsEditingName(true)}
                      className="text-xs text-slate-500 hover:text-slate-300 transition"
                      title="Edit project name"
                    >
                      (Rename)
                    </button>
                  )}
                </div>
              )}

              <span className="font-mono text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                #{project.id}
              </span>
            </div>

            <p className="text-xs text-slate-400 mt-1">
              Organization: <span className="font-medium text-slate-300">{selectedTenant?.name}</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {!isCurrentActive ? (
            <button
              onClick={() => selectProject(project)}
              className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 transition"
            >
              <Check className="w-3.5 h-3.5 text-slate-400" />
              <span>Set as Active Project</span>
            </button>
          ) : (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/30 text-xs font-semibold text-indigo-400">
              <Check className="w-3.5 h-3.5" />
              Active Project
            </span>
          )}
        </div>
      </div>

      {/* Tabs Navigation */}
      <div className="flex items-center gap-2 overflow-x-auto border-b border-slate-800 pb-px">
        {[
          { key: 'overview', label: 'Overview', icon: FolderGit2 },
          { key: 'integration', label: 'Integration & Onboarding', icon: Terminal },
          { key: 'environments', label: 'Environments', icon: Layers },
          { key: 'credentials', label: 'API Credentials', icon: Key },
          { key: 'releases', label: 'Releases', icon: Tag },
          { key: 'flags', label: 'Feature Flags', icon: Sliders },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 px-4 py-2.5 border-b-2 text-xs font-semibold transition shrink-0 ${
                isActive
                  ? 'border-indigo-500 text-indigo-400 bg-indigo-500/5'
                  : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
              }`}
            >
              <Icon className="w-4 h-4" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* TAB 1: OVERVIEW */}
      {activeTab === 'overview' && (
        <div className="space-y-6 animate-in fade-in duration-100">
          {/* Summary Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="p-5 bg-slate-900/60 border border-slate-800 rounded-xl">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Total Issues</span>
                <div className="p-2 rounded-lg bg-rose-500/10 text-rose-400">
                  <Flame className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-3 text-2xl font-bold text-slate-100">{project.issues_count ?? 0}</div>
              <div className="mt-2">
                <Link to="/issues" className="text-xs text-indigo-400 hover:underline inline-flex items-center gap-1">
                  View issue tracker <ExternalLink className="w-3 h-3" />
                </Link>
              </div>
            </div>

            <div className="p-5 bg-slate-900/60 border border-slate-800 rounded-xl">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Environments</span>
                <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400">
                  <Layers className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-3 text-2xl font-bold text-slate-100">{project.environments_count ?? 3}</div>
              <div className="mt-2">
                <button onClick={() => setActiveTab('environments')} className="text-xs text-indigo-400 hover:underline">
                  Configure environments →
                </button>
              </div>
            </div>

            <div className="p-5 bg-slate-900/60 border border-slate-800 rounded-xl">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Releases Tracked</span>
                <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400">
                  <Tag className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-3 text-2xl font-bold text-slate-100">{project.releases_count ?? 0}</div>
              <div className="mt-2">
                <Link to="/releases" className="text-xs text-indigo-400 hover:underline inline-flex items-center gap-1">
                  View releases <ExternalLink className="w-3 h-3" />
                </Link>
              </div>
            </div>

            <div className="p-5 bg-slate-900/60 border border-slate-800 rounded-xl">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Latest Release</span>
                <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400">
                  <Tag className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-3 text-xl font-bold text-slate-100 truncate">
                {project.recent_release || 'No releases'}
              </div>
              <div className="mt-2 text-xs text-slate-500 font-mono">
                {project.recent_release ? 'Production release' : 'Deploy a release build'}
              </div>
            </div>
          </div>

          {/* Quick Setup Card */}
          <div className="p-6 bg-slate-900/40 border border-slate-800 rounded-2xl flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div>
              <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
                <Terminal className="w-5 h-5 text-indigo-400" />
                Application Integration Guide
              </h3>
              <p className="text-xs text-slate-400 mt-1 max-w-xl">
                Instrument your Python backend using the official ReleaseGuard SDK. Ingest exceptions, correlate releases, and verify your connection in minutes.
              </p>
            </div>
            <button
              onClick={() => setActiveTab('integration')}
              className="flex items-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold transition shadow-lg shadow-indigo-600/20 shrink-0"
            >
              <span>View Python SDK Setup</span>
              <ExternalLink className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* TAB 2: INTEGRATION & ONBOARDING */}
      {activeTab === 'integration' && (
        <div className="space-y-6 animate-in fade-in duration-100">
          <div className="p-5 bg-slate-900/60 border border-slate-800 rounded-2xl">
            <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
              <Terminal className="w-5 h-5 text-indigo-400" />
              Python SDK Integration Guide
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Follow these simple steps to install and initialize ReleaseGuard in your Python codebase.
            </p>
          </div>

          {/* Step 1: Install */}
          <div className="p-5 bg-slate-900/40 border border-slate-800 rounded-xl space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                <span className="w-5 h-5 rounded-full bg-indigo-600/20 text-indigo-400 border border-indigo-500/30 flex items-center justify-center text-xs font-bold">1</span>
                Install ReleaseGuard SDK
              </h3>
              <button
                onClick={() => handleCopySnippet('install', pythonInstallSnippet)}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-xs font-mono text-slate-300 transition"
              >
                {copiedSnippet === 'install' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedSnippet === 'install' ? 'Copied' : 'Copy'}</span>
              </button>
            </div>
            <pre className="p-3 bg-slate-950 rounded-lg text-xs font-mono text-indigo-300 border border-slate-800 overflow-x-auto">
              {pythonInstallSnippet}
            </pre>
          </div>

          {/* Step 2: Environment Variables */}
          <div className="p-5 bg-slate-900/40 border border-slate-800 rounded-xl space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                <span className="w-5 h-5 rounded-full bg-indigo-600/20 text-indigo-400 border border-indigo-500/30 flex items-center justify-center text-xs font-bold">2</span>
                Set Environment Variables
              </h3>
              <button
                onClick={() => handleCopySnippet('env', pythonEnvSnippet)}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-xs font-mono text-slate-300 transition"
              >
                {copiedSnippet === 'env' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedSnippet === 'env' ? 'Copied' : 'Copy'}</span>
              </button>
            </div>
            <pre className="p-3 bg-slate-950 rounded-lg text-xs font-mono text-slate-300 border border-slate-800 overflow-x-auto">
              {pythonEnvSnippet}
            </pre>
          </div>

          {/* Step 3: Initialization */}
          <div className="p-5 bg-slate-900/40 border border-slate-800 rounded-xl space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                <span className="w-5 h-5 rounded-full bg-indigo-600/20 text-indigo-400 border border-indigo-500/30 flex items-center justify-center text-xs font-bold">3</span>
                Initialize the Client
              </h3>
              <button
                onClick={() => handleCopySnippet('init', pythonInitSnippet)}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-xs font-mono text-slate-300 transition"
              >
                {copiedSnippet === 'init' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedSnippet === 'init' ? 'Copied' : 'Copy'}</span>
              </button>
            </div>
            <pre className="p-3 bg-slate-950 rounded-lg text-xs font-mono text-indigo-200 border border-slate-800 overflow-x-auto">
              {pythonInitSnippet}
            </pre>
          </div>

          {/* Step 4: Capture Exception */}
          <div className="p-5 bg-slate-900/40 border border-slate-800 rounded-xl space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                <span className="w-5 h-5 rounded-full bg-indigo-600/20 text-indigo-400 border border-indigo-500/30 flex items-center justify-center text-xs font-bold">4</span>
                Capture Exceptions & Errors
              </h3>
              <button
                onClick={() => handleCopySnippet('capture', pythonCaptureSnippet)}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-xs font-mono text-slate-300 transition"
              >
                {copiedSnippet === 'capture' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedSnippet === 'capture' ? 'Copied' : 'Copy'}</span>
              </button>
            </div>
            <pre className="p-3 bg-slate-950 rounded-lg text-xs font-mono text-emerald-300 border border-slate-800 overflow-x-auto">
              {pythonCaptureSnippet}
            </pre>
          </div>

          {/* Step 5: SEND TEST EVENT WORKFLOW */}
          <div className="p-6 bg-gradient-to-br from-indigo-950/40 to-slate-900 border border-indigo-500/30 rounded-2xl space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
                  <Send className="w-5 h-5 text-indigo-400" />
                  Verify Integration Pipeline
                </h3>
                <p className="text-xs text-slate-400 mt-1 max-w-lg">
                  Send an authenticated test error event directly through the ReleaseGuard ingestion pipeline (FastAPI → Redis Streams → Background Worker → PostgreSQL).
                </p>
              </div>

              <button
                onClick={handleSendTestEvent}
                disabled={sendingTestEvent}
                className="flex items-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl text-xs font-semibold transition shadow-lg shadow-indigo-600/20 shrink-0"
              >
                {sendingTestEvent ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Verifying Pipeline...</span>
                  </>
                ) : (
                  <>
                    <Send className="w-4 h-4" />
                    <span>Send Test Event</span>
                  </>
                )}
              </button>
            </div>

            {testEventError && (
              <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl text-xs text-rose-400 flex items-center gap-2 animate-in fade-in">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{testEventError}</span>
              </div>
            )}

            {/* State: Queued */}
            {testEventStatus === 'queued' && testEventData && (
              <div className="p-4 bg-indigo-950/40 border border-indigo-500/40 rounded-xl space-y-3 animate-in fade-in duration-150">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-indigo-300 text-sm font-semibold">
                    <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
                    <span>Queued in Redis Stream — Polling for Worker Completion...</span>
                  </div>
                  <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                    Queued
                  </span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                  <div className="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800">
                    <span className="text-slate-500 uppercase tracking-wider text-[10px] font-semibold block">Event ID</span>
                    <span className="font-mono text-slate-300 break-all">{testEventData.event_id}</span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800">
                    <span className="text-slate-500 uppercase tracking-wider text-[10px] font-semibold block">Pipeline Processing</span>
                    <span className="font-mono text-amber-400 flex items-center gap-1.5 mt-0.5">
                      <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                      Pending worker fingerprinting & database persistence
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* State: Completed */}
            {testEventStatus === 'completed' && testEventData && (
              <div className="p-4 bg-emerald-950/30 border border-emerald-500/40 rounded-xl space-y-3 animate-in fade-in duration-150">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-emerald-400 text-sm font-semibold">
                    <CheckCircle2 className="w-5 h-5 shrink-0" />
                    <span>Integration connected ✅</span>
                  </div>
                  <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                    Verified
                  </span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                  <div className="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800">
                    <span className="text-slate-500 uppercase tracking-wider text-[10px] font-semibold block">Event ID</span>
                    <span className="font-mono text-slate-300 break-all">{testEventData.event_id}</span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800">
                    <span className="text-slate-500 uppercase tracking-wider text-[10px] font-semibold block">Issue Record</span>
                    {testEventData.issue_id ? (
                      <Link
                        to={`/issues/${testEventData.issue_id}`}
                        className="font-mono text-indigo-400 hover:underline inline-flex items-center gap-1 font-semibold"
                      >
                        Issue #{testEventData.issue_id} <ExternalLink className="w-3 h-3" />
                      </Link>
                    ) : (
                      <span className="font-mono text-slate-400">Processing...</span>
                    )}
                  </div>
                  <div className="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800">
                    <span className="text-slate-500 uppercase tracking-wider text-[10px] font-semibold block">Timestamp</span>
                    <span className="font-mono text-slate-300">
                      {testEventData.timestamp ? new Date(testEventData.timestamp).toLocaleTimeString() : 'Just now'}
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* State: Timeout */}
            {testEventStatus === 'timeout' && (
              <div className="p-4 bg-amber-950/30 border border-amber-500/40 rounded-xl space-y-2 animate-in fade-in duration-150">
                <div className="flex items-center gap-2 text-amber-400 text-sm font-semibold">
                  <AlertCircle className="w-5 h-5 shrink-0" />
                  <span>Pipeline Timeout</span>
                </div>
                <p className="text-xs text-amber-200 leading-relaxed">
                  The test event was successfully accepted into Redis, but background worker processing did not complete within 30 seconds. Verify that the ingestion worker service (<code className="bg-slate-950 px-1 py-0.5 rounded text-amber-300">python -m app.worker</code>) is active.
                </p>
                {testEventData?.event_id && (
                  <p className="text-xs text-slate-400 font-mono">
                    Enqueued Event ID: {testEventData.event_id}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 3: ENVIRONMENTS */}
      {activeTab === 'environments' && (
        <div className="space-y-6 animate-in fade-in duration-100">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                <Layers className="w-5 h-5 text-indigo-400" />
                Project Environments
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                Configure deployment environments (production, staging, development) for release tracking and targeted rollouts.
              </p>
            </div>

            {canAdminister && (
              <button
                onClick={() => setShowAddEnvModal(true)}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold transition shadow-lg shadow-indigo-600/20"
              >
                <Plus className="w-4 h-4" />
                Add Environment
              </button>
            )}
          </div>

          {loadingEnvs ? (
            <div className="flex items-center justify-center p-12">
              <Loader2 className="w-6 h-6 text-indigo-400 animate-spin" />
            </div>
          ) : environments.length === 0 ? (
            <div className="text-center p-12 bg-slate-900/40 rounded-xl border border-slate-800">
              <Layers className="w-10 h-10 text-slate-600 mx-auto mb-2" />
              <h3 className="text-sm font-semibold text-slate-200">No custom environments yet</h3>
              <p className="text-xs text-slate-400 mt-1">
                Standard environments (production, staging, development) are automatically available.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {environments.map((env) => (
                <div
                  key={env.id}
                  className="p-5 bg-slate-900/60 border border-slate-800 rounded-xl space-y-3"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold px-2 py-0.5 rounded uppercase tracking-wider bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                      {env.key}
                    </span>
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(env.key);
                        setCopiedEnvKey(env.key);
                        setTimeout(() => setCopiedEnvKey(null), 2000);
                      }}
                      className="p-1 hover:text-slate-200 text-slate-500 transition rounded"
                      title="Copy environment key"
                    >
                      {copiedEnvKey === env.key ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                  <div>
                    <h4 className="text-base font-bold text-slate-100">{env.name}</h4>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      Created: {new Date(env.created_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Add Environment Modal */}
          {showAddEnvModal && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
              <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl">
                <h2 className="text-lg font-bold text-slate-100">Add New Environment</h2>
                <p className="text-xs text-slate-400 mt-1">
                  Define an environment identifier for scoping feature flags and releases.
                </p>

                <form onSubmit={handleCreateEnvironment} className="mt-5 space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Environment Key (slug) <span className="text-rose-400">*</span>
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. qa, uat, canary"
                      value={envKey}
                      onChange={(e) => setEnvKey(e.target.value)}
                      className="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-xs font-mono text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Display Name <span className="text-rose-400">*</span>
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. QA Environment"
                      value={envName}
                      onChange={(e) => setEnvName(e.target.value)}
                      className="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                    />
                  </div>

                  <div className="flex items-center justify-end gap-3 pt-3">
                    <button
                      type="button"
                      onClick={() => setShowAddEnvModal(false)}
                      className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-slate-200"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={savingEnv || !envKey.trim() || !envName.trim()}
                      className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl text-xs font-semibold"
                    >
                      {savingEnv ? 'Creating...' : 'Create Environment'}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 4: API CREDENTIALS */}
      {activeTab === 'credentials' && (
        <div className="space-y-6 animate-in fade-in duration-100">
          {/* Security Warning Banner */}
          <div className="p-4 bg-amber-950/20 border border-amber-600/30 rounded-2xl flex items-start gap-3">
            <ShieldAlert className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            <div className="text-xs text-amber-200 leading-relaxed">
              <strong className="text-amber-300 block mb-1">Ingestion credentials must be kept confidential</strong>
              Project API keys authorize error ingestion and metric capture. Never commit credentials to public Git repositories, embed them in client-side Web / React code, or store them in unsecured browser localStorage. Always configure them as server-side environment variables.
            </div>
          </div>

          {/* Credential Card */}
          <div className="p-6 bg-slate-900/60 border border-slate-800 rounded-2xl space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
                  <Key className="w-4 h-4 text-indigo-400" />
                  Project Ingestion Key
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Scoped strictly to project #{project.id} ({project.name}).
                </p>
              </div>

              {canAdminister ? (
                <span className="text-[11px] font-semibold text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded-full border border-emerald-500/20">
                  Active & Authorized
                </span>
              ) : (
                <span className="text-[11px] font-semibold text-amber-400 bg-amber-500/10 px-2.5 py-1 rounded-full border border-amber-500/20">
                  Member (Masked Only)
                </span>
              )}
            </div>

            {keyPermissionDenied && (
              <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-xs text-rose-300 flex items-center gap-2 animate-in fade-in">
                <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0" />
                <span>{keyPermissionDenied}</span>
              </div>
            )}

            <div className="flex items-center gap-2 p-3 bg-slate-950 rounded-xl border border-slate-800/90 font-mono text-sm">
              <span className="flex-1 truncate text-slate-200 select-all">
                {revealKey && unmaskedKey
                  ? unmaskedKey
                  : (project.api_key || 'rg_live_••••••••••••••••••••••••')}
              </span>

              <button
                type="button"
                onClick={handleRevealKey}
                disabled={fetchingKey}
                className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 disabled:opacity-50 transition"
                title={revealKey ? 'Hide secret' : 'Reveal secret'}
              >
                {fetchingKey ? (
                  <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
                ) : revealKey ? (
                  <EyeOff className="w-4 h-4" />
                ) : (
                  <Eye className="w-4 h-4" />
                )}
              </button>

              <button
                type="button"
                onClick={handleCopyKey}
                disabled={fetchingKey}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold transition"
              >
                {copiedKey ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                <span>{copiedKey ? 'Copied!' : 'Copy Key'}</span>
              </button>
            </div>

            {!canAdminister && (
              <p className="text-xs text-slate-400">
                🔒 Plaintext ingestion credentials can only be revealed or copied by organization owners and administrators.
              </p>
            )}

            <div className="pt-2 text-xs text-slate-500 flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
              <span>Multi-tenant tenant isolation prevents this credential from modifying or inspecting other projects.</span>
            </div>
          </div>
        </div>
      )}

      {/* TAB 5: RELEASES */}
      {activeTab === 'releases' && (
        <div className="space-y-6 animate-in fade-in duration-100">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                <Tag className="w-5 h-5 text-indigo-400" />
                Project Releases
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                Release deployments correlated with project #{project.id}.
              </p>
            </div>
            <Link
              to="/releases"
              className="flex items-center gap-1.5 px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-semibold border border-slate-700 transition"
            >
              <span>Manage Releases</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </Link>
          </div>

          {loadingReleases ? (
            <div className="flex items-center justify-center p-12">
              <Loader2 className="w-6 h-6 text-indigo-400 animate-spin" />
            </div>
          ) : releases.length === 0 ? (
            <div className="text-center p-12 bg-slate-900/40 rounded-xl border border-slate-800">
              <Tag className="w-10 h-10 text-slate-600 mx-auto mb-2" />
              <h3 className="text-sm font-semibold text-slate-200">No releases registered for this project</h3>
              <p className="text-xs text-slate-400 mt-1">
                Create a release or pass the release parameter in the SDK to track builds.
              </p>
            </div>
          ) : (
            <div className="border border-slate-800 rounded-xl overflow-hidden">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-900/80 text-slate-400 border-b border-slate-800 uppercase tracking-wider font-semibold">
                  <tr>
                    <th className="px-4 py-3">Version</th>
                    <th className="px-4 py-3">Environment</th>
                    <th className="px-4 py-3">Commit SHA</th>
                    <th className="px-4 py-3">Registered</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 bg-slate-900/40 text-slate-300">
                  {releases.map((rel) => (
                    <tr key={rel.id} className="hover:bg-slate-800/40">
                      <td className="px-4 py-3 font-semibold text-slate-100">{rel.version}</td>
                      <td className="px-4 py-3">
                        <span className="px-2 py-0.5 rounded uppercase font-semibold text-[10px] bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                          {rel.environment}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-mono text-slate-400">
                        {rel.commit_sha ? rel.commit_sha.slice(0, 7) : '—'}
                      </td>
                      <td className="px-4 py-3 text-slate-400">
                        {new Date(rel.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* TAB 6: FEATURE FLAGS */}
      {activeTab === 'flags' && (
        <div className="space-y-6 animate-in fade-in duration-100">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                <Sliders className="w-5 h-5 text-indigo-400" />
                Project Feature Flags
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                Dynamic configurations and rollouts for project #{project.id}.
              </p>
            </div>
            <Link
              to="/feature-flags"
              className="flex items-center gap-1.5 px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-semibold border border-slate-700 transition"
            >
              <span>Manage Flags</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </Link>
          </div>

          {loadingFlags ? (
            <div className="flex items-center justify-center p-12">
              <Loader2 className="w-6 h-6 text-indigo-400 animate-spin" />
            </div>
          ) : flags.length === 0 ? (
            <div className="text-center p-12 bg-slate-900/40 rounded-xl border border-slate-800">
              <Sliders className="w-10 h-10 text-slate-600 mx-auto mb-2" />
              <h3 className="text-sm font-semibold text-slate-200">No feature flags created yet</h3>
              <p className="text-xs text-slate-400 mt-1">
                Configure deterministic percentage rollouts and environment targeting rules.
              </p>
            </div>
          ) : (
            <div className="border border-slate-800 rounded-xl overflow-hidden">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-900/80 text-slate-400 border-b border-slate-800 uppercase tracking-wider font-semibold">
                  <tr>
                    <th className="px-4 py-3">Flag Name</th>
                    <th className="px-4 py-3">Flag Key</th>
                    <th className="px-4 py-3">Description</th>
                    <th className="px-4 py-3">Created</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 bg-slate-900/40 text-slate-300">
                  {flags.map((flag) => (
                    <tr key={flag.id} className="hover:bg-slate-800/40">
                      <td className="px-4 py-3 font-semibold text-slate-100">{flag.name}</td>
                      <td className="px-4 py-3 font-mono text-indigo-300">{flag.key}</td>
                      <td className="px-4 py-3 text-slate-400 truncate max-w-xs">{flag.description || '—'}</td>
                      <td className="px-4 py-3 text-slate-400">
                        {new Date(flag.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
