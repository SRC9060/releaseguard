/**
 * ReleaseGuard API Service Layer
 * Centralizes all HTTP communication with the backend.
 * Supports JWT authentication and multi-tenant scoping.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
const TOKEN_KEY = 'releaseguard_auth_token';

class ApiError extends Error {
  constructor(message, status, data = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

export function getAuthToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setAuthToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

export function clearAuthToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function request(endpoint, options = {}) {
  const url = `${BASE_URL}${endpoint}`;
  const token = getAuthToken();

  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const config = {
    ...options,
    headers,
  };

  try {
    const response = await fetch(url, config);

    if (!response.ok) {
      let errorData = null;
      try {
        errorData = await response.json();
      } catch {
        // Non-JSON response
      }

      if (response.status === 401 && token) {
        clearAuthToken();
        window.dispatchEvent(new CustomEvent('releaseguard:auth_expired'));
      }

      let message;
      if (typeof errorData?.detail === 'string') {
        message = errorData.detail;
      } else if (Array.isArray(errorData?.detail)) {
        message = errorData.detail.map(e => e.msg || e.message || JSON.stringify(e)).join(', ');
      } else if (errorData?.detail) {
        message = JSON.stringify(errorData.detail);
      } else {
        message = `API request failed with status ${response.status}`;
      }

      throw new ApiError(message, response.status, errorData);
    }

    if (response.status === 204) {
      return null;
    }

    return await response.json();
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(
      `Unable to connect to ReleaseGuard backend at ${BASE_URL}. Ensure the service is running.`,
      0,
      { originalError: error.message }
    );
  }
}

export const api = {
  // Health
  checkHealth: () => request('/health'),

  // Auth
  login: (email, password) =>
    request('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  register: (email, password, tenant_name = null) =>
    request('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, tenant_name }),
    }),

  getMe: () => request('/api/v1/auth/me'),

  // Tenants
  getTenants: () => request('/api/v1/tenants'),
  getTenant: (tenantId) => request(`/api/v1/tenants/${tenantId}`),
  createTenant: (name) =>
    request('/api/v1/tenants', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  updateTenant: (tenantId, name) =>
    request(`/api/v1/tenants/${tenantId}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    }),
  getTenantMembers: (tenantId) => request(`/api/v1/tenants/${tenantId}/members`),
  updateMemberRole: (tenantId, userId, role) =>
    request(`/api/v1/tenants/${tenantId}/members/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify({ role }),
    }),
  removeMember: (tenantId, userId) =>
    request(`/api/v1/tenants/${tenantId}/members/${userId}`, {
      method: 'DELETE',
    }),
  createInvite: (tenantId, email, role = 'member') =>
    request(`/api/v1/tenants/${tenantId}/invites`, {
      method: 'POST',
      body: JSON.stringify({ email, role }),
    }),

  // Tenant-Scoped Projects
  getTenantProjects: (tenantId) => request(`/api/v1/tenants/${tenantId}/projects`),
  getTenantProject: (tenantId, projectId) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}`),
  getProjectKey: (tenantId, projectId) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}/key`),
  createTenantProject: (tenantId, name) =>
    request(`/api/v1/tenants/${tenantId}/projects`, {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  updateTenantProject: (tenantId, projectId, name) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    }),
  sendProjectTestEvent: (tenantId, projectId) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}/test-event`, {
      method: 'POST',
    }),
  getProjectTestEvent: (tenantId, projectId, eventId) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}/test-event/${eventId}`),

  // Tenant-Scoped Issues
  getTenantIssues: (tenantId, projectId, status = null) => {
    const query = status ? `?status=${encodeURIComponent(status)}` : '';
    return request(`/api/v1/tenants/${tenantId}/projects/${projectId}/issues${query}`);
  },

  getTenantIssue: (tenantId, projectId, issueId) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}/issues/${issueId}`),

  resolveTenantIssue: (tenantId, projectId, issueId) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}/issues/${issueId}/resolve`, {
      method: 'POST',
    }),

  muteTenantIssue: (tenantId, projectId, issueId) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}/issues/${issueId}/mute`, {
      method: 'POST',
    }),

  unresolveTenantIssue: (tenantId, projectId, issueId) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}/issues/${issueId}/unresolve`, {
      method: 'POST',
    }),

  // Tenant-Scoped Event Timeline
  getTenantIssueEvents: (tenantId, projectId, issueId, limit = 50, offset = 0) =>
    request(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/issues/${issueId}/events?limit=${limit}&offset=${offset}`
    ),

  // Tenant-Scoped Time Series
  getTenantIssueTimeseries: (tenantId, projectId, issueId, range = '24h') =>
    request(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/metrics/issues/${issueId}/timeseries?range=${encodeURIComponent(range)}`
    ),

  getTenantProjectTimeseries: (tenantId, projectId, range = '24h') =>
    request(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/metrics/timeseries?range=${encodeURIComponent(range)}`
    ),

  // Issue Releases Correlation
  getIssueReleases: (tenantId, projectId, issueId) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}/issues/${issueId}/releases`),

  // Releases
  getReleases: (tenantId, projectId, environment = null) => {
    const query = environment ? `?environment=${encodeURIComponent(environment)}` : '';
    return request(`/api/v1/tenants/${tenantId}/projects/${projectId}/releases${query}`);
  },
  createRelease: (tenantId, projectId, releaseData) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}/releases`, {
      method: 'POST',
      body: JSON.stringify(releaseData),
    }),
  getRelease: (tenantId, projectId, releaseId) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}/releases/${releaseId}`),

  // Feature Flags
  getEnvironments: (tenantId, projectId) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}/environments`),
  createEnvironment: (tenantId, projectId, envData) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}/environments`, {
      method: 'POST',
      body: JSON.stringify(envData),
    }),
  getFeatureFlags: (tenantId, projectId, includeArchived = false) =>
    request(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/flags?include_archived=${includeArchived}`
    ),
  getFeatureFlag: (tenantId, projectId, flagId) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}/flags/${flagId}`),
  createFeatureFlag: (tenantId, projectId, flagData) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}/flags`, {
      method: 'POST',
      body: JSON.stringify(flagData),
    }),
  updateFeatureFlag: (tenantId, projectId, flagId, flagData) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}/flags/${flagId}`, {
      method: 'PUT',
      body: JSON.stringify(flagData),
    }),
  archiveFeatureFlag: (tenantId, projectId, flagId) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}/flags/${flagId}`, {
      method: 'DELETE',
    }),
  updateFlagSetting: (tenantId, projectId, flagId, environmentId, settingData) =>
    request(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/flags/${flagId}/environments/${environmentId}/setting`,
      {
        method: 'PUT',
        body: JSON.stringify(settingData),
      }
    ),
  updateFlagRollout: (tenantId, projectId, flagId, environmentId, rolloutData) =>
    request(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/flags/${flagId}/environments/${environmentId}/rollout`,
      {
        method: 'PUT',
        body: JSON.stringify(rolloutData),
      }
    ),
  setFlagRules: (tenantId, projectId, flagId, environmentId, rules) =>
    request(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/flags/${flagId}/environments/${environmentId}/rules`,
      {
        method: 'PUT',
        body: JSON.stringify(rules),
      }
    ),
  killFlag: (tenantId, projectId, flagId, environmentId) =>
    request(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/flags/${flagId}/environments/${environmentId}/kill`,
      {
        method: 'POST',
      }
    ),
  getFlagAuditLogs: (tenantId, projectId, flagId) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}/flags/${flagId}/audit-logs`),
  getConfigDocument: (projectIdentifier, environmentKey, userId = null) => {
    const query = userId ? `?user_id=${encodeURIComponent(userId)}` : '';
    return request(`/api/v1/config/${projectIdentifier}/${environmentKey}${query}`);
  },

  // Phase 9: Incidents & Mitigation
  getIncidents: (tenantId, projectId, filters = {}) => {
    const params = new URLSearchParams();
    if (filters.status) params.append('status', filters.status);
    if (filters.severity) params.append('severity', filters.severity);
    if (filters.environment) params.append('environment', filters.environment);
    const qs = params.toString() ? `?${params.toString()}` : '';
    return request(`/api/v1/tenants/${tenantId}/projects/${projectId}/incidents${qs}`);
  },
  getIncident: (tenantId, projectId, incidentId) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}/incidents/${incidentId}`),
  createIncident: (tenantId, projectId, incidentData) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}/incidents`, {
      method: 'POST',
      body: JSON.stringify(incidentData),
    }),
  updateIncident: (tenantId, projectId, incidentId, updateData) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}/incidents/${incidentId}`, {
      method: 'PATCH',
      body: JSON.stringify(updateData),
    }),
  getIncidentTimeline: (tenantId, projectId, incidentId) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}/incidents/${incidentId}/timeline`),
  addIncidentTimelineNote: (tenantId, projectId, incidentId, noteData) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}/incidents/${incidentId}/timeline`, {
      method: 'POST',
      body: JSON.stringify(noteData),
    }),
  approveMitigation: (tenantId, projectId, incidentId, mitigationId) =>
    request(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/incidents/${incidentId}/mitigations/${mitigationId}/approve`,
      {
        method: 'POST',
      }
    ),
  detectSpike: (tenantId, projectId, issueId, environment = 'production', autoCreate = true) =>
    request(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/incidents/detect-spike?issue_id=${issueId}&environment=${encodeURIComponent(
        environment
      )}&auto_create_incident=${autoCreate}`,
      {
        method: 'POST',
      }
    ),

  // Legacy fallback routes (for unauthenticated prototype tests)
  getProjects: () => request('/api/v1/projects'),
  getProject: (projectId) => request(`/api/v1/projects/${projectId}`),
  createProject: (name) =>
    request('/api/v1/projects', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  getIssues: (projectId, status = null) => {
    const query = status ? `?status=${encodeURIComponent(status)}` : '';
    return request(`/api/v1/projects/${projectId}/issues${query}`);
  },
  getIssue: (projectId, issueId) => request(`/api/v1/projects/${projectId}/issues/${issueId}`),
  resolveIssue: (projectId, issueId) =>
    request(`/api/v1/projects/${projectId}/issues/${issueId}/resolve`, { method: 'POST' }),
  muteIssue: (projectId, issueId) =>
    request(`/api/v1/projects/${projectId}/issues/${issueId}/mute`, { method: 'POST' }),
  unresolveIssue: (projectId, issueId) =>
    request(`/api/v1/projects/${projectId}/issues/${issueId}/unresolve`, { method: 'POST' }),
  getIssueEvents: (projectId, issueId, limit = 50, offset = 0) =>
    request(
      `/api/v1/projects/${projectId}/issues/${issueId}/events?limit=${limit}&offset=${offset}`
    ),
  getIssueTimeseries: (projectId, issueId, range = '24h') =>
    request(
      `/api/v1/projects/${projectId}/metrics/issues/${issueId}/timeseries?range=${encodeURIComponent(range)}`
    ),
  getProjectTimeseries: (projectId, range = '24h') =>
    request(
      `/api/v1/projects/${projectId}/metrics/timeseries?range=${encodeURIComponent(range)}`
    ),

  // Error Ingestion (Simulation / Test trigger)
  ingestEvent: (projectId, eventData, apiKey = null) => {
    const headers = {};
    if (apiKey) {
      headers['X-ReleaseGuard-Key'] = apiKey;
    }
    return request(`/api/v1/projects/${projectId}/events`, {
      method: 'POST',
      headers,
      body: JSON.stringify(eventData),
    });
  },
};

export { BASE_URL, ApiError };
export default api;
