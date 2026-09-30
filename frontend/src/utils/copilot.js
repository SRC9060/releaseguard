/**
 * Phase 15B — AI Incident Copilot Utilities & Safety Helpers
 * Centralizes safety notices, error state mappings, and payload formatting.
 */

export const COPILOT_ADVISORY_NOTICE =
  'AI-generated analysis is advisory. Verify evidence before taking action.';

export const COPILOT_NO_AUTONOMOUS_ACTION_NOTICE =
  'AI does not automatically modify feature flags, releases, or incident status.';

export const COPILOT_CANNOT_MODIFY_SYSTEMS_NOTICE =
  'Copilot cannot directly modify production systems.';

/**
 * Maps HTTP and network errors from Copilot endpoints into safe, user-friendly UI state.
 * Prevents raw provider stack traces or payloads from leaking to the UI.
 */
export function getCopilotErrorState(err) {
  if (!err) return null;

  const status = err.status ?? 0;

  if (status === 504) {
    return {
      status: 504,
      title: 'AI Copilot Provider Timed Out',
      message:
        'The AI provider timed out while evaluating incident telemetry. The incident record and system status remain completely safe and unmodified.',
      allowRetry: true,
    };
  }

  if (status === 503) {
    return {
      status: 503,
      title: 'AI Copilot Provider Unavailable',
      message:
        'The external AI provider is currently unreachable or experiencing an outage. The incident is unaffected. Please try again in a few moments.',
      allowRetry: true,
    };
  }

  if (status === 502) {
    return {
      status: 502,
      title: 'Invalid Structured Response',
      message:
        'The AI provider returned an unexpected or malformed response structure. Raw model payload has been suppressed for security.',
      allowRetry: true,
    };
  }

  if (status === 403) {
    return {
      status: 403,
      title: 'Permission Denied',
      message:
        'You do not have sufficient permissions to request an AI Copilot analysis for this project.',
      allowRetry: false,
    };
  }

  if (status === 404) {
    return {
      status: 404,
      title: 'No Analysis Found',
      message: 'No previous AI Copilot analysis exists for this incident.',
      allowRetry: false,
    };
  }

  return {
    status,
    title: 'Analysis Request Failed',
    message: err.message || 'Failed to complete incident analysis. Please check your network connection.',
    allowRetry: true,
  };
}

/**
 * Validates that an analysis response conforms to the Phase 15A schema
 * and distinguishes observed evidence from inference.
 */
export function validateCopilotResponse(response) {
  if (!response || typeof response !== 'object') {
    return { valid: false, error: 'Response must be an object' };
  }

  if (!response.analysis || typeof response.analysis !== 'object') {
    return { valid: false, error: 'Response must contain an analysis object' };
  }

  const { analysis } = response;

  if (typeof analysis.summary !== 'string') {
    return { valid: false, error: 'Analysis must contain a summary string' };
  }

  if (!Array.isArray(analysis.hypotheses)) {
    return { valid: false, error: 'Analysis must contain a hypotheses array' };
  }

  for (const hyp of analysis.hypotheses) {
    if (!hyp.title) {
      return { valid: false, error: 'Hypothesis must have a title' };
    }
    if (!Array.isArray(hyp.evidence)) {
      return { valid: false, error: 'Hypothesis must contain evidence array' };
    }
    if (!Array.isArray(hyp.inference) && typeof hyp.inference !== 'string') {
      return { valid: false, error: 'Hypothesis must contain inference (array or string)' };
    }
  }

  if (!Array.isArray(analysis.recommended_actions)) {
    return { valid: false, error: 'Analysis must contain a recommended_actions array' };
  }

  return { valid: true };
}

/**
 * Guarantees that AI recommendations cannot be directly or automatically executed.
 */
export function isAutonomousActionAllowed() {
  return false;
}

/**
 * Validates that a conversational chat response conforms to the Phase 15C schema.
 */
export function validateCopilotChatResponse(response) {
  if (!response || typeof response !== 'object') {
    return { valid: false, error: 'Response must be an object' };
  }
  if (typeof response.answer !== 'string' || !response.answer.trim()) {
    return { valid: false, error: 'Chat response must contain an answer string' };
  }
  if (!Array.isArray(response.evidence)) {
    return { valid: false, error: 'Chat response must contain an evidence array' };
  }
  if (!Array.isArray(response.uncertainties)) {
    return { valid: false, error: 'Chat response must contain an uncertainties array' };
  }
  return { valid: true };
}

/**
 * Formats structured evidence reference badge for conversational citations.
 * Format: "Evidence: Issue #1" or "Evidence: Feature Flag #enable_v3"
 */
export function formatEvidenceBadge(evidenceItem) {
  if (!evidenceItem) return 'Evidence';
  const typeLabels = {
    incident: 'Incident',
    issue: 'Issue',
    release: 'Release',
    feature_flag: 'Feature Flag',
    flag_audit: 'Flag Audit',
    mitigation: 'Mitigation',
    timeline: 'Timeline Event',
    event: 'Event',
  };
  const label = typeLabels[evidenceItem.source_type] || evidenceItem.source_type || 'Evidence';
  if (evidenceItem.source_id !== null && evidenceItem.source_id !== undefined && evidenceItem.source_id !== '') {
    return `Evidence: ${label} #${evidenceItem.source_id}`;
  }
  return `Evidence: ${label}`;
}
