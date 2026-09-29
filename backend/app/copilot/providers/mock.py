"""
Mock provider implementation for deterministic, isolated, and offline testing.
"""

from typing import Any, Optional
from app.copilot.providers.base import (
    BaseCopilotProvider,
    CopilotProviderError,
    CopilotResponseParseError,
    CopilotTimeoutError,
)
from app.copilot.schemas import (
    CopilotAnalysisPayload,
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
                )
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
