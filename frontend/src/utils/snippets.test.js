import test from 'node:test';
import assert from 'node:assert/strict';
import {
  generatePythonEnvSnippet,
  generatePythonInitSnippet,
  PYTHON_INSTALL_SNIPPET,
  PYTHON_CAPTURE_SNIPPET,
} from './snippets.js';
import {
  resolveApiBaseUrl,
  PRODUCTION_API_URL,
  LOCAL_API_URL,
} from '../services/api.js';

const VERCEL_FRONTEND_URL = 'https://releaseguard-two.vercel.app';
const EXPECTED_PROD_BACKEND_URL = 'https://releaseguard-api-0jbc.onrender.com';

test('resolveApiBaseUrl: correctly returns production backend in production environment', () => {
  const prodUrl = resolveApiBaseUrl({ PROD: true });
  assert.equal(prodUrl, EXPECTED_PROD_BACKEND_URL);
  assert.notEqual(prodUrl, VERCEL_FRONTEND_URL, 'Must NOT use Vercel frontend URL as API base URL');
});

test('resolveApiBaseUrl: correctly returns local development backend by default', () => {
  const localUrl = resolveApiBaseUrl({ PROD: false, NODE_ENV: 'development' });
  assert.equal(localUrl, LOCAL_API_URL);
  assert.notEqual(localUrl, VERCEL_FRONTEND_URL, 'Must NOT use Vercel frontend URL as API base URL');
});

test('resolveApiBaseUrl: respects explicit VITE_API_BASE_URL environment variable', () => {
  const customUrl = resolveApiBaseUrl({ VITE_API_BASE_URL: 'https://custom-backend.internal' });
  assert.equal(customUrl, 'https://custom-backend.internal');
});

test('generatePythonEnvSnippet: verifies production snippet uses backend endpoint and NOT frontend Vercel URL', () => {
  const snippet = generatePythonEnvSnippet({
    apiKey: null,
    endpoint: EXPECTED_PROD_BACKEND_URL,
    environment: 'production',
  });

  // Verify expected production snippet line
  assert.ok(
    snippet.includes(`RELEASEGUARD_ENDPOINT="${EXPECTED_PROD_BACKEND_URL}"`),
    `Snippet must contain production backend URL. Got:\n${snippet}`
  );

  // Critical regression test: ensure frontend Vercel URL is never used
  assert.ok(
    !snippet.includes(VERCEL_FRONTEND_URL),
    `Regression failure: Onboarding snippet must NOT use Vercel frontend URL (${VERCEL_FRONTEND_URL})`
  );

  // Verify API key placeholder is masked and safe
  assert.ok(
    snippet.includes('RELEASEGUARD_API_KEY="rg_live_••••••••••••"'),
    'Snippet must mask API key by default'
  );
  assert.ok(
    snippet.includes('RELEASEGUARD_ENVIRONMENT="production"'),
    'Snippet must set production environment'
  );
});

test('generatePythonEnvSnippet: works seamlessly with local development backend URL', () => {
  const snippet = generatePythonEnvSnippet({
    apiKey: 'rg_live_testkey123',
    endpoint: 'http://127.0.0.1:8000',
    environment: 'development',
  });

  assert.ok(
    snippet.includes('RELEASEGUARD_ENDPOINT="http://127.0.0.1:8000"'),
    'Snippet must contain local backend URL'
  );
  assert.ok(
    !snippet.includes(VERCEL_FRONTEND_URL),
    'Snippet must not contain Vercel frontend URL'
  );
  assert.ok(
    snippet.includes('RELEASEGUARD_API_KEY="rg_live_testkey123"'),
    'Snippet should include provided key'
  );
});

test('generatePythonInitSnippet: verifies python client initialization uses backend endpoint', () => {
  const snippet = generatePythonInitSnippet({
    projectId: 12,
    endpoint: EXPECTED_PROD_BACKEND_URL,
    release: 'v1.0.0',
    environment: 'production',
  });

  // Verify base_url fallback uses backend endpoint
  assert.ok(
    snippet.includes(`base_url=os.environ.get("RELEASEGUARD_ENDPOINT", "${EXPECTED_PROD_BACKEND_URL}")`),
    `Init snippet must default to backend endpoint. Got:\n${snippet}`
  );

  // Regression check: ensure frontend Vercel URL is never in init snippet
  assert.ok(
    !snippet.includes(VERCEL_FRONTEND_URL),
    `Init snippet must NOT contain Vercel frontend URL (${VERCEL_FRONTEND_URL})`
  );

  assert.ok(snippet.includes('project_id=12'), 'Init snippet must include project_id');
});

test('static snippets: verify install and capture snippets are well-formed', () => {
  assert.equal(PYTHON_INSTALL_SNIPPET, 'pip install releaseguard-sdk');
  assert.ok(PYTHON_CAPTURE_SNIPPET.includes('releaseguard_sdk.capture_exception()'));
});
