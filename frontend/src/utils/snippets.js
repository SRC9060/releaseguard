/**
 * ReleaseGuard SDK & Integration Snippet Generators
 */

/**
 * Generates the environment variables snippet for Python SDK configuration.
 *
 * @param {Object} options
 * @param {string|null} [options.apiKey] - Project API key (unmasked or masked)
 * @param {string} options.endpoint - The backend API base URL
 * @param {string} [options.environment='production'] - Deployment environment
 * @returns {string} Formatted snippet
 */
export function generatePythonEnvSnippet({ apiKey, endpoint, environment = 'production' }) {
  const key = apiKey || 'rg_live_••••••••••••';
  return `# In your production environment (.env / system variables)
RELEASEGUARD_API_KEY="${key}"
RELEASEGUARD_ENDPOINT="${endpoint}"
RELEASEGUARD_ENVIRONMENT="${environment}"`;
}

/**
 * Generates the Python SDK initialization snippet.
 *
 * @param {Object} options
 * @param {string|number} options.projectId - Project ID
 * @param {string} options.endpoint - The backend API base URL
 * @param {string} [options.release='v1.0.0'] - Release tag fallback
 * @param {string} [options.environment='production'] - Environment fallback
 * @returns {string} Formatted snippet
 */
export function generatePythonInitSnippet({
  projectId,
  endpoint,
  release = 'v1.0.0',
  environment = 'production',
}) {
  return `import os
import releaseguard_sdk

# Initialize ReleaseGuard at application startup
releaseguard_sdk.init(
    project_id=${projectId},
    base_url=os.environ.get("RELEASEGUARD_ENDPOINT", "${endpoint}"),
    api_key=os.environ["RELEASEGUARD_API_KEY"],
    release=os.environ.get("RELEASEGUARD_RELEASE", "${release}"),
    environment=os.environ.get("RELEASEGUARD_ENVIRONMENT", "${environment}"),
)`;
}

export const PYTHON_INSTALL_SNIPPET = `pip install releaseguard-sdk`;

export const PYTHON_CAPTURE_SNIPPET = `try:
    # Execute critical business logic
    process_transaction()
except Exception:
    # Captures stack trace, exception type, and metadata asynchronously
    releaseguard_sdk.capture_exception()
    raise`;
