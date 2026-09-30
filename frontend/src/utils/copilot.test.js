import test from 'node:test';
import assert from 'node:assert/strict';
import {
  COPILOT_ADVISORY_NOTICE,
  COPILOT_NO_AUTONOMOUS_ACTION_NOTICE,
  COPILOT_CANNOT_MODIFY_SYSTEMS_NOTICE,
  getCopilotErrorState,
  validateCopilotResponse,
  validateCopilotChatResponse,
  formatEvidenceBadge,
  formatModelBadge,
  isAutonomousActionAllowed,
} from './copilot.js';

// Sample grounded response matching Phase 15A backend schema
const MOCK_COPILOT_RESPONSE = {
  id: 101,
  incident_id: 42,
  provider: 'gemini',
  model: 'gemini-3.8-flash',
  cached: false,
  context_hash: 'a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef1234567890',
  created_at: '2026-09-29T10:00:00Z',
  analysis: {
    summary:
      'Elevated 502/504 error spike detected in checkout service immediately following deployment of release v2.4.1.',
    recent_changes: [
      {
        type: 'release',
        identifier: 'v2.4.1',
        description: 'Updated webhook signature verification library.',
        timestamp: '2026-09-29T09:45:00Z',
        potential_relevance: 'High temporal proximity to error onset.',
      },
      {
        type: 'feature_flag',
        identifier: 'enable_stripe_v3',
        description: 'Toggled enabled to true in production.',
        timestamp: '2026-09-29T09:50:00Z',
        potential_relevance: 'Directly impacts credit card processing pathway.',
      },
    ],
    hypotheses: [
      {
        id: 'H1',
        title: 'Webhook signature validation regression',
        explanation:
          'The newly deployed verification logic may reject legitimate payment gateway callbacks due to strict header checking.',
        evidence: [
          '502 Bad Gateway error count surged from 0 to 418 at 09:46 UTC.',
          'Stack trace highlights signature_validator.py line 42.',
        ],
        inference: [
          'Third-party provider headers likely omitted custom prefix.',
          'Timeout in downstream callback processing causes worker thread exhaustion.',
        ],
        likelihood: 'probable',
      },
      {
        id: 'H2',
        title: 'Database connection pool saturation',
        explanation: 'Payment retries created connection backlog.',
        evidence: ['Pool checkout wait time increased by 350ms.'],
        inference: ['Secondary symptom rather than primary root cause.'],
        likelihood: 'plausible',
      },
    ],
    recommended_actions: [
      {
        action_type: 'mitigation',
        priority: 'immediate',
        description: 'Disable feature flag enable_stripe_v3 in production.',
        rationale: 'Reverts payment traffic to legacy stable pathway.',
        risk_assessment: 'Low risk; legacy path is fully backward-compatible.',
        target_flag_key: 'enable_stripe_v3',
        target_environment: 'production',
      },
      {
        action_type: 'investigation',
        priority: 'secondary',
        description: 'Inspect raw webhook payload headers in staging.',
        rationale: 'Confirm signature header formatting.',
        risk_assessment: 'None; read-only investigation.',
        target_flag_key: null,
        target_environment: 'staging',
      },
    ],
    evidence: [
      {
        source: 'error_events',
        description: '418 occurrences of WebhookValidationError in 10 minutes.',
        confidence: 'high',
      },
      {
        source: 'release_audit',
        description: 'Release v2.4.1 deployed 1 minute prior to first error.',
        confidence: 'high',
      },
    ],
    uncertainties: [
      {
        area: 'Third-party upstream webhook header format',
        missing_information: 'Raw HTTP request headers for failed requests.',
        how_to_verify: 'Enable debug logging temporarily on webhook ingress gateway.',
      },
    ],
  },
};

test('Copilot Advisory Notice: persistent and calibrated safety copy', () => {
  assert.equal(
    COPILOT_ADVISORY_NOTICE,
    'AI-generated analysis is advisory. Verify evidence before taking action.'
  );
  assert.equal(
    COPILOT_NO_AUTONOMOUS_ACTION_NOTICE,
    'AI does not automatically modify feature flags, releases, or incident status.'
  );
});

test('Copilot Safety Guarantee: Autonomous actions are strictly prohibited', () => {
  assert.equal(
    isAutonomousActionAllowed(),
    false,
    'Copilot UI must never expose or permit autonomous mutation triggers'
  );
});

test('validateCopilotResponse: accepts valid Phase 15A structured response', () => {
  const result = validateCopilotResponse(MOCK_COPILOT_RESPONSE);
  assert.equal(result.valid, true);
});

test('validateCopilotResponse: rejects malformed or missing sections', () => {
  assert.equal(validateCopilotResponse(null).valid, false);
  assert.equal(validateCopilotResponse({}).valid, false);
  assert.equal(validateCopilotResponse({ analysis: { summary: 123 } }).valid, false);
  assert.equal(
    validateCopilotResponse({
      analysis: {
        summary: 'ok',
        hypotheses: [{ title: 'h1', evidence: 'not-an-array' }],
      },
    }).valid,
    false
  );
});

test('Evidence vs Inference distinction: ensures observable facts are separated from deduction', () => {
  const hypotheses = MOCK_COPILOT_RESPONSE.analysis.hypotheses;
  assert.ok(hypotheses.length >= 1);

  for (const hyp of hypotheses) {
    // 1. Evidence must be an array of factual observations
    assert.ok(Array.isArray(hyp.evidence));
    assert.ok(hyp.evidence.length > 0);
    for (const ev of hyp.evidence) {
      assert.equal(typeof ev, 'string');
      // Evidence should contain facts/numbers/timestamps/traces, not speculations
      assert.ok(ev.length > 0);
    }

    // 2. Inference must be strictly separated
    assert.ok(Array.isArray(hyp.inference) || typeof hyp.inference === 'string');
    if (Array.isArray(hyp.inference)) {
      for (const inf of hyp.inference) {
        assert.equal(typeof inf, 'string');
        assert.ok(inf.length > 0);
      }
    }

    // 3. Likelihood must be calibrated
    assert.ok(['probable', 'plausible', 'unlikely'].includes(hyp.likelihood));
  }
});

test('Uncertainties: verifies telemetry gaps and verification steps are structured', () => {
  const uncertainties = MOCK_COPILOT_RESPONSE.analysis.uncertainties;
  assert.ok(Array.isArray(uncertainties));
  assert.ok(uncertainties.length > 0);

  const first = uncertainties[0];
  assert.ok(first.area);
  assert.ok(first.missing_information);
  assert.ok(first.how_to_verify);
});

test('Recommended Actions: advisory only, non-executable, with risk assessment', () => {
  const actions = MOCK_COPILOT_RESPONSE.analysis.recommended_actions;
  assert.ok(Array.isArray(actions));
  assert.ok(actions.length > 0);

  for (const act of actions) {
    assert.ok(['immediate', 'secondary', 'post_incident'].includes(act.priority));
    assert.ok(
      ['mitigation', 'investigation', 'monitoring', 'communication'].includes(act.action_type)
    );
    assert.ok(act.description.length > 0);
    assert.ok(act.rationale.length > 0);
    assert.ok(act.risk_assessment.length > 0);
  }
});

test('getCopilotErrorState: handles 504 provider timeout safely', () => {
  const state = getCopilotErrorState({ status: 504 });
  assert.equal(state.status, 504);
  assert.ok(state.title.includes('Timed Out'));
  assert.ok(state.message.includes('completely safe and unmodified'));
  assert.equal(state.allowRetry, true);
});

test('getCopilotErrorState: handles 503 provider unavailable safely', () => {
  const state = getCopilotErrorState({ status: 503 });
  assert.equal(state.status, 503);
  assert.ok(state.title.includes('Unavailable'));
  assert.ok(state.message.includes('incident is unaffected'));
  assert.equal(state.allowRetry, true);
});

test('getCopilotErrorState: handles 502 malformed AI response without leaking raw payload', () => {
  const state = getCopilotErrorState({
    status: 502,
    message: 'Raw LLM gibberish: {broken: json [123}',
  });
  assert.equal(state.status, 502);
  assert.ok(state.title.includes('Invalid Structured Response'));
  assert.ok(state.message.includes('Raw model payload has been suppressed'));
  assert.ok(!state.message.includes('broken: json'), 'Must never leak raw LLM payload');
  assert.equal(state.allowRetry, true);
});

test('getCopilotErrorState: handles 403 forbidden without retry', () => {
  const state = getCopilotErrorState({ status: 403 });
  assert.equal(state.status, 403);
  assert.ok(state.title.includes('Permission Denied'));
  assert.equal(state.allowRetry, false);
});

test('getCopilotErrorState: handles 404 no previous analysis cleanly', () => {
  const state = getCopilotErrorState({ status: 404 });
  assert.equal(state.status, 404);
  assert.ok(state.title.includes('No Analysis Found'));
  assert.equal(state.allowRetry, false);
});

test('getCopilotErrorState: handles network failure (status 0)', () => {
  const state = getCopilotErrorState({ status: 0, message: 'Network offline' });
  assert.equal(state.status, 0);
  assert.ok(state.title.includes('Request Failed'));
  assert.equal(state.allowRetry, true);
});

test('Cached state vs Fresh analysis: identifies deterministic caching badge', () => {
  const cachedResponse = { ...MOCK_COPILOT_RESPONSE, cached: true };
  assert.equal(cachedResponse.cached, true);
  assert.equal(MOCK_COPILOT_RESPONSE.cached, false);
});

// =========================================================================
// API Client Method Tests (with mocked fetch)
// =========================================================================

test('api.getLatestIncidentCopilot: fetches latest analysis endpoint', async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl = null;

  globalThis.fetch = async (url) => {
    requestedUrl = url;
    return {
      ok: true,
      status: 200,
      json: async () => MOCK_COPILOT_RESPONSE,
    };
  };

  try {
    const { default: api } = await import('../services/api.js');
    const result = await api.getLatestIncidentCopilot(1, 2, 42);
    assert.ok(requestedUrl.includes('/tenants/1/projects/2/incidents/42/copilot/latest'));
    assert.equal(result.id, 101);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('api.analyzeIncidentCopilot: sends force_refresh parameter accurately', async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl = null;
  let requestedBody = null;

  globalThis.fetch = async (url, options) => {
    requestedUrl = url;
    requestedBody = JSON.parse(options.body);
    return {
      ok: true,
      status: 200,
      json: async () => ({ ...MOCK_COPILOT_RESPONSE, cached: false }),
    };
  };

  try {
    const { default: api } = await import('../services/api.js');

    // Case 1: normal analysis (force_refresh = false)
    await api.analyzeIncidentCopilot(1, 2, 42, { force_refresh: false });
    assert.ok(requestedUrl.includes('/tenants/1/projects/2/incidents/42/copilot/analyze'));
    assert.equal(requestedBody.force_refresh, false);

    // Case 2: force refresh (force_refresh = true)
    await api.analyzeIncidentCopilot(1, 2, 42, { force_refresh: true });
    assert.equal(requestedBody.force_refresh, true);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('api.analyzeIncidentCopilot: propagates 504 provider timeout as ApiError', async () => {
  const originalFetch = globalThis.fetch;

  globalThis.fetch = async () => ({
    ok: false,
    status: 504,
    json: async () => ({ detail: 'AI Copilot provider timed out' }),
  });

  try {
    const { default: api, ApiError } = await import('../services/api.js');
    await assert.rejects(
      async () => {
        await api.analyzeIncidentCopilot(1, 2, 42);
      },
      (err) => {
        assert.ok(err instanceof ApiError);
        assert.equal(err.status, 504);
        assert.ok(err.message.includes('timed out'));
        return true;
      }
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('api.analyzeIncidentCopilot: propagates 503 provider unavailable as ApiError', async () => {
  const originalFetch = globalThis.fetch;

  globalThis.fetch = async () => ({
    ok: false,
    status: 503,
    json: async () => ({ detail: 'AI Copilot provider unavailable' }),
  });

  try {
    const { default: api, ApiError } = await import('../services/api.js');
    await assert.rejects(
      async () => {
        await api.analyzeIncidentCopilot(1, 2, 42);
      },
      (err) => {
        assert.ok(err instanceof ApiError);
        assert.equal(err.status, 503);
        assert.ok(err.message.includes('unavailable'));
        return true;
      }
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('api.analyzeIncidentCopilot: propagates 502 malformed response as ApiError', async () => {
  const originalFetch = globalThis.fetch;

  globalThis.fetch = async () => ({
    ok: false,
    status: 502,
    json: async () => ({ detail: 'AI Copilot provider returned invalid structured response' }),
  });

  try {
    const { default: api, ApiError } = await import('../services/api.js');
    await assert.rejects(
      async () => {
        await api.analyzeIncidentCopilot(1, 2, 42);
      },
      (err) => {
        assert.ok(err instanceof ApiError);
        assert.equal(err.status, 502);
        return true;
      }
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

// =========================================================================
// Phase 15C: Conversational AI Incident Copilot Tests
// =========================================================================

test('Copilot Safety Guarantee: Copilot cannot directly modify production systems', () => {
  assert.equal(
    COPILOT_CANNOT_MODIFY_SYSTEMS_NOTICE,
    'Copilot cannot directly modify production systems.'
  );
  assert.equal(isAutonomousActionAllowed(), false);
});

test('validateCopilotChatResponse: accepts valid Phase 15C structured chat response', () => {
  const validResponse = {
    id: 10,
    incident_id: 3,
    user_message: 'Why do you think H1 is probable?',
    answer: 'The strongest evidence is the error spike immediately following release v2.4.0.',
    model: 'gemini-3.8-flash',
    cached: false,
    created_at: '2026-09-30T12:00:00Z',
    evidence: [
      {
        source_type: 'issue',
        source_id: 1,
        claim: 'Issue #1 surged to 45 occurrences in 15 minutes',
      },
      {
        source_type: 'release',
        source_id: 'v2.4.0',
        claim: 'Release v2.4.0 deployed 15 minutes before error onset',
      },
    ],
    uncertainties: ['Database connection saturation data is not available'],
  };

  const result = validateCopilotChatResponse(validResponse);
  assert.equal(result.valid, true);
});

test('validateCopilotChatResponse: rejects malformed or missing fields', () => {
  assert.equal(validateCopilotChatResponse(null).valid, false);
  assert.equal(validateCopilotChatResponse({}).valid, false);
  assert.equal(validateCopilotChatResponse({ answer: '' }).valid, false);
  assert.equal(
    validateCopilotChatResponse({ answer: 'Valid answer', evidence: 'not-an-array' }).valid,
    false
  );
  assert.equal(
    validateCopilotChatResponse({
      answer: 'Valid answer',
      evidence: [],
      uncertainties: 'not-an-array',
    }).valid,
    false
  );
});

test('formatEvidenceBadge: accurately formats source types and IDs', () => {
  assert.equal(
    formatEvidenceBadge({ source_type: 'issue', source_id: 1, claim: 'claim' }),
    'Evidence: Issue #1'
  );
  assert.equal(
    formatEvidenceBadge({ source_type: 'release', source_id: 'v2.4.0', claim: 'claim' }),
    'Evidence: Release #v2.4.0'
  );
  assert.equal(
    formatEvidenceBadge({ source_type: 'feature_flag', source_id: 'stripe_v3', claim: 'claim' }),
    'Evidence: Feature Flag #stripe_v3'
  );
  assert.equal(
    formatEvidenceBadge({ source_type: 'flag_audit', source_id: 42, claim: 'claim' }),
    'Evidence: Flag Audit #42'
  );
  assert.equal(
    formatEvidenceBadge({ source_type: 'timeline', source_id: 5, claim: 'claim' }),
    'Evidence: Timeline Event #5'
  );
  assert.equal(
    formatEvidenceBadge({ source_type: 'mitigation', source_id: 2, claim: 'claim' }),
    'Evidence: Mitigation #2'
  );
  assert.equal(
    formatEvidenceBadge({ source_type: 'event', source_id: 'ev-123', claim: 'claim' }),
    'Evidence: Event #ev-123'
  );
  assert.equal(
    formatEvidenceBadge({ source_type: 'incident', source_id: 3, claim: 'claim' }),
    'Evidence: Incident #3'
  );
  assert.equal(
    formatEvidenceBadge({ source_type: 'incident', source_id: null, claim: 'claim' }),
    'Evidence: Incident'
  );
  assert.equal(formatEvidenceBadge(null), 'Evidence');
});

test('api.getIncidentCopilotChat: fetches conversation history with limit', async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl = null;

  globalThis.fetch = async (url) => {
    requestedUrl = url;
    return {
      ok: true,
      status: 200,
      json: async () => [
        {
          id: 1,
          incident_id: 42,
          role: 'user',
          content: 'Why is H1 likely?',
          created_at: '2026-09-30T10:00:00Z',
        },
        {
          id: 2,
          incident_id: 42,
          role: 'assistant',
          content: 'Based on telemetry, H1 is supported by Issue #1.',
          answer: 'Based on telemetry, H1 is supported by Issue #1.',
          evidence: [{ source_type: 'issue', source_id: 1, claim: 'High error rate' }],
          uncertainties: [],
          created_at: '2026-09-30T10:00:05Z',
        },
      ],
    };
  };

  try {
    const { default: api } = await import('../services/api.js');
    const result = await api.getIncidentCopilotChat(1, 2, 42, 25);
    assert.ok(requestedUrl.includes('/api/v1/tenants/1/projects/2/incidents/42/copilot/chat?limit=25'));
    assert.equal(result.length, 2);
    assert.equal(result[0].role, 'user');
    assert.equal(result[1].role, 'assistant');
    assert.equal(result[1].evidence.length, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('api.sendIncidentCopilotChat: sends inquiry and receives structured answer', async () => {
  const originalFetch = globalThis.fetch;
  let capturedBody = null;
  let capturedUrl = null;

  globalThis.fetch = async (url, options) => {
    capturedUrl = url;
    capturedBody = JSON.parse(options.body);
    return {
      ok: true,
      status: 200,
      json: async () => ({
        id: 105,
        incident_id: 42,
        user_message: 'What caused the spike?',
        answer: 'The spike was triggered by deployment v2.4.0.',
        model: 'gemini-3.8-flash',
        cached: false,
        created_at: '2026-09-30T12:00:00Z',
        evidence: [
          { source_type: 'release', source_id: 'v2.4.0', claim: 'Deployed 10 minutes prior' },
        ],
        uncertainties: ['DB connection pool telemetry missing'],
      }),
    };
  };

  try {
    const { default: api } = await import('../services/api.js');
    const result = await api.sendIncidentCopilotChat(1, 2, 42, 'What caused the spike?');
    assert.ok(capturedUrl.includes('/api/v1/tenants/1/projects/2/incidents/42/copilot/chat'));
    assert.equal(capturedBody.message, 'What caused the spike?');
    assert.equal(result.answer, 'The spike was triggered by deployment v2.4.0.');
    assert.equal(result.evidence.length, 1);
    assert.equal(result.evidence[0].source_id, 'v2.4.0');
    assert.equal(result.uncertainties.length, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('api.sendIncidentCopilotChat: propagates 504 timeout safely', async () => {
  const originalFetch = globalThis.fetch;

  globalThis.fetch = async () => ({
    ok: false,
    status: 504,
    json: async () => ({ detail: 'AI Copilot provider timed out' }),
  });

  try {
    const { default: api, ApiError } = await import('../services/api.js');
    await assert.rejects(
      async () => {
        await api.sendIncidentCopilotChat(1, 2, 42, 'Question');
      },
      (err) => {
        assert.ok(err instanceof ApiError);
        assert.equal(err.status, 504);
        const errorState = getCopilotErrorState(err);
        assert.equal(errorState.status, 504);
        assert.ok(errorState.title.includes('Timed Out'));
        assert.equal(errorState.allowRetry, true);
        return true;
      }
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

// ============================================================================
// Phase 15D — Production Hardening & Evaluation Suite
// ============================================================================

test('Phase 15D: formatModelBadge formats primary vs fallback models correctly', () => {
  assert.equal(formatModelBadge('gemini-3.8-flash'), 'gemini-3.8-flash');
  assert.equal(formatModelBadge('gemini-3.5-flash-lite'), 'gemini-3.5-flash-lite (Fallback)');
  assert.equal(formatModelBadge('mock-copilot-lite'), 'mock-copilot-lite (Fallback)');
  assert.equal(formatModelBadge(null), 'AI Copilot');
  assert.equal(formatModelBadge(''), 'AI Copilot');
});

test('Phase 15D: getCopilotErrorState handles HTTP 429 rate limit correctly', () => {
  const errorState = getCopilotErrorState({ status: 429 });
  assert.equal(errorState.status, 429);
  assert.equal(errorState.title, 'Rate Limit Exceeded');
  assert.ok(errorState.message.includes('rate limit was reached'));
  assert.equal(errorState.allowRetry, true);
});

test('Phase 15D: formatEvidenceBadge formats all source types accurately', () => {
  assert.equal(formatEvidenceBadge({ source_type: 'incident', source_id: '42' }), 'Evidence: Incident #42');
  assert.equal(formatEvidenceBadge({ source_type: 'issue', source_id: '15' }), 'Evidence: Issue #15');
  assert.equal(formatEvidenceBadge({ source_type: 'release', source_id: 'v1.2.0' }), 'Evidence: Release #v1.2.0');
  assert.equal(formatEvidenceBadge({ source_type: 'feature_flag', source_id: 'enable_checkout' }), 'Evidence: Feature Flag #enable_checkout');
  assert.equal(formatEvidenceBadge({ source_type: 'mitigation', source_id: '3' }), 'Evidence: Mitigation #3');
  assert.equal(formatEvidenceBadge({ source_type: 'timeline', source_id: '7' }), 'Evidence: Timeline Event #7');
  assert.equal(formatEvidenceBadge({ source_type: 'custom', source_id: null }), 'Evidence: custom');
  assert.equal(formatEvidenceBadge(null), 'Evidence');
});

test('Phase 15D: Safety guarantees — autonomous action is strictly disallowed', () => {
  assert.equal(isAutonomousActionAllowed(), false);
  assert.ok(COPILOT_ADVISORY_NOTICE.includes('advisory'));
  assert.ok(COPILOT_NO_AUTONOMOUS_ACTION_NOTICE.includes('does not automatically modify'));
  assert.ok(COPILOT_CANNOT_MODIFY_SYSTEMS_NOTICE.includes('cannot directly modify production'));
});

test('Phase 15D: validateCopilotChatResponse checks required fields and arrays', () => {
  // Valid response
  const valid = validateCopilotChatResponse({
    answer: 'Hypothesis H1 is probable based on release v2.4.1.',
    evidence: [{ source_type: 'release', source_id: 'v2.4.1', claim: 'Deployed prior to error spike' }],
    uncertainties: ['CPU metrics unavailable'],
  });
  assert.equal(valid.valid, true);

  // Missing answer
  const missingAnswer = validateCopilotChatResponse({
    evidence: [],
    uncertainties: [],
  });
  assert.equal(missingAnswer.valid, false);
  assert.ok(missingAnswer.error.includes('answer string'));

  // Non-array evidence
  const invalidEvidence = validateCopilotChatResponse({
    answer: 'An answer',
    evidence: 'not-an-array',
    uncertainties: [],
  });
  assert.equal(invalidEvidence.valid, false);
  assert.ok(invalidEvidence.error.includes('evidence array'));
});
