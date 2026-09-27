import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { useProject } from '../context/ProjectContext';
import api from '../services/api';
import {
  ToggleLeft,
  ToggleRight,
  Plus,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Sliders,
  ShieldAlert,
  History,
  Trash2,
  Layers,
  ChevronRight,
  Sparkles,
  AlertTriangle,
} from 'lucide-react';

export default function FeatureFlagsPage() {
  const { selectedTenant } = useAuth();
  const { selectedProject: currentProject } = useProject();

  const [flags, setFlags] = useState([]);
  const [environments, setEnvironments] = useState([]);
  const [selectedEnvKey, setSelectedEnvKey] = useState('production');
  const [selectedFlag, setSelectedFlag] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Create Flag Modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newKey, setNewKey] = useState('');
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  // Audit Logs State
  const [auditLogs, setAuditLogs] = useState([]);
  const [loadingLogs, setLoadingLogs] = useState(false);

  // Targeting Rules State
  const [showRuleModal, setShowRuleModal] = useState(false);
  const [ruleAttr, setRuleAttr] = useState('user_id');
  const [ruleOp, setRuleOp] = useState('equals');
  const [ruleVals, setRuleVals] = useState('');
  const [ruleVariant, setRuleVariant] = useState('on');

  const fetchEnvironmentsAndFlags = async () => {
    if (!selectedTenant || !currentProject) return;
    setLoading(true);
    setError(null);
    try {
      const [envsData, flagsData] = await Promise.all([
        api.getEnvironments(selectedTenant.id, currentProject.id),
        api.getFeatureFlags(selectedTenant.id, currentProject.id),
      ]);
      setEnvironments(envsData);
      setFlags(flagsData);

      // Keep selected flag updated if already open
      if (selectedFlag) {
        const refreshed = flagsData.find((f) => f.id === selectedFlag.id);
        if (refreshed) setSelectedFlag(refreshed);
      }
    } catch (err) {
      setError(err.message || 'Failed to load feature flags');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEnvironmentsAndFlags();
  }, [selectedTenant, currentProject]);

  const activeEnv = environments.find((e) => e.key === selectedEnvKey) || environments[0];

  const getFlagSetting = (flag) => {
    if (!flag || !activeEnv) return null;
    return flag.settings?.find((s) => s.environment_id === activeEnv.id) || null;
  };

  const handleCreateFlag = async (e) => {
    e.preventDefault();
    if (!newKey.trim() || !newName.trim()) return;
    setSubmitting(true);
    setFormError(null);
    try {
      await api.createFeatureFlag(selectedTenant.id, currentProject.id, {
        key: newKey.trim(),
        name: newName.trim(),
        description: newDesc.trim() || null,
      });
      setShowCreateModal(false);
      setNewKey('');
      setNewName('');
      setNewDesc('');
      fetchEnvironmentsAndFlags();
    } catch (err) {
      setFormError(err.message || 'Failed to create flag');
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggleSetting = async (flag, currentEnabled) => {
    const setting = getFlagSetting(flag);
    if (!setting) return;
    try {
      await api.updateFlagSetting(selectedTenant.id, currentProject.id, flag.id, setting.environment_id, {
        enabled: !currentEnabled,
      });
      fetchEnvironmentsAndFlags();
    } catch (err) {
      alert(err.message || 'Failed to update flag state');
    }
  };

  const handleUpdateRollout = async (flag, percentage) => {
    const setting = getFlagSetting(flag);
    if (!setting) return;
    try {
      await api.updateFlagRollout(selectedTenant.id, currentProject.id, flag.id, setting.environment_id, {
        percentage,
      });
      fetchEnvironmentsAndFlags();
    } catch (err) {
      alert(err.message || 'Failed to update rollout');
    }
  };

  const handleKillSwitch = async (flag) => {
    const setting = getFlagSetting(flag);
    if (!setting) return;
    if (
      !window.confirm(
        `EMERGENCY KILL SWITCH: Are you sure you want to kill '${flag.name}' in ${activeEnv?.name}? This immediately disables the flag and resets rollout to 0%.`
      )
    ) {
      return;
    }
    try {
      await api.killFlag(selectedTenant.id, currentProject.id, flag.id, setting.environment_id);
      fetchEnvironmentsAndFlags();
    } catch (err) {
      alert(err.message || 'Kill switch failed');
    }
  };

  const handleAddRule = async (e) => {
    e.preventDefault();
    const setting = getFlagSetting(selectedFlag);
    if (!setting || !ruleVals.trim()) return;

    const valuesList = ruleVals
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);

    const existingRules = setting.rules?.map((r) => ({
      priority: r.priority,
      attribute: r.attribute,
      operator: r.operator,
      values: r.values,
      variant: r.variant,
    })) || [];

    const newRules = [
      ...existingRules,
      {
        priority: existingRules.length,
        attribute: ruleAttr,
        operator: ruleOp,
        values: valuesList,
        variant: ruleVariant,
      },
    ];

    try {
      await api.setFlagRules(selectedTenant.id, currentProject.id, selectedFlag.id, setting.environment_id, newRules);
      setShowRuleModal(false);
      setRuleVals('');
      fetchEnvironmentsAndFlags();
    } catch (err) {
      alert(err.message || 'Failed to add rule');
    }
  };

  const handleRemoveRule = async (ruleIdx) => {
    const setting = getFlagSetting(selectedFlag);
    if (!setting) return;

    const updatedRules = setting.rules
      .filter((_, idx) => idx !== ruleIdx)
      .map((r, idx) => ({
        priority: idx,
        attribute: r.attribute,
        operator: r.operator,
        values: r.values,
        variant: r.variant,
      }));

    try {
      await api.setFlagRules(selectedTenant.id, currentProject.id, selectedFlag.id, setting.environment_id, updatedRules);
      fetchEnvironmentsAndFlags();
    } catch (err) {
      alert(err.message || 'Failed to remove rule');
    }
  };

  const fetchAuditLogs = async (flagId) => {
    setLoadingLogs(true);
    try {
      const logs = await api.getFlagAuditLogs(selectedTenant.id, currentProject.id, flagId);
      setAuditLogs(logs);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingLogs(false);
    }
  };

  const selectFlagForDetail = (flag) => {
    setSelectedFlag(flag);
    fetchAuditLogs(flag.id);
  };

  const selectedSetting = selectedFlag ? getFlagSetting(selectedFlag) : null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 tracking-tight flex items-center gap-2.5">
            <Sliders className="w-6 h-6 text-indigo-400" />
            Feature Flags & Rollouts
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Deterministic feature toggles, targeting rules, and instant kill switches
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={fetchEnvironmentsAndFlags}
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
            Create Flag
          </button>
        </div>
      </div>

      {/* Environment Selector Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-800 pb-3">
        <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider mr-2">Environment:</span>
        {environments.map((env) => (
          <button
            key={env.id}
            onClick={() => setSelectedEnvKey(env.key)}
            className={`px-4 py-1.5 rounded-lg text-xs font-medium transition ${
              selectedEnvKey === env.key
                ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/20'
                : 'bg-slate-800/80 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            {env.name}
          </button>
        ))}
      </div>

      {error && (
        <div className="p-4 bg-rose-500/10 border border-rose-500/20 rounded-xl text-sm text-rose-400 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* Main Grid: Flags List & Detail Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Flag List (7 Cols) */}
        <div className="lg:col-span-7 space-y-3">
          {loading ? (
            <div className="flex items-center justify-center p-16">
              <RefreshCw className="w-8 h-8 text-indigo-400 animate-spin" />
            </div>
          ) : flags.length === 0 ? (
            <div className="text-center p-16 bg-slate-900/40 rounded-xl border border-slate-800/80">
              <Sliders className="w-12 h-12 text-slate-600 mx-auto mb-3" />
              <h3 className="text-base font-semibold text-slate-200">No feature flags configured</h3>
              <p className="text-sm text-slate-400 max-w-sm mx-auto mt-1 mb-6">
                Create your first flag to enable gradual rollouts and runtime control.
              </p>
              <button
                onClick={() => setShowCreateModal(true)}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium transition"
              >
                Create Flag
              </button>
            </div>
          ) : (
            flags.map((flag) => {
              const setting = getFlagSetting(flag);
              const isSelected = selectedFlag?.id === flag.id;
              const isEnabled = setting?.enabled;
              const pct = setting?.rollout_percentage || 0;

              return (
                <div
                  key={flag.id}
                  onClick={() => selectFlagForDetail(flag)}
                  className={`p-4 rounded-xl border transition cursor-pointer ${
                    isSelected
                      ? 'bg-slate-800/90 border-indigo-500/80 shadow-lg shadow-indigo-500/10'
                      : 'bg-slate-900/60 border-slate-800 hover:border-slate-700 hover:bg-slate-800/50'
                  }`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2.5">
                        <span className="font-semibold text-slate-100">{flag.name}</span>
                        <code className="px-2 py-0.5 bg-slate-800 text-indigo-300 text-xs font-mono rounded">
                          {flag.key}
                        </code>
                      </div>
                      {flag.description && <p className="text-xs text-slate-400 line-clamp-1">{flag.description}</p>}
                    </div>

                    <div className="flex items-center gap-3">
                      {/* State Badge */}
                      <span
                        className={`px-2.5 py-1 rounded-full text-xs font-medium border flex items-center gap-1.5 ${
                          isEnabled
                            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                            : 'bg-slate-800 text-slate-400 border-slate-700'
                        }`}
                      >
                        {isEnabled ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
                        {isEnabled ? `${pct}% Rollout` : 'Disabled'}
                      </span>
                      <ChevronRight className="w-4 h-4 text-slate-500" />
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Flag Detail Drawer / Configurator (5 Cols) */}
        <div className="lg:col-span-5">
          {selectedFlag && selectedSetting ? (
            <div className="bg-slate-900/80 rounded-2xl border border-slate-800 p-6 space-y-6 shadow-xl sticky top-6">
              {/* Detail Header */}
              <div className="flex items-start justify-between border-b border-slate-800 pb-4">
                <div>
                  <h2 className="text-lg font-bold text-slate-100">{selectedFlag.name}</h2>
                  <p className="text-xs font-mono text-indigo-400">{selectedFlag.key}</p>
                </div>
                <button
                  onClick={() => handleKillSwitch(selectedFlag)}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 rounded-lg text-xs font-semibold transition"
                  title="Emergency Kill Switch"
                >
                  <ShieldAlert className="w-3.5 h-3.5" />
                  Kill Switch
                </button>
              </div>

              {/* State Toggle */}
              <div className="flex items-center justify-between bg-slate-800/40 p-4 rounded-xl border border-slate-800">
                <div>
                  <div className="text-sm font-semibold text-slate-200">Flag State</div>
                  <div className="text-xs text-slate-400">
                    {selectedSetting.enabled ? 'Active in ' + activeEnv?.name : 'Turned off in ' + activeEnv?.name}
                  </div>
                </div>
                <button
                  onClick={() => handleToggleSetting(selectedFlag, selectedSetting.enabled)}
                  className="transition"
                >
                  {selectedSetting.enabled ? (
                    <ToggleRight className="w-10 h-10 text-emerald-400" />
                  ) : (
                    <ToggleLeft className="w-10 h-10 text-slate-600" />
                  )}
                </button>
              </div>

              {/* Rollout Percentage Controls */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                    Gradual Rollout: {selectedSetting.rollout_percentage}%
                  </label>
                  <span className="text-xs text-slate-500 font-mono">Salt: {selectedSetting.rollout_salt.slice(0, 6)}</span>
                </div>

                {/* Percentage Preset Buttons */}
                <div className="grid grid-cols-6 gap-1.5">
                  {[0, 10, 25, 50, 75, 100].map((val) => (
                    <button
                      key={val}
                      onClick={() => handleUpdateRollout(selectedFlag, val)}
                      className={`py-1.5 rounded-lg text-xs font-medium border transition ${
                        selectedSetting.rollout_percentage === val
                          ? 'bg-indigo-600 text-white border-indigo-500 shadow-sm'
                          : 'bg-slate-800/80 text-slate-400 border-slate-700/60 hover:bg-slate-800 hover:text-slate-200'
                      }`}
                    >
                      {val}%
                    </button>
                  ))}
                </div>

                {/* Slider */}
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="5"
                  value={selectedSetting.rollout_percentage}
                  onChange={(e) => handleUpdateRollout(selectedFlag, parseInt(e.target.value))}
                  className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
                />
              </div>

              {/* Targeting Rules */}
              <div className="space-y-3 border-t border-slate-800 pt-5">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                    <Layers className="w-3.5 h-3.5 text-indigo-400" />
                    Targeting Rules ({selectedSetting.rules?.length || 0})
                  </div>
                  <button
                    onClick={() => setShowRuleModal(true)}
                    className="text-xs font-medium text-indigo-400 hover:text-indigo-300"
                  >
                    + Add Rule
                  </button>
                </div>

                {selectedSetting.rules?.length === 0 ? (
                  <p className="text-xs text-slate-500 italic bg-slate-800/30 p-3 rounded-lg border border-slate-800/60">
                    No custom targeting rules. All evaluations use percentage rollout.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {selectedSetting.rules.map((rule, idx) => (
                      <div
                        key={rule.id}
                        className="p-3 bg-slate-800/50 rounded-lg border border-slate-800 flex items-center justify-between text-xs"
                      >
                        <div className="space-y-0.5">
                          <span className="font-mono text-indigo-300">{rule.attribute}</span>{' '}
                          <span className="text-slate-400">{rule.operator}</span>{' '}
                          <span className="font-semibold text-slate-200">[{rule.values.join(', ')}]</span>
                          <div className="text-[11px] text-emerald-400">Variant: {rule.variant}</div>
                        </div>
                        <button
                          onClick={() => handleRemoveRule(idx)}
                          className="p-1 text-slate-500 hover:text-rose-400 transition"
                          title="Remove rule"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Audit History */}
              <div className="space-y-3 border-t border-slate-800 pt-5">
                <div className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                  <History className="w-3.5 h-3.5 text-indigo-400" />
                  Audit History
                </div>
                {loadingLogs ? (
                  <div className="p-3 text-center text-xs text-slate-500">Loading audit history...</div>
                ) : auditLogs.length === 0 ? (
                  <div className="p-3 text-center text-xs text-slate-500 bg-slate-800/20 rounded-lg">No audit events</div>
                ) : (
                  <div className="max-h-48 overflow-y-auto space-y-2 pr-1">
                    {auditLogs.map((log) => (
                      <div key={log.id} className="p-2.5 bg-slate-800/40 rounded-lg text-xs border border-slate-800/60">
                        <div className="flex items-center justify-between text-slate-400 text-[11px]">
                          <span className="font-medium text-slate-200 capitalize">{log.action.replace('_', ' ')}</span>
                          <span>{new Date(log.created_at).toLocaleTimeString()}</span>
                        </div>
                        <div className="text-[11px] text-slate-500 mt-0.5">
                          Actor: {log.actor_email || 'System'}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="h-full min-h-[300px] border border-dashed border-slate-800 rounded-2xl flex items-center justify-center p-8 text-center text-slate-500 text-sm">
              Select a feature flag to configure rollouts and targeting rules.
            </div>
          )}
        </div>
      </div>

      {/* Create Flag Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md p-6 shadow-2xl space-y-5 animate-in fade-in zoom-in-95 duration-150">
            <div>
              <h2 className="text-lg font-bold text-slate-100">Create Feature Flag</h2>
              <p className="text-xs text-slate-400 mt-0.5">Define a new runtime toggle in {currentProject?.name}</p>
            </div>

            {formError && (
              <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-lg text-xs text-rose-400">
                {formError}
              </div>
            )}

            <form onSubmit={handleCreateFlag} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">Flag Key *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. new_checkout_v2"
                  value={newKey}
                  onChange={(e) => setNewKey(e.target.value.toLowerCase().replace(/\s+/g, '_'))}
                  className="w-full px-3.5 py-2.5 bg-slate-800/80 border border-slate-700/80 rounded-lg text-sm font-mono text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">Display Name *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. New Checkout V2"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-slate-800/80 border border-slate-700/80 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">Description (optional)</label>
                <textarea
                  rows="2"
                  placeholder="What capability does this flag toggle?"
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  className="w-full px-3.5 py-2 bg-slate-800/80 border border-slate-700/80 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
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
                  {submitting ? 'Creating...' : 'Create Flag'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add Targeting Rule Modal */}
      {showRuleModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md p-6 shadow-2xl space-y-5 animate-in fade-in zoom-in-95 duration-150">
            <div>
              <h2 className="text-lg font-bold text-slate-100">Add Targeting Rule</h2>
              <p className="text-xs text-slate-400 mt-0.5">Route users to specific variants based on user attributes</p>
            </div>

            <form onSubmit={handleAddRule} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">User Attribute</label>
                <select
                  value={ruleAttr}
                  onChange={(e) => setRuleAttr(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-slate-800/80 border border-slate-700/80 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-indigo-500"
                >
                  <option value="user_id">user_id</option>
                  <option value="email">email</option>
                  <option value="role">role</option>
                  <option value="country">country</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">Operator</label>
                <select
                  value={ruleOp}
                  onChange={(e) => setRuleOp(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-slate-800/80 border border-slate-700/80 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-indigo-500"
                >
                  <option value="equals">equals</option>
                  <option value="in">in (comma-separated)</option>
                  <option value="contains">contains</option>
                  <option value="regex">regex</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">Values (comma-separated)</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. user_101, user_102, beta-tester"
                  value={ruleVals}
                  onChange={(e) => setRuleVals(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-slate-800/80 border border-slate-700/80 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">Variant Assigned</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. on or beta_variant"
                  value={ruleVariant}
                  onChange={(e) => setRuleVariant(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-slate-800/80 border border-slate-700/80 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-3">
                <button
                  type="button"
                  onClick={() => setShowRuleModal(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-sm transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium transition"
                >
                  Save Rule
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
