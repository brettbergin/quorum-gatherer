"""The Chairman report renderer fills every Output-Format section."""

from app.agents.synthesis import render_report_markdown
from app.schemas.agent_outputs import (
    Alternative,
    CouncilReportContent,
    DecisionClassification,
    ExecutiveSummary,
    FinalRecommendation,
    InvestmentReview,
    KeyAssumptions,
    StressTest,
    SuccessMetrics,
)


def _sample() -> CouncilReportContent:
    return CouncilReportContent(
        executive_summary=ExecutiveSummary(
            recommendation="Investigate",
            why_now="Window",
            biggest_risk="Adoption",
            success_metric="WAU",
            next_action="2 interviews",
        ),
        clarified_idea="Build X",
        strategic_question="Invest in X?",
        key_assumptions=KeyAssumptions(facts=["F"], assumptions=["A"], speculation=["S"]),
        alternative_approaches=[
            Alternative(name="Alt", strengths="cheap", weaknesses="small", comparison="less")
        ],
        stress_test=StressTest(
            customer_value="cv",
            business_value="bv",
            strategic_differentiation="sd",
            feasibility="fe",
            distribution="di",
            timing="ti",
            defensibility="de",
        ),
        investment_review=InvestmentReview(
            recommendation="Investigate", opportunity_cost="oc", why_this_wins="lev"
        ),
        decision_classification=DecisionClassification(
            reversible=["pilot"], difficult_to_reverse=["bet"]
        ),
        mvp="Smallest",
        validation_experiments=["E1"],
        success_metrics=SuccessMetrics(leading=["signups"], lagging=["rev"]),
        kill_criteria=["<5%"],
        tensions=["speed vs rigor"],
        final_recommendation=FinalRecommendation(
            recommendation="Investigate",
            confidence="Medium",
            evidence_quality="Moderate",
            rationale="because",
            next_actions=["A"],
        ),
    )


def test_render_includes_all_sections():
    md = render_report_markdown(_sample())
    for section in [
        "## Executive Summary",
        "## Clarified Idea",
        "## Key Assumptions and Risks",
        "## Alternative Approaches",
        "## Stress Test Results",
        "## Investment Review",
        "## Decision Classification",
        "## MVP",
        "## Validation Experiments",
        "## Success Metrics",
        "## Kill Criteria",
        "## Tensions and Trade-offs",
        "## Final Recommendation",
    ]:
        assert section in md
    assert "speed vs rigor" in md
