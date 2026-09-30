import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Sparkles,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Shield,
  Search,
  Database,
  HelpCircle,
  Layers,
  ArrowRight,
  ExternalLink,
  Bot,
  Zap,
  Send,
  MessageSquare,
  User,
  AlertCircle,
} from 'lucide-react';
import api, { ApiError } from '../services/api';
import { formatExactTimestamp, formatRelativeTime } from '../utils/formatters';
import {
  COPILOT_ADVISORY_NOTICE,
  COPILOT_NO_AUTONOMOUS_ACTION_NOTICE,
  COPILOT_CANNOT_MODIFY_SYSTEMS_NOTICE,
  getCopilotErrorState,
  formatEvidenceBadge,
} from '../utils/copilot';

const SUGGESTED_QUESTIONS = [
  "Why do you think H1 is probable?",
  "What evidence supports H1?",
  "Why is Issue #1 probably not the primary cause?",
  "What changed immediately before the incident?",
  "What information is missing to confirm the root cause?",
  "What should I investigate first?",
  "What happened during the mitigation?",
  "What changed when the feature flag was reverted?",
];

/**
 * Phase 15B & 15C — AI Incident Copilot Section
 * Provides evidence-grounded, advisory root-cause analysis and conversational investigation.
 * Strictly separates observed evidence from AI inferences.
 * Does not perform autonomous actions or feature-flag modifications.
 */
export default function IncidentCopilotSection({ tenantId, projectId, incidentId }) {
  const [analysisRecord, setAnalysisRecord] = useState(null);
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [errorState, setErrorState] = useState(null);

  // Conversational Chat State (Phase 15C)
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState(null);
  const messagesEndRef = useRef(null);

  // Load the latest persisted analysis on mount
  const loadLatestAnalysis = useCallback(async () => {
    if (!tenantId || !projectId || !incidentId) return;
    setInitialLoading(true);
    setErrorState(null);
    try {
      const data = await api.getLatestIncidentCopilot(tenantId, projectId, incidentId);
      setAnalysisRecord(data);
    } catch (err) {
      // 404 indicates no analysis has been generated yet for this incident
      if (err.status === 404) {
        setAnalysisRecord(null);
      } else {
        // Handle unexpected error during initial load
        setErrorState({
          status: err.status,
          title: 'Unable to Load Previous Analysis',
          message: err.message || 'Could not retrieve existing AI Copilot analysis.',
        });
      }
    } finally {
      setInitialLoading(false);
    }
  }, [tenantId, projectId, incidentId]);

  // Load chat history on mount
  const loadChatHistory = useCallback(async () => {
    if (!tenantId || !projectId || !incidentId) return;
    try {
      const history = await api.getIncidentCopilotChat(tenantId, projectId, incidentId);
      if (Array.isArray(history)) {
        setChatMessages(history);
      }
    } catch (err) {
      console.warn('Failed to load copilot chat history:', err);
    }
  }, [tenantId, projectId, incidentId]);

  useEffect(() => {
    loadLatestAnalysis();
    loadChatHistory();
  }, [loadLatestAnalysis, loadChatHistory]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (chatMessages.length > 0) {
      scrollToBottom();
    }
  }, [chatMessages.length]);

  const handleSendChat = async (messageText) => {
    const textToSend = (messageText || chatInput).trim();
    if (!textToSend || chatLoading || !tenantId || !projectId || !incidentId) return;

    setChatLoading(true);
    setChatError(null);
    setChatInput('');

    // Optimistically record user message
    const tempUserMsg = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: textToSend,
      created_at: new Date().toISOString(),
    };
    setChatMessages((prev) => [...prev, tempUserMsg]);

    try {
      const response = await api.sendIncidentCopilotChat(tenantId, projectId, incidentId, textToSend);
      const assistantMsg = {
        id: response.id,
        role: 'assistant',
        content: response.answer,
        answer: response.answer,
        model: response.model,
        created_at: response.created_at,
        evidence: response.evidence || [],
        uncertainties: response.uncertainties || [],
      };
      setChatMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      setChatError(getCopilotErrorState(err));
    } finally {
      setChatLoading(false);
    }
  };

  // Request analysis (or force refresh)
  const handleRunAnalysis = async (forceRefresh = false) => {
    if (!tenantId || !projectId || !incidentId || loading) return;
    setLoading(true);
    setErrorState(null);

    try {
      const response = await api.analyzeIncidentCopilot(tenantId, projectId, incidentId, {
        force_refresh: forceRefresh,
      });
      setAnalysisRecord(response);
    } catch (err) {
      setErrorState(getCopilotErrorState(err));
    } finally {
      setLoading(false);
    }
  };

  const payload = analysisRecord?.analysis;

  return (
    <div
      data-testid="copilot-section"
      className="p-5 bg-slate-900 border border-slate-800 rounded-xl space-y-5"
    >
      {/* Header & Main Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="p-1 rounded-md bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <Sparkles className="w-4 h-4" />
            </span>
            <h2 className="text-sm font-bold text-slate-100 tracking-tight">AI Incident Copilot</h2>
            {analysisRecord && (
              <span
                data-testid="copilot-provider-badge"
                className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-indigo-300 border border-slate-700"
              >
                {analysisRecord.provider} · {analysisRecord.model}
              </span>
            )}
            {analysisRecord?.cached && (
              <span
                data-testid="copilot-cached-badge"
                className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-800/80 text-emerald-400 border border-emerald-500/30 flex items-center gap-1"
                title="Retrieved from deterministic context cache"
              >
                Cached
              </span>
            )}
          </div>
          <p className="text-xs text-slate-400">
            Evidence-based incident analysis & root-cause candidate evaluation.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {analysisRecord?.created_at && (
            <span
              data-testid="copilot-timestamp"
              className="text-[11px] text-slate-500 font-mono hidden md:inline-block"
              title={formatExactTimestamp(analysisRecord.created_at)}
            >
              Generated {formatRelativeTime(analysisRecord.created_at)}
            </span>
          )}

          {analysisRecord ? (
            <button
              data-testid="copilot-refresh-btn"
              onClick={() => handleRunAnalysis(true)}
              disabled={loading}
              className="px-3 py-1.5 bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-500/30 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              {loading ? 'Analyzing...' : 'Refresh Analysis'}
            </button>
          ) : (
            <button
              data-testid="copilot-analyze-btn"
              onClick={() => handleRunAnalysis(false)}
              disabled={loading || initialLoading}
              className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 transition shadow-sm cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Sparkles className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              {loading ? 'Analyzing Incident...' : 'Analyze Incident'}
            </button>
          )}
        </div>
      </div>

      {/* Mandatory AI Safety & Advisory Notice */}
      <div
        data-testid="copilot-advisory-notice"
        className="p-3 bg-indigo-950/20 border border-indigo-900/40 rounded-lg text-xs text-indigo-200/80 flex items-start gap-2.5"
      >
        <Shield className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
        <div className="space-y-0.5">
          <p className="font-medium text-indigo-200">
            {COPILOT_ADVISORY_NOTICE}
          </p>
          <p className="text-[11px] text-indigo-300/70">
            {COPILOT_NO_AUTONOMOUS_ACTION_NOTICE} All findings represent candidate hypotheses for engineering review.
          </p>
        </div>
      </div>

      {/* State: Initial Loading Skeleton */}
      {initialLoading && (
        <div className="py-8 flex flex-col items-center justify-center text-center space-y-3">
          <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-xs text-slate-400 font-medium">Checking for existing incident analysis...</p>
        </div>
      )}

      {/* State: Active Request Loading */}
      {loading && (
        <div
          data-testid="copilot-loading-state"
          className="py-10 px-4 bg-slate-800/40 border border-slate-800 rounded-xl flex flex-col items-center justify-center text-center space-y-3 animate-pulse"
        >
          <div className="w-8 h-8 rounded-full bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
            <RefreshCw className="w-4 h-4 animate-spin" />
          </div>
          <div className="space-y-1">
            <h3 className="text-sm font-semibold text-slate-200">Analyzing incident context...</h3>
            <p className="text-xs text-slate-400 max-w-md">
              Aggregating linked error events, stack traces, recent releases, feature flag mutations, and activity timeline...
            </p>
          </div>
        </div>
      )}

      {/* State: Error / Failure with Friendly Retry */}
      {errorState && !loading && (
        <div
          data-testid="copilot-error-state"
          className="p-4 bg-rose-950/20 border border-rose-900/40 rounded-xl space-y-3"
        >
          <div className="flex items-start gap-3">
            <div className="p-1.5 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 shrink-0">
              <AlertTriangle className="w-4 h-4" />
            </div>
            <div className="space-y-1 flex-1">
              <h3 className="text-xs font-bold text-rose-200 uppercase tracking-wider">
                {errorState.title}
              </h3>
              <p className="text-xs text-rose-300/80">{errorState.message}</p>
            </div>
          </div>
          <div className="flex justify-end pt-2 border-t border-rose-900/30">
            <button
              data-testid="copilot-retry-btn"
              onClick={() => handleRunAnalysis(true)}
              className="px-3 py-1 bg-rose-600/20 hover:bg-rose-600/30 text-rose-200 border border-rose-500/30 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition cursor-pointer"
            >
              <RefreshCw className="w-3 h-3" />
              Retry Analysis
            </button>
          </div>
        </div>
      )}

      {/* State: Empty / No Analysis Yet */}
      {!analysisRecord && !loading && !initialLoading && !errorState && (
        <div
          data-testid="copilot-empty-state"
          className="p-6 bg-slate-800/30 border border-dashed border-slate-700/60 rounded-xl text-center space-y-4"
        >
          <div className="w-10 h-10 mx-auto rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
            <Bot className="w-5 h-5" />
          </div>
          <div className="space-y-1 max-w-md mx-auto">
            <h3 className="text-sm font-semibold text-slate-200">No AI Analysis Run Yet</h3>
            <p className="text-xs text-slate-400">
              ReleaseGuard Copilot evaluates incident telemetry to isolate plausible triggers, correlate recent deployments or flag updates, and suggest safe operator investigation paths.
            </p>
          </div>
          <button
            data-testid="copilot-analyze-initial-btn"
            onClick={() => handleRunAnalysis(false)}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold inline-flex items-center gap-2 transition cursor-pointer"
          >
            <Sparkles className="w-4 h-4" />
            Analyze Incident Now
          </button>
        </div>
      )}

      {/* State: Structured Analysis Display */}
      {payload && !loading && (
        <div data-testid="copilot-analysis-content" className="space-y-6">
          {/* SECTION A: INCIDENT SUMMARY */}
          {payload.summary && (
            <div className="space-y-2">
              <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-indigo-400" />
                Executive Summary
              </h3>
              <div
                data-testid="copilot-summary"
                className="p-4 bg-slate-800/50 border border-slate-700/70 rounded-xl text-xs text-slate-200 leading-relaxed"
              >
                {payload.summary}
              </div>
            </div>
          )}

          {/* SECTION B: RECENT CHANGES */}
          {payload.recent_changes && payload.recent_changes.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-amber-400" />
                Recent System Changes ({payload.recent_changes.length})
              </h3>
              <div className="space-y-2">
                {payload.recent_changes.map((change, idx) => (
                  <div
                    key={idx}
                    data-testid="copilot-recent-change-item"
                    className="p-3 bg-slate-800/40 border border-slate-700/60 rounded-lg text-xs space-y-1.5"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-medium uppercase bg-slate-700 text-slate-300 border border-slate-600">
                          {change.type}
                        </span>
                        <span className="font-semibold text-slate-100 font-mono">
                          {change.identifier}
                        </span>
                      </div>
                      {change.timestamp && (
                        <span className="text-[11px] text-slate-500 font-mono">
                          {formatRelativeTime(change.timestamp)}
                        </span>
                      )}
                    </div>
                    <p className="text-slate-300 text-xs">{change.description}</p>
                    {change.potential_relevance && (
                      <p className="text-[11px] text-slate-400 italic">
                        Relevance: {change.potential_relevance}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* SECTION C: ROOT-CAUSE HYPOTHESES (EVIDENCE VS INFERENCE SEPARATION) */}
          {payload.hypotheses && payload.hypotheses.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                  <HelpCircle className="w-3.5 h-3.5 text-rose-400" />
                  Root-Cause Hypotheses ({payload.hypotheses.length})
                </h3>
                <span className="text-[11px] text-slate-500 italic">
                  Calibrated candidate explanations
                </span>
              </div>

              <div className="space-y-3">
                {payload.hypotheses.map((hyp) => (
                  <div
                    key={hyp.id || hyp.title}
                    data-testid="copilot-hypothesis-item"
                    className="p-4 bg-slate-800/50 border border-slate-700 rounded-xl space-y-3"
                  >
                    {/* Hypothesis Title & Likelihood */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="px-1.5 py-0.5 rounded text-[11px] font-bold font-mono bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                          {hyp.id}
                        </span>
                        <h4 className="font-bold text-slate-100 text-sm">{hyp.title}</h4>
                      </div>
                      <span
                        data-testid="hypothesis-likelihood-badge"
                        className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wider border self-start sm:self-center ${
                          hyp.likelihood === 'probable'
                            ? 'bg-amber-500/10 text-amber-300 border-amber-500/30'
                            : hyp.likelihood === 'plausible'
                            ? 'bg-blue-500/10 text-blue-300 border-blue-500/30'
                            : 'bg-slate-700/60 text-slate-400 border-slate-600'
                        }`}
                      >
                        Likelihood: {hyp.likelihood}
                      </span>
                    </div>

                    {/* Hypothesis Explanation */}
                    {hyp.explanation && (
                      <p className="text-xs text-slate-300 leading-relaxed">{hyp.explanation}</p>
                    )}

                    {/* Dual Box: OBSERVED EVIDENCE vs AI INFERENCE */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
                      {/* Left: Observed Evidence */}
                      <div
                        data-testid="hypothesis-evidence-box"
                        className="p-3 bg-emerald-950/15 border border-emerald-800/40 rounded-lg space-y-1.5"
                      >
                        <div className="flex items-center gap-1.5 text-emerald-400 text-[11px] font-bold uppercase tracking-wider">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          Observed Evidence (Telemetry Facts)
                        </div>
                        {Array.isArray(hyp.evidence) && hyp.evidence.length > 0 ? (
                          <ul className="space-y-1 text-xs text-slate-200 list-disc list-inside">
                            {hyp.evidence.map((ev, eIdx) => (
                              <li key={eIdx} className="leading-snug">
                                {ev}
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-xs text-slate-500 italic">No direct evidence points cited.</p>
                        )}
                      </div>

                      {/* Right: AI Inference */}
                      <div
                        data-testid="hypothesis-inference-box"
                        className="p-3 bg-purple-950/15 border border-purple-800/40 rounded-lg space-y-1.5"
                      >
                        <div className="flex items-center gap-1.5 text-purple-400 text-[11px] font-bold uppercase tracking-wider">
                          <Bot className="w-3.5 h-3.5" />
                          AI Inference (Reasoned Deduction)
                        </div>
                        {Array.isArray(hyp.inference) && hyp.inference.length > 0 ? (
                          <ul className="space-y-1 text-xs text-slate-200 list-disc list-inside">
                            {hyp.inference.map((inf, iIdx) => (
                              <li key={iIdx} className="leading-snug">
                                {inf}
                              </li>
                            ))}
                          </ul>
                        ) : typeof hyp.inference === 'string' ? (
                          <p className="text-xs text-slate-200">{hyp.inference}</p>
                        ) : (
                          <p className="text-xs text-slate-500 italic">No inferences provided.</p>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* SECTION D: RECOMMENDED ACTIONS */}
          {payload.recommended_actions && payload.recommended_actions.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                  <Zap className="w-3.5 h-3.5 text-amber-400" />
                  Recommended Next Steps ({payload.recommended_actions.length})
                </h3>
                <span className="text-[11px] text-slate-500 italic">
                  Advisory suggestions for operator review
                </span>
              </div>

              <div className="space-y-2.5">
                {payload.recommended_actions.map((act, idx) => (
                  <div
                    key={idx}
                    data-testid="copilot-recommended-action-item"
                    className="p-3.5 bg-slate-800/50 border border-slate-700 rounded-lg space-y-2 text-xs"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wider border ${
                            act.priority === 'immediate'
                              ? 'bg-rose-500/15 text-rose-300 border-rose-500/30'
                              : act.priority === 'secondary'
                              ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                              : 'bg-slate-700 text-slate-300 border-slate-600'
                          }`}
                        >
                          {act.priority}
                        </span>
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-slate-800 text-slate-300 border border-slate-700">
                          {act.action_type}
                        </span>
                        {act.target_flag_key && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                            Flag: {act.target_flag_key}
                          </span>
                        )}
                      </div>
                    </div>

                    <p className="text-slate-100 font-semibold">{act.description}</p>

                    {act.rationale && (
                      <p className="text-slate-300 text-xs">
                        <strong className="text-slate-400 font-medium">Rationale:</strong>{' '}
                        {act.rationale}
                      </p>
                    )}

                    {act.risk_assessment && (
                      <p className="text-[11px] text-slate-400 italic">
                        Risk Assessment: {act.risk_assessment}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* SECTION E: GROUNDED EVIDENCE */}
          {payload.evidence && payload.evidence.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                <Database className="w-3.5 h-3.5 text-cyan-400" />
                Telemetry Evidence Points ({payload.evidence.length})
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {payload.evidence.map((ev, idx) => (
                  <div
                    key={idx}
                    data-testid="copilot-evidence-item"
                    className="p-3 bg-slate-800/40 border border-slate-700/60 rounded-lg text-xs space-y-1"
                  >
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="font-mono text-cyan-400 font-medium">{ev.source}</span>
                      {ev.confidence && (
                        <span className="px-1.5 py-0.2 rounded text-[10px] font-mono bg-slate-700 text-slate-300">
                          {ev.confidence} confidence
                        </span>
                      )}
                    </div>
                    <p className="text-slate-200">{ev.description}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* SECTION F: UNCERTAINTIES & MISSING INFORMATION */}
          {payload.uncertainties && payload.uncertainties.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                <Search className="w-3.5 h-3.5 text-amber-400" />
                Uncertainties & Telemetry Gaps ({payload.uncertainties.length})
              </h3>
              <div className="space-y-2">
                {payload.uncertainties.map((unc, idx) => (
                  <div
                    key={idx}
                    data-testid="copilot-uncertainty-item"
                    className="p-3 bg-amber-950/10 border border-amber-900/30 rounded-lg text-xs space-y-1"
                  >
                    <div className="font-semibold text-amber-300 font-mono text-[11px]">
                      Area: {unc.area}
                    </div>
                    <p className="text-slate-200">{unc.missing_information}</p>
                    {unc.how_to_verify && (
                      <p className="text-[11px] text-slate-400">
                        <strong className="text-slate-300 font-medium">Verification step:</strong>{' '}
                        {unc.how_to_verify}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ============================================================ */}
      {/* PHASE 15C: CONVERSATIONAL INVESTIGATION CHAT SECTION          */}
      {/* ============================================================ */}
      <div
        data-testid="copilot-chat-section"
        className="mt-6 pt-5 border-t border-slate-800 space-y-4"
      >
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="space-y-0.5">
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
              <MessageSquare className="w-4 h-4 text-indigo-400" />
              Ask Copilot about this incident
            </h3>
            <p className="text-[11px] text-slate-400">
              Conversational inquiry strictly grounded in authorized incident telemetry and timeline.
            </p>
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-amber-400/90 font-mono bg-amber-500/10 px-2.5 py-1 rounded-md border border-amber-500/20">
            <Shield className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
            <span>{COPILOT_CANNOT_MODIFY_SYSTEMS_NOTICE}</span>
          </div>
        </div>

        {/* Suggested Question Prompt Pills */}
        <div className="flex flex-wrap gap-1.5 pt-1">
          {SUGGESTED_QUESTIONS.map((q, idx) => (
            <button
              key={idx}
              type="button"
              disabled={chatLoading}
              onClick={() => handleSendChat(q)}
              className="text-[11px] px-2.5 py-1 rounded-full bg-slate-800/80 hover:bg-slate-700/80 text-slate-300 hover:text-slate-100 border border-slate-700/60 transition disabled:opacity-50 text-left"
            >
              {q}
            </button>
          ))}
        </div>

        {/* Chat Messages Container */}
        <div
          data-testid="copilot-chat-messages"
          className="p-4 bg-slate-950/60 border border-slate-800 rounded-lg max-h-96 overflow-y-auto space-y-3"
        >
          {chatMessages.length === 0 ? (
            <div className="py-6 text-center text-xs text-slate-500 space-y-1">
              <Bot className="w-6 h-6 mx-auto text-slate-600 mb-1" />
              <p>No conversation yet for this incident.</p>
              <p className="text-[11px] text-slate-600">
                Ask any question about root causes, telemetry evidence, or recent releases.
              </p>
            </div>
          ) : (
            chatMessages.map((msg, idx) => (
              <div
                key={msg.id || idx}
                data-testid={`copilot-chat-message-${msg.role}`}
                className={`flex gap-3 text-xs ${
                  msg.role === 'user' ? 'justify-end' : 'justify-start'
                }`}
              >
                {msg.role === 'assistant' && (
                  <div className="w-6 h-6 rounded-md bg-indigo-500/20 text-indigo-400 flex items-center justify-center flex-shrink-0 mt-0.5 border border-indigo-500/30">
                    <Bot className="w-3.5 h-3.5" />
                  </div>
                )}
                <div
                  className={`max-w-[85%] rounded-lg p-3 space-y-2 ${
                    msg.role === 'user'
                      ? 'bg-indigo-600/30 text-indigo-100 border border-indigo-500/40'
                      : 'bg-slate-800/90 text-slate-200 border border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 text-[10px] text-slate-400 font-mono">
                    <span className="font-semibold uppercase tracking-wider text-slate-300">
                      {msg.role === 'user' ? 'Operator' : `Copilot (${msg.model || 'AI'})`}
                    </span>
                    {msg.created_at && (
                      <span>{formatRelativeTime(msg.created_at)}</span>
                    )}
                  </div>

                  <p className="whitespace-pre-wrap leading-relaxed text-slate-100">
                    {msg.answer || msg.content}
                  </p>

                  {/* Evidence Citations */}
                  {msg.evidence && msg.evidence.length > 0 && (
                    <div className="pt-2 border-t border-slate-700/60 space-y-1">
                      <div className="text-[10px] uppercase font-mono text-cyan-400 font-semibold tracking-wider flex items-center gap-1">
                        <Database className="w-3 h-3 text-cyan-400" />
                        Evidence Citations ({msg.evidence.length})
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {msg.evidence.map((ev, evIdx) => (
                          <div
                            key={evIdx}
                            data-testid="copilot-chat-evidence-badge"
                            className="px-2 py-0.5 rounded bg-cyan-950/40 border border-cyan-800/50 text-[10px] text-cyan-300 font-mono flex items-center gap-1"
                            title={ev.claim}
                          >
                            <span className="font-bold">{formatEvidenceBadge(ev)}:</span>
                            <span className="text-slate-300">{ev.claim}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Uncertainties */}
                  {msg.uncertainties && msg.uncertainties.length > 0 && (
                    <div className="pt-1 text-[11px] text-amber-300/90 italic flex items-start gap-1">
                      <Search className="w-3 h-3 flex-shrink-0 mt-0.5 text-amber-400" />
                      <span>Uncertainty: {msg.uncertainties.join('; ')}</span>
                    </div>
                  )}
                </div>
                {msg.role === 'user' && (
                  <div className="w-6 h-6 rounded-md bg-slate-700 text-slate-300 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <User className="w-3.5 h-3.5" />
                  </div>
                )}
              </div>
            ))
          )}

          {/* Loading indicator */}
          {chatLoading && (
            <div className="flex items-center gap-2 text-xs text-indigo-400 italic py-1 pl-1">
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              <span>Copilot is analyzing incident telemetry and citations...</span>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Chat Error State */}
        {chatError && (
          <div
            data-testid="copilot-chat-error"
            className="p-3 rounded-lg bg-red-950/40 border border-red-900/60 flex items-start justify-between gap-3 text-xs"
          >
            <div className="flex items-start gap-2 text-red-300">
              <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-red-200">{chatError.title}</p>
                <p className="text-[11px] text-red-300/90">{chatError.message}</p>
              </div>
            </div>
            {chatError.allowRetry && (
              <button
                type="button"
                onClick={() => setChatError(null)}
                className="px-2 py-1 rounded bg-red-900/40 hover:bg-red-900/60 text-red-200 text-[10px] font-mono border border-red-800"
              >
                Dismiss
              </button>
            )}
          </div>
        )}

        {/* Chat Input & Submit */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSendChat();
          }}
          className="flex items-center gap-2"
        >
          <input
            type="text"
            data-testid="copilot-chat-input"
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            disabled={chatLoading}
            placeholder="Ask about this incident..."
            className="flex-1 bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 disabled:opacity-50"
          />
          <button
            type="submit"
            data-testid="copilot-chat-send-btn"
            disabled={chatLoading || !chatInput.trim()}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 text-white text-xs font-semibold disabled:text-slate-500 disabled:cursor-not-allowed transition"
          >
            {chatLoading ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Send className="w-3.5 h-3.5" />
            )}
            <span>Send</span>
          </button>
        </form>
      </div>
    </div>
  );
}
