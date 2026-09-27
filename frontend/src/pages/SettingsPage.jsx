import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useProject } from '../context/ProjectContext';
import api from '../services/api';
import {
  Settings,
  Building,
  Users,
  Shield,
  FolderGit2,
  Terminal,
  AlertCircle,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Plus,
  Trash2,
  ShieldAlert,
  ShieldCheck,
  UserCheck,
  Key,
  ExternalLink,
  Lock,
} from 'lucide-react';

export default function SettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { user, selectedTenant, refreshUserTenants } = useAuth();
  const { projects } = useProject();

  const activeTab = searchParams.get('tab') || 'workspace';
  const setActiveTab = (tab) => {
    setSearchParams({ tab });
  };

  // Workspace Tab State
  const [tenantName, setTenantName] = useState(selectedTenant?.name || '');
  const [savingTenant, setSavingTenant] = useState(false);
  const [tenantSuccess, setTenantSuccess] = useState(false);
  const [tenantError, setTenantError] = useState(null);

  // Team Tab State
  const [members, setMembers] = useState([]);
  const [loadingMembers, setLoadingMembers] = useState(false);
  const [teamError, setTeamError] = useState(null);
  const [teamSuccess, setTeamSuccess] = useState(null);

  // Invite Modal
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('member');
  const [inviting, setInviting] = useState(false);
  const [inviteResult, setInviteResult] = useState(null);

  // Remove Member Confirm Modal
  const [memberToRemove, setMemberToRemove] = useState(null);
  const [removing, setRemoving] = useState(false);

  // Role Change
  const [updatingRoleId, setUpdatingRoleId] = useState(null);

  const currentUserRole = selectedTenant?.role || 'member';
  const isOwner = currentUserRole === 'owner';
  const isAdmin = currentUserRole === 'admin';
  const canManageTeam = isOwner || isAdmin;

  useEffect(() => {
    if (selectedTenant?.name) {
      setTenantName(selectedTenant.name);
    }
  }, [selectedTenant?.name]);

  const fetchMembers = async () => {
    if (!selectedTenant) return;
    setLoadingMembers(true);
    setTeamError(null);
    try {
      const data = await api.getTenantMembers(selectedTenant.id);
      setMembers(data);
    } catch (err) {
      setTeamError(err.message || 'Failed to load team members');
    } finally {
      setLoadingMembers(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'team') {
      fetchMembers();
    }
  }, [activeTab, selectedTenant?.id]);

  const handleUpdateWorkspace = async (e) => {
    e.preventDefault();
    if (!tenantName.trim() || !canManageTeam || !selectedTenant) return;
    setSavingTenant(true);
    setTenantError(null);
    setTenantSuccess(false);
    try {
      await api.updateTenant(selectedTenant.id, tenantName.trim());
      setTenantSuccess(true);
      if (refreshUserTenants) {
        await refreshUserTenants();
      }
      setTimeout(() => setTenantSuccess(false), 3000);
    } catch (err) {
      setTenantError(err.message || 'Failed to update workspace name');
    } finally {
      setSavingTenant(false);
    }
  };

  const handleSendInvite = async (e) => {
    e.preventDefault();
    if (!inviteEmail.trim() || !selectedTenant) return;
    setInviting(true);
    setTeamError(null);
    try {
      const res = await api.createInvite(selectedTenant.id, inviteEmail.trim(), inviteRole);
      setInviteResult(res);
      setInviteEmail('');
      fetchMembers();
    } catch (err) {
      setTeamError(err.message || 'Failed to send invite');
    } finally {
      setInviting(false);
    }
  };

  const handleChangeRole = async (targetMember, newRole) => {
    if (!selectedTenant) return;
    setUpdatingRoleId(targetMember.id);
    setTeamError(null);
    setTeamSuccess(null);
    try {
      await api.updateMemberRole(selectedTenant.id, targetMember.user_id, newRole);
      setTeamSuccess(`Updated role for ${targetMember.email || 'member'} to ${newRole}`);
      fetchMembers();
      setTimeout(() => setTeamSuccess(null), 3000);
    } catch (err) {
      setTeamError(err.message || 'Failed to update member role');
    } finally {
      setUpdatingRoleId(null);
    }
  };

  const handleRemoveMember = async () => {
    if (!memberToRemove || !selectedTenant) return;
    setRemoving(true);
    setTeamError(null);
    try {
      await api.removeMember(selectedTenant.id, memberToRemove.user_id);
      setMemberToRemove(null);
      fetchMembers();
    } catch (err) {
      setTeamError(err.message || 'Failed to remove member');
    } finally {
      setRemoving(false);
    }
  };

  const getRoleBadge = (role) => {
    switch (role?.toLowerCase()) {
      case 'owner':
        return 'bg-purple-500/10 text-purple-400 border-purple-500/20';
      case 'admin':
        return 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20';
      default:
        return 'bg-slate-500/10 text-slate-400 border-slate-500/20';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-100 tracking-tight flex items-center gap-2.5">
          <Settings className="w-6 h-6 text-indigo-400" />
          Settings
        </h1>
        <p className="text-sm text-slate-400 mt-1">
          Manage workspace settings, team members & permissions, security policies, and integrations.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-2 overflow-x-auto border-b border-slate-800 pb-px">
        {[
          { key: 'workspace', label: 'Workspace', icon: Building },
          { key: 'team', label: 'Team & RBAC', icon: Users },
          { key: 'security', label: 'Security', icon: Shield },
          { key: 'projects', label: 'Projects', icon: FolderGit2 },
          { key: 'integrations', label: 'Integrations', icon: Terminal },
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

      {/* SECTION A: WORKSPACE */}
      {activeTab === 'workspace' && (
        <div className="space-y-6 max-w-3xl animate-in fade-in duration-100">
          <div className="p-6 bg-slate-900/60 border border-slate-800 rounded-2xl space-y-6">
            <div>
              <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
                <Building className="w-4 h-4 text-indigo-400" />
                Workspace Information
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                Details and identity for your current ReleaseGuard organization.
              </p>
            </div>

            {tenantSuccess && (
              <div className="p-3 bg-emerald-950/30 border border-emerald-500/40 rounded-xl text-xs text-emerald-300 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                <span>Workspace name updated successfully.</span>
              </div>
            )}

            {tenantError && (
              <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl text-xs text-rose-400 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{tenantError}</span>
              </div>
            )}

            <form onSubmit={handleUpdateWorkspace} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Workspace Name
                </label>
                <input
                  type="text"
                  required
                  disabled={!canManageTeam}
                  value={tenantName}
                  onChange={(e) => setTenantName(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 disabled:opacity-60 transition"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1">
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1.5">
                    Workspace Slug
                  </label>
                  <input
                    type="text"
                    disabled
                    value={selectedTenant?.slug || ''}
                    className="w-full px-3.5 py-2.5 bg-slate-950/60 border border-slate-800/80 rounded-xl text-xs font-mono text-slate-400 cursor-not-allowed"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1.5">
                    Your Assigned Role
                  </label>
                  <div className="px-3.5 py-2.5 bg-slate-950/60 border border-slate-800/80 rounded-xl text-xs font-semibold flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${getRoleBadge(currentUserRole)}`}>
                      {currentUserRole}
                    </span>
                    <span className="text-slate-400">({user?.email})</span>
                  </div>
                </div>
              </div>

              {canManageTeam ? (
                <div className="pt-3 flex justify-end">
                  <button
                    type="submit"
                    disabled={savingTenant || !tenantName.trim() || tenantName === selectedTenant?.name}
                    className="flex items-center gap-2 px-5 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl text-xs font-semibold transition shadow-lg shadow-indigo-600/20"
                  >
                    {savingTenant && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                    <span>{savingTenant ? 'Saving...' : 'Update Workspace'}</span>
                  </button>
                </div>
              ) : (
                <p className="text-[11px] text-slate-500 italic pt-1">
                  Only Workspace Owners and Admins can update workspace configuration.
                </p>
              )}
            </form>
          </div>
        </div>
      )}

      {/* SECTION B: TEAM & RBAC */}
      {activeTab === 'team' && (
        <div className="space-y-6 animate-in fade-in duration-100">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                <Users className="w-5 h-5 text-indigo-400" />
                Team Members & Access Control
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                Manage user permissions and role assignments across your organization.
              </p>
            </div>

            {canManageTeam && (
              <button
                onClick={() => {
                  setInviteResult(null);
                  setShowInviteModal(true);
                }}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold transition shadow-lg shadow-indigo-600/20"
              >
                <Plus className="w-4 h-4" />
                Invite Member
              </button>
            )}
          </div>

          {teamSuccess && (
            <div className="p-3 bg-emerald-950/30 border border-emerald-500/40 rounded-xl text-xs text-emerald-300 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{teamSuccess}</span>
            </div>
          )}

          {teamError && (
            <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl text-xs text-rose-400 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{teamError}</span>
            </div>
          )}

          {/* Members Table */}
          <div className="bg-slate-900/60 border border-slate-800 rounded-2xl overflow-hidden">
            {loadingMembers ? (
              <div className="flex items-center justify-center p-12">
                <Loader2 className="w-6 h-6 text-indigo-400 animate-spin" />
              </div>
            ) : (
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/70 text-slate-400 border-b border-slate-800 uppercase tracking-wider font-semibold">
                  <tr>
                    <th className="px-5 py-3.5">User</th>
                    <th className="px-5 py-3.5">Role</th>
                    <th className="px-5 py-3.5">Joined Date</th>
                    <th className="px-5 py-3.5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-slate-300">
                  {members.map((m) => {
                    const isCurrentUser = m.user_id === user?.id;
                    const canEditThisMember =
                      canManageTeam && (!isCurrentUser || isOwner) && (isOwner || m.role !== 'owner');

                    return (
                      <tr key={m.id} className="hover:bg-slate-800/30 transition">
                        <td className="px-5 py-4">
                          <div className="flex items-center gap-3">
                            <div className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center font-bold text-xs uppercase text-slate-300">
                              {m.email ? m.email.slice(0, 2).toUpperCase() : 'U'}
                            </div>
                            <div>
                              <div className="font-semibold text-slate-100 flex items-center gap-2">
                                <span>{m.email}</span>
                                {isCurrentUser && (
                                  <span className="text-[10px] font-normal px-1.5 py-0.2 rounded bg-slate-800 text-slate-400">
                                    You
                                  </span>
                                )}
                              </div>
                              <span className="text-[11px] text-slate-500 font-mono">User ID #{m.user_id}</span>
                            </div>
                          </div>
                        </td>

                        <td className="px-5 py-4">
                          {canEditThisMember && isOwner ? (
                            <select
                              value={m.role}
                              disabled={updatingRoleId === m.id}
                              onChange={(e) => handleChangeRole(m, e.target.value)}
                              className="px-2.5 py-1 bg-slate-950 border border-slate-700 rounded-lg text-xs font-medium text-slate-200 focus:outline-none focus:border-indigo-500"
                            >
                              <option value="owner">Owner</option>
                              <option value="admin">Admin</option>
                              <option value="member">Member</option>
                            </select>
                          ) : canEditThisMember && isAdmin && m.role !== 'owner' ? (
                            <select
                              value={m.role}
                              disabled={updatingRoleId === m.id}
                              onChange={(e) => handleChangeRole(m, e.target.value)}
                              className="px-2.5 py-1 bg-slate-950 border border-slate-700 rounded-lg text-xs font-medium text-slate-200 focus:outline-none focus:border-indigo-500"
                            >
                              <option value="admin">Admin</option>
                              <option value="member">Member</option>
                            </select>
                          ) : (
                            <span
                              className={`px-2.5 py-1 rounded text-[11px] font-bold uppercase border ${getRoleBadge(
                                m.role
                              )}`}
                            >
                              {m.role}
                            </span>
                          )}
                        </td>

                        <td className="px-5 py-4 text-slate-400">
                          {new Date(m.created_at).toLocaleDateString()}
                        </td>

                        <td className="px-5 py-4 text-right">
                          {(canManageTeam && !isCurrentUser && (isOwner || m.role !== 'owner')) ||
                          (isCurrentUser && members.length > 1) ? (
                            <button
                              type="button"
                              onClick={() => setMemberToRemove(m)}
                              className="p-1.5 hover:bg-rose-500/10 text-slate-400 hover:text-rose-400 rounded-lg transition"
                              title={isCurrentUser ? 'Leave Workspace' : 'Remove Member'}
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          ) : (
                            <span className="text-[11px] text-slate-600">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          {/* RBAC Info Card */}
          <div className="p-4 bg-slate-900/40 border border-slate-800 rounded-xl space-y-2 text-xs text-slate-400">
            <h4 className="font-semibold text-slate-200 flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-indigo-400" />
              Role Permissions Reference
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-1">
              <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800">
                <strong className="text-purple-400 block mb-1">Owner</strong>
                Full control over workspace settings, billing, project creation, member role assignment, and project deletion. Protected by last-owner invariant.
              </div>
              <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800">
                <strong className="text-indigo-400 block mb-1">Admin</strong>
                Manage projects, invite members, promote/demote regular members, configure feature flags and releases.
              </div>
              <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800">
                <strong className="text-slate-300 block mb-1">Member</strong>
                View projects, inspect error issues, trigger test verification events, and view deployment status.
              </div>
            </div>
          </div>

          {/* Invite Member Modal */}
          {showInviteModal && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
              <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl">
                <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                  <UserCheck className="w-5 h-5 text-indigo-400" />
                  Invite Team Member
                </h2>
                <p className="text-xs text-slate-400 mt-1">
                  Send an invitation to join <span className="font-semibold text-slate-300">{selectedTenant?.name}</span>.
                </p>

                {inviteResult ? (
                  <div className="mt-5 p-4 bg-emerald-950/30 border border-emerald-500/40 rounded-xl space-y-3">
                    <div className="flex items-center gap-2 text-emerald-400 text-sm font-semibold">
                      <CheckCircle2 className="w-4 h-4" />
                      <span>Invitation Generated!</span>
                    </div>
                    <p className="text-xs text-slate-300">
                      Invitation for <strong>{inviteResult.email}</strong> created with role <strong>{inviteResult.role}</strong>.
                    </p>
                    {inviteResult.token && (
                      <div className="p-2.5 bg-slate-950 rounded-lg border border-slate-800 font-mono text-[11px] text-slate-300 break-all select-all">
                        Invite Token: {inviteResult.token}
                      </div>
                    )}
                    <button
                      type="button"
                      onClick={() => setShowInviteModal(false)}
                      className="w-full mt-2 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs font-semibold transition"
                    >
                      Done
                    </button>
                  </div>
                ) : (
                  <form onSubmit={handleSendInvite} className="mt-5 space-y-4">
                    <div>
                      <label className="block text-xs font-medium text-slate-300 mb-1">
                        Email Address <span className="text-rose-400">*</span>
                      </label>
                      <input
                        type="email"
                        required
                        placeholder="colleague@company.com"
                        value={inviteEmail}
                        onChange={(e) => setInviteEmail(e.target.value)}
                        className="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-slate-300 mb-1">
                        Assign Role
                      </label>
                      <select
                        value={inviteRole}
                        onChange={(e) => setInviteRole(e.target.value)}
                        className="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-xs font-medium text-slate-200 focus:outline-none focus:border-indigo-500"
                      >
                        <option value="member">Member</option>
                        <option value="admin">Admin</option>
                        {isOwner && <option value="owner">Owner</option>}
                      </select>
                    </div>

                    <div className="flex items-center justify-end gap-3 pt-3">
                      <button
                        type="button"
                        onClick={() => setShowInviteModal(false)}
                        className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-slate-200"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={inviting || !inviteEmail.trim()}
                        className="flex items-center gap-2 px-5 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl text-xs font-semibold"
                      >
                        {inviting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                        <span>{inviting ? 'Sending...' : 'Send Invitation'}</span>
                      </button>
                    </div>
                  </form>
                )}
              </div>
            </div>
          )}

          {/* Remove Member Confirmation Modal */}
          {memberToRemove && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
              <div className="w-full max-w-sm bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl space-y-4">
                <div className="w-10 h-10 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 flex items-center justify-center mx-auto">
                  <ShieldAlert className="w-5 h-5" />
                </div>
                <div className="text-center">
                  <h3 className="text-base font-bold text-slate-100">
                    {memberToRemove.user_id === user?.id ? 'Leave Workspace?' : 'Remove Team Member?'}
                  </h3>
                  <p className="text-xs text-slate-400 mt-1">
                    Are you sure you want to remove <strong>{memberToRemove.email}</strong> from {selectedTenant?.name}?
                  </p>
                </div>
                <div className="flex items-center justify-center gap-3 pt-2">
                  <button
                    type="button"
                    disabled={removing}
                    onClick={() => setMemberToRemove(null)}
                    className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    disabled={removing}
                    onClick={handleRemoveMember}
                    className="px-4 py-2 rounded-xl text-xs font-semibold bg-rose-600 hover:bg-rose-500 text-white transition shadow-lg shadow-rose-600/20"
                  >
                    {removing ? 'Removing...' : 'Confirm Remove'}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* SECTION C: SECURITY */}
      {activeTab === 'security' && (
        <div className="space-y-6 max-w-3xl animate-in fade-in duration-100">
          <div className="p-6 bg-slate-900/60 border border-slate-800 rounded-2xl space-y-5">
            <div>
              <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
                <Shield className="w-4 h-4 text-indigo-400" />
                Authentication & Security Architecture
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                ReleaseGuard enforces strict tenant isolation, distributed lockout protection, and credential security.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-1.5">
                <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block">Session Protocol</span>
                <div className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                  <Lock className="w-3.5 h-3.5 text-indigo-400" />
                  <span>HMAC-SHA256 JWT</span>
                </div>
                <p className="text-[11px] text-slate-400">Tokens are digitally signed and expire every 24 hours.</p>
              </div>

              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-1.5">
                <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block">Isolation Boundary</span>
                <div className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Tenant & Project Scoped</span>
                </div>
                <p className="text-[11px] text-slate-400">All queries enforce strict multi-tenant authorization barriers.</p>
              </div>
            </div>

            <div className="p-4 bg-slate-950/60 border border-slate-800 rounded-xl space-y-2 text-xs text-slate-300">
              <h4 className="font-semibold text-slate-200 flex items-center gap-2">
                <Key className="w-4 h-4 text-amber-400" />
                API Credentials Policy
              </h4>
              <p className="text-slate-400 leading-relaxed">
                ReleaseGuard generates dedicated ingestion keys per project. Ingestion keys cannot view project dashboards, perform administrative operations, or query issues across other tenants. Never expose project keys in client-side applications.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* SECTION D: PROJECTS */}
      {activeTab === 'projects' && (
        <div className="space-y-6 animate-in fade-in duration-100">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                <FolderGit2 className="w-5 h-5 text-indigo-400" />
                Organization Projects
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                View and manage projects created within {selectedTenant?.name}.
              </p>
            </div>

            <Link
              to="/projects"
              className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold transition"
            >
              <span>Go to Project Management</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </Link>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.map((p) => (
              <div key={p.id} className="p-5 bg-slate-900/60 border border-slate-800 rounded-xl space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-400">
                    #{p.id}
                  </span>
                  <Link
                    to={`/projects/${p.id}`}
                    className="text-xs text-indigo-400 hover:underline inline-flex items-center gap-1 font-medium"
                  >
                    View Project <ExternalLink className="w-3 h-3" />
                  </Link>
                </div>
                <h3 className="text-base font-semibold text-slate-100 truncate">{p.name}</h3>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* SECTION E: INTEGRATIONS */}
      {activeTab === 'integrations' && (
        <div className="space-y-6 max-w-3xl animate-in fade-in duration-100">
          <div className="p-6 bg-slate-900/60 border border-slate-800 rounded-2xl space-y-4">
            <div>
              <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
                <Terminal className="w-4 h-4 text-indigo-400" />
                Platform Integrations & SDKs
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                ReleaseGuard provides native language SDKs designed to capture errors with zero performance impact.
              </p>
            </div>

            <div className="space-y-3">
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg bg-indigo-500/10 text-indigo-400 flex items-center justify-center font-bold text-xs">
                    PY
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-slate-200">Python SDK (releaseguard-sdk)</h4>
                    <p className="text-xs text-slate-400">Async batching, Redis stream ingestion, feature flag evaluation.</p>
                  </div>
                </div>

                <span className="px-2.5 py-1 rounded text-[11px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  Ready & Active
                </span>
              </div>

              <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80 flex items-center justify-between opacity-70">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg bg-slate-800 text-slate-400 flex items-center justify-center font-bold text-xs">
                    JS
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-slate-300">Node.js / TypeScript SDK</h4>
                    <p className="text-xs text-slate-500">Express, Fastify, and NestJS instrumentation.</p>
                  </div>
                </div>

                <span className="px-2.5 py-1 rounded text-[11px] font-semibold bg-slate-800 text-slate-500 border border-slate-700">
                  Coming Soon
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
