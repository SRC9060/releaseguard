/**
 * ReleaseGuard API Service Layer
 * Centralizes all HTTP communication with the backend.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

class ApiError extends Error {
  constructor(message, status, data = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

async function request(endpoint, options = {}) {
  const url = `${BASE_URL}${endpoint}`;
  const config = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  };

  try {
    const response = await fetch(url, config);

    if (!response.ok) {
      let errorData = null;
      try {
        errorData = await response.json();
      } catch {
        // Response was not JSON
      }
      const message = errorData?.detail || `API request failed with status ${response.status}`;
      throw new ApiError(message, response.status, errorData);
    }

    return await response.json();
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    // Network or connection error
    throw new ApiError(
      `Unable to connect to ReleaseGuard backend at ${BASE_URL}. Ensure the backend service is running.`,
      0,
      { originalError: error.message }
    );
  }
}

export const api = {
  // Health
  checkHealth: () => request('/health'),

  // Projects
  getProjects: () => request('/api/v1/projects'),
  getProject: (projectId) => request(`/api/v1/projects/${projectId}`),
  createProject: (name) =>
    request('/api/v1/projects', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),

  // Issues
  getIssues: (projectId, status = null) => {
    const query = status ? `?status=${encodeURIComponent(status)}` : '';
    return request(`/api/v1/projects/${projectId}/issues${query}`);
  },

  getIssue: async (projectId, issueId) => {
    try {
      return await request(`/api/v1/projects/${projectId}/issues/${issueId}`);
    } catch (err) {
      // Fallback: If individual issue route returns 404/not supported, find in list
      const issues = await request(`/api/v1/projects/${projectId}/issues`);
      const matched = issues.find((i) => i.id === Number(issueId));
      if (!matched) {
        throw new ApiError(`Issue #${issueId} not found in this project.`, 404);
      }
      return matched;
    }
  },

  // Issue Status Actions (Phase 6)
  resolveIssue: (projectId, issueId) =>
    request(`/api/v1/projects/${projectId}/issues/${issueId}/resolve`, {
      method: 'POST',
    }),

  muteIssue: (projectId, issueId) =>
    request(`/api/v1/projects/${projectId}/issues/${issueId}/mute`, {
      method: 'POST',
    }),

  unresolveIssue: (projectId, issueId) =>
    request(`/api/v1/projects/${projectId}/issues/${issueId}/unresolve`, {
      method: 'POST',
    }),

  // Event Timeline & Details (Phase 6)
  getIssueEvents: (projectId, issueId, limit = 50, offset = 0) =>
    request(
      `/api/v1/projects/${projectId}/issues/${issueId}/events?limit=${limit}&offset=${offset}`
    ),

  // Time Series Metrics (Phase 6)
  getIssueTimeseries: (projectId, issueId, range = '24h') =>
    request(
      `/api/v1/projects/${projectId}/metrics/issues/${issueId}/timeseries?range=${encodeURIComponent(range)}`
    ),

  getProjectTimeseries: (projectId, range = '24h') =>
    request(
      `/api/v1/projects/${projectId}/metrics/timeseries?range=${encodeURIComponent(range)}`
    ),

  // Error Ingestion (Simulation / Test trigger)
  ingestEvent: (projectId, eventData) =>
    request(`/api/v1/projects/${projectId}/events`, {
      method: 'POST',
      body: JSON.stringify(eventData),
    }),

  // Bulk Ingestion
  ingestEventsBulk: (projectId, events) =>
    request(`/api/v1/projects/${projectId}/events/bulk`, {
      method: 'POST',
      body: JSON.stringify({ events }),
    }),
};

export { ApiError };
export default api;
