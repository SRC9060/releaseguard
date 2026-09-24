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
  getIssues: (projectId) => request(`/api/v1/projects/${projectId}/issues`),
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

  // Error Ingestion (Simulation / Test trigger)
  ingestEvent: (projectId, eventData) =>
    request(`/api/v1/projects/${projectId}/events`, {
      method: 'POST',
      body: JSON.stringify(eventData),
    }),
};

export { ApiError };
export default api;
