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
      const message = errorData?.detail || `API request failed with status ${response.status}`;
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
  getTenantMembers: (tenantId) => request(`/api/v1/tenants/${tenantId}/members`),

  // Tenant-Scoped Projects
  getTenantProjects: (tenantId) => request(`/api/v1/tenants/${tenantId}/projects`),
  getTenantProject: (tenantId, projectId) =>
    request(`/api/v1/tenants/${tenantId}/projects/${projectId}`),
  createTenantProject: (tenantId, name) =>
    request(`/api/v1/tenants/${tenantId}/projects`, {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),

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

export { ApiError };
export default api;
