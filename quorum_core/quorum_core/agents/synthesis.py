"""Prompt assembly for both phases, and rendering the Chairman's structured report
into the source prompt's Markdown Output Format."""

from __future__ import annotations

from quorum_core.schemas.agent_outputs import CouncilReportContent

Document = tuple[str, str]  # (filename, text)
Contribution = tuple[str, str]  # (agent display name, perspective text)


def _documents_block(documents: list[Document]) -> str:
    if not documents:
        return "_No additional context documents were provided._"
    parts = []
    for filename, text in documents:
        parts.append(f"### {filename}\n{text.strip()}")
    return "\n\n".join(parts)


# Asked of an agent (with its full clarification thread as history) right before synthesis, so the
# Chairman receives each chatted agent's *updated* position rather than its first-pass take.
FINAL_POSITION_PROMPT = (
    "Based on the full discussion above, state your final, updated position on the strategy idea — "
    "your recommendation and the key reasons — incorporating any clarifications provided. "
    "Be concise and decisive; do not ask further questions."
)


def build_member_prompt(idea: str, documents: list[Document]) -> str:
    return (
        "# Strategy idea to evaluate\n"
        f"{idea.strip()}\n\n"
        "# Provided context documents (authoritative)\n"
        f"{_documents_block(documents)}\n\n"
        "Give your council perspective on this idea now, from your role."
    )


def build_chairman_prompt(
    idea: str, documents: list[Document], contributions: list[Contribution]
) -> str:
    if contributions:
        deliberations = "\n\n".join(f"## {name}\n{text.strip()}" for name, text in contributions)
    else:
        deliberations = "_No council member contributions were produced._"
    return (
        "# Strategy idea\n"
        f"{idea.strip()}\n\n"
        "# Provided context documents (authoritative)\n"
        f"{_documents_block(documents)}\n\n"
        "# Council deliberations\n"
        f"{deliberations}\n\n"
        "Synthesize the council's input into the final report. Resolve the tensions, make a "
        "single recommendation, and populate every section of the required output."
    )


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items) if items else "- _None._"


def render_report_markdown(content: CouncilReportContent) -> str:
    es = content.executive_summary
    st = content.stress_test
    ir = content.investment_review
    dc = content.decision_classification
    sm = content.success_metrics
    fr = content.final_recommendation
    ka = content.key_assumptions

    alternatives = (
        "\n\n".join(
            f"### {a.name}\n"
            f"- **Strengths:** {a.strengths}\n"
            f"- **Weaknesses:** {a.weaknesses}\n"
            f"- **vs. original:** {a.comparison}"
            for a in content.alternative_approaches
        )
        or "_None offered._"
    )

    return f"""## Executive Summary

- **Recommendation:** {es.recommendation}
- **Why now:** {es.why_now}
- **Biggest risk:** {es.biggest_risk}
- **Success metric:** {es.success_metric}
- **Next action:** {es.next_action}

## Clarified Idea

{content.clarified_idea}

## Strategic Question

{content.strategic_question}

## Key Assumptions and Risks

### Facts
{_bullets(ka.facts)}

### Assumptions
{_bullets(ka.assumptions)}

### Speculation
{_bullets(ka.speculation)}

## Alternative Approaches

{alternatives}

## Stress Test Results

### Customer Value
{st.customer_value}

### Business Value
{st.business_value}

### Strategic Differentiation
{st.strategic_differentiation}

### Feasibility
{st.feasibility}

### Distribution
{st.distribution}

### Timing
{st.timing}

### Defensibility
{st.defensibility}

## Investment Review

### Recommendation
{ir.recommendation}

### Opportunity Cost
{ir.opportunity_cost}

### Why This Wins
{ir.why_this_wins}

## Decision Classification

### Reversible Decisions
{_bullets(dc.reversible)}

### Difficult-to-Reverse Decisions
{_bullets(dc.difficult_to_reverse)}

## MVP

{content.mvp}

## Validation Experiments

{_bullets(content.validation_experiments)}

## Success Metrics

### Leading Indicators
{_bullets(sm.leading)}

### Lagging Indicators
{_bullets(sm.lagging)}

## Kill Criteria

{_bullets(content.kill_criteria)}

## Tensions and Trade-offs

{_bullets(content.tensions)}

## Final Recommendation

### Recommendation
{fr.recommendation}

### Confidence
{fr.confidence}

### Evidence Quality
{fr.evidence_quality}

### Rationale
{fr.rationale}

### Next Actions
{_bullets(fr.next_actions)}
"""
