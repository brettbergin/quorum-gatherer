"""Structured outputs the agents are forced to produce (pydantic-ai output types).

- Council members (Phase A) return `CouncilContribution`.
- The Chairman (Phase B) returns `CouncilReportContent` — the full Output Format.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- members


class CouncilContribution(BaseModel):
    """One council member's independent contribution during deliberation."""

    headline: str = Field(description="One-line stance from this member's point of view.")
    perspective: str = Field(description="Concise, non-redundant analysis from the role.")
    key_points: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    # Owned Output-Format sections this member drives, keyed by section id
    # (e.g. {"investment_review": "...", "stress_feasibility": "..."}).
    section_contributions: dict[str, str] = Field(default_factory=dict)


# --------------------------------------------------------------------------- chairman


class ExecutiveSummary(BaseModel):
    recommendation: str
    why_now: str
    biggest_risk: str
    success_metric: str
    next_action: str


class KeyAssumptions(BaseModel):
    facts: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    speculation: list[str] = Field(default_factory=list)


class Alternative(BaseModel):
    name: str
    strengths: str
    weaknesses: str
    comparison: str = Field(description="How it compares to the original idea.")


class StressTest(BaseModel):
    customer_value: str
    business_value: str
    strategic_differentiation: str
    feasibility: str
    distribution: str
    timing: str
    defensibility: str


class InvestmentReview(BaseModel):
    recommendation: Literal["Invest", "Investigate", "Delay", "Reject"]
    opportunity_cost: str
    why_this_wins: str


class DecisionClassification(BaseModel):
    reversible: list[str] = Field(default_factory=list)
    difficult_to_reverse: list[str] = Field(default_factory=list)


class SuccessMetrics(BaseModel):
    leading: list[str] = Field(default_factory=list)
    lagging: list[str] = Field(default_factory=list)


class FinalRecommendation(BaseModel):
    recommendation: str
    confidence: Literal["High", "Medium", "Low"]
    evidence_quality: Literal["Strong", "Moderate", "Weak"]
    rationale: str
    next_actions: list[str] = Field(default_factory=list)


class CouncilReportContent(BaseModel):
    """The Chairman's full synthesis — mirrors the source prompt's Output Format."""

    executive_summary: ExecutiveSummary
    clarified_idea: str
    strategic_question: str
    key_assumptions: KeyAssumptions
    alternative_approaches: list[Alternative] = Field(default_factory=list)
    stress_test: StressTest
    investment_review: InvestmentReview
    decision_classification: DecisionClassification
    mvp: str
    validation_experiments: list[str] = Field(default_factory=list)
    success_metrics: SuccessMetrics
    kill_criteria: list[str] = Field(default_factory=list)
    tensions: list[str] = Field(
        default_factory=list, description="Decision-relevant disagreements / trade-offs."
    )
    final_recommendation: FinalRecommendation


# Registry so agent definition files can reference an output schema by name.
OUTPUT_SCHEMAS: dict[str, type[BaseModel]] = {
    "CouncilContribution": CouncilContribution,
    "CouncilReportContent": CouncilReportContent,
}


def resolve_output_schema(name: str) -> type[BaseModel]:
    try:
        return OUTPUT_SCHEMAS[name]
    except KeyError as exc:
        raise KeyError(f"unknown output_schema '{name}'; known: {sorted(OUTPUT_SCHEMAS)}") from exc
