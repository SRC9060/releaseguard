"""
Mock provider implementation for deterministic, isolated, and offline testing.
"""

import re
from typing import Any, Optional
from app.copilot.providers.base import (
    BaseCopilotProvider,
    CopilotProviderError,
    CopilotResponseParseError,
    CopilotTimeoutError,
)
from app.copilot.schemas import (
    CopilotAnalysisPayload,
    CopilotChatEvidenceItem,
    CopilotChatPayload,
    EvidenceItem,
    Hypothesis,
    RecentChangeItem,
    RecommendedAction,
    UncertaintyItem,
)


class MockCopilotProvider(BaseCopilotProvider):
    """
    Mock provider for automated testing and offline development.
    Supports injecting specific errors (timeout, parse error) or custom response payloads.
    """

    def __init__(
        self,
        model_name: str = "mock-model-v1",
        timeout_seconds: float = 5.0,
        simulated_error: Optional[str] = None,
        custom_payload: Optional[CopilotAnalysisPayload] = None,
        raw_response_text: Optional[str] = None,
        simulate_timeout: bool = False,
        simulate_failure: bool = False,
        simulate_malformed: bool = False,
        custom_chat_payload: Optional[CopilotChatPayload] = None,
    ) -> None:
        super().__init__(model_name=model_name, timeout_seconds=timeout_seconds)
        if simulate_timeout:
            self.simulated_error = "timeout"
        elif simulate_failure:
            self.simulated_error = "provider_failure"
        elif simulate_malformed:
            self.simulated_error = "malformed_json"
        else:
            self.simulated_error = simulated_error
        self.custom_payload = custom_payload
        self.custom_chat_payload = custom_chat_payload
        self.raw_response_text = raw_response_text
        self.call_count = 0
        self.last_system_prompt: Optional[str] = None
        self.last_user_prompt: Optional[str] = None

    @property
    def provider_name(self) -> str:
        return "mock"

    async def analyze(self, system_prompt: str, user_prompt: str) -> CopilotAnalysisPayload:
        self.call_count += 1
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt

        if self.simulated_error == "timeout":
            raise CopilotTimeoutError(f"Mock provider call timed out after {self.timeout_seconds}s")
        elif self.simulated_error == "provider_failure":
            raise CopilotProviderError("Mock provider experienced upstream service outage")
        elif self.simulated_error == "malformed_json":
            raise CopilotResponseParseError("Failed to parse JSON response from LLM: invalid syntax")

        if self.custom_payload is not None:
            return self.custom_payload

        # Generate realistic, structured, grounded response
        return CopilotAnalysisPayload(
            summary="Automated mock analysis indicates elevated error rates correlated with recent system activity.",
            recent_changes=[
                RecentChangeItem(
                    type="release",
                    identifier="v2.4.0",
                    description="Core billing service deployed with updated Stripe webhook handlers.",
                    timestamp="2026-09-29T09:00:00Z",
                    potential_relevance="Deployed 15 minutes before the initial error spike."
                )
            ],
            hypotheses=[
                Hypothesis(
                    id="H1",
                    title="Regression in upstream webhook signature validation",
                    explanation="Recent changes to the webhook verification pathway may be rejecting legitimate requests.",
                    evidence=[
                        "504 and 500 error counts surged immediately following release v2.4.0.",
                        "Stack trace points to signature_verifier.py line 42."
                    ],
                    inference=[
                        "The new parsing logic likely fails to handle missing or mutated headers.",
                        "Third-party webhook payload format may differ from test environment expectations."
                    ],
                    likelihood="probable",
                ),
                Hypothesis(
                    id="H2",
                    title="Database connection pool saturation under retried requests",
                    explanation="Downstream timeout cascades caused request retries, exhausting available connection pool workers.",
                    evidence=[
                        "504 Gateway Timeout errors observed concurrently across payment workers.",
                    ],
                    inference=[
                        "Retries without exponential backoff may have compounded database thread exhaustion.",
                    ],
                    likelihood="plausible",
                ),
            ],
            recommended_actions=[
                RecommendedAction(
                    action_type="mitigation",
                    priority="immediate",
                    description="Evaluate killing or reverting the related feature flag if active, or preparing a rollback of v2.4.0.",
                    rationale="Error rate doubled immediately after the deployment window.",
                    risk_assessment="Low risk if safe fallback variant is configured; high impact if left unmitigated.",
                    target_flag_key="new_checkout_flow",
                    target_environment="production",
                ),
                RecommendedAction(
                    action_type="investigation",
                    priority="immediate",
                    description="Inspect incoming request payload headers in application logs for malformed signature tokens.",
                    rationale="Confirms whether signature validation is actively failing.",
                    risk_assessment="Read-only logging inspection carries no operational risk.",
                )
            ],
            evidence=[
                EvidenceItem(
                    source="error_event",
                    description="NullPointerException observed across 45 error events in 15 minutes.",
                    confidence="high",
                ),
                EvidenceItem(
                    source="release",
                    description="Release v2.4.0 was deployed to production at 09:00:00Z.",
                    confidence="high",
                )
            ],
            uncertainties=[
                UncertaintyItem(
                    area="database_load",
                    missing_information="Database connection pool metrics are not visible in telemetry.",
                    how_to_verify="Query connection pool saturation metrics in database monitoring.",
                )
            ]
        )

    async def chat(self, system_prompt: str, user_prompt: str) -> CopilotChatPayload:
        self.call_count += 1
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt

        if self.simulated_error == "timeout":
            raise CopilotTimeoutError(f"Mock provider call timed out after {self.timeout_seconds}s")
        elif self.simulated_error == "provider_failure":
            raise CopilotProviderError("Mock provider experienced upstream service outage")
        elif self.simulated_error == "malformed_json":
            raise CopilotResponseParseError("Failed to parse JSON response from LLM: invalid syntax")

        if self.custom_chat_payload is not None:
            return self.custom_chat_payload

        # Check if user prompt is inquiring about a hypothesis such as H1
        question_lower = user_prompt.lower()
        has_persisted_analysis = "<persisted_copilot_analysis>" in user_prompt

        if "h1" in question_lower:
            if has_persisted_analysis and '"id": "h1"' in question_lower:
                iss_match = re.search(r'"linked_issues":\s*\[\s*\{\s*"id":\s*(\d+)', user_prompt)
                issue_id = iss_match.group(1) if iss_match else "1"
                evidence_items = [
                    CopilotChatEvidenceItem(
                        source_type="issue",
                        source_id=issue_id,
                        claim=f"Issue #{issue_id} occurred 45 times across the incident window",
                    ),
                ]
                flag_match = re.search(r'"feature_flags":\s*\[\s*\{\s*"key":\s*"([^"]+)"', user_prompt)
                if flag_match:
                    evidence_items.append(
                        CopilotChatEvidenceItem(
                            source_type="feature_flag",
                            source_id=flag_match.group(1),
                            claim=f"Feature flag {flag_match.group(1)} was enabled 10 minutes prior to error onset",
                        )
                    )
                return CopilotChatPayload(
                    answer="Hypothesis H1 is probable because the newly enabled feature flag correlates temporally with error spikes in payment processing.",
                    evidence=evidence_items,
                    uncertainties=[
                        "Database connection pool metrics are not visible in telemetry",
                    ],
                )
            elif not has_persisted_analysis or '"id": "h1"' not in question_lower:
                return CopilotChatPayload(
                    answer="The available telemetry and incident context do not contain any reference to 'H1'. No persisted analysis with hypothesis H1 was found for this incident.",
                    evidence=[],
                    uncertainties=[
                        "No structured hypothesis H1 exists in the incident telemetry or persisted analysis",
                    ],
                )

        # Handling for questions regarding telemetry missing from ReleaseGuard
        if "cpu" in question_lower:
            return CopilotChatPayload(
                answer="CPU usage metrics are not available in ReleaseGuard incident telemetry. Please inspect APM or infrastructure monitoring tools (such as Prometheus, CloudWatch, or Datadog) to verify host and container CPU saturation during the incident window.",
                evidence=[],
                uncertainties=[
                    "CPU utilization telemetry is not available within ReleaseGuard.",
                ],
            )
        elif "connection-pool" in question_lower or "connection pool" in question_lower:
            return CopilotChatPayload(
                answer="Database connection-pool utilization is not available in current incident telemetry. Operators should inspect database server metrics or connection pool logs to determine if pool exhaustion occurred.",
                evidence=[],
                uncertainties=[
                    "Database connection-pool utilization metrics are not available within ReleaseGuard.",
                ],
            )
        elif "which customer" in question_lower or "customer was affected" in question_lower:
            return CopilotChatPayload(
                answer="Specific customer identities and affected account IDs are not available in ReleaseGuard aggregated incident telemetry. Check support tickets, access logs, or billing events to identify impacted customers.",
                evidence=[],
                uncertainties=[
                    "Customer-specific identity records are not available within ReleaseGuard telemetry.",
                ],
            )
        elif "source-code line" in question_lower or "source code line" in question_lower or "exact line" in question_lower:
            return CopilotChatPayload(
                answer="The exact source-code line that triggered the timeout is unavailable in captured stack traces. Review the trace telemetry and application repository at the deployed release commit to verify the timeout location.",
                evidence=[],
                uncertainties=[
                    "Exact source-code line for the timeout is not present in available stack traces.",
                ],
            )
        elif "requests per second" in question_lower or "how many requests" in question_lower or "rps" in question_lower:
            return CopilotChatPayload(
                answer="Requests per second (RPS) throughput metrics are not available in ReleaseGuard error ingestion. Review API gateway or ingress proxy monitoring to inspect traffic volume during the incident.",
                evidence=[],
                uncertainties=[
                    "Requests per second (RPS) throughput metrics are not available within ReleaseGuard.",
                ],
            )
        elif "sdk" in question_lower or "formatting" in question_lower:
            return CopilotChatPayload(
                answer="An unhandled KeyError formatting exception occurred in the ReleaseGuard SDK event payload processor.",
                evidence=[],
                uncertainties=[
                    "Stack trace does not include caller arguments.",
                ],
            )

        return CopilotChatPayload(
            answer="The primary evidence points to release v2.4.0 and related error spikes in webhook processing.",
            evidence=[
                CopilotChatEvidenceItem(
                    source_type="release",
                    source_id="v2.4.0",
                    claim="Release v2.4.0 was deployed 15 minutes before error onset",
                ),
                CopilotChatEvidenceItem(
                    source_type="issue",
                    source_id=1,
                    claim="Issue #1 occurred 45 times across the incident window",
                ),
            ],
            uncertainties=[
                "Database connection pool metrics are not visible in telemetry",
            ],
        )
