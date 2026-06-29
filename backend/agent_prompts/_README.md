# Agent definitions

Each `*.agent.md` file defines one agent on the Product Strategy Council. The app reads
this folder at startup (`app/agents/loader.py`) and builds an isolated pydantic-ai agent
per file — so **editing a file changes an agent; no code change required**.

## File format

YAML frontmatter + a Markdown body (the role's system prompt):

```markdown
---
key: investor                 # stable unique id
name: The Investor            # display name in the chat
role: council_member          # council_member | chairman  (exactly one chairman)
phase: deliberation           # deliberation (Phase A) | synthesis (Phase B)
default_provider: anthropic   # overridable per-user in the UI
default_model: claude-sonnet-4-6
temperature: 0.3
order: 8                      # ordering among members
owned_sections: [investment_review]   # Output-Format sections this member drives
output_schema: CouncilContribution    # members; chairman uses CouncilReportContent
---

<the role's instructions — its system prompt body>
```

`_charter.md` is **not** an agent; its contents (council intro + Context Usage +
Guidelines) are prepended to every agent's system prompt.

## Pipeline

1. **Phase A — deliberation**: all `council_member` agents run concurrently, each isolated,
   each returning a `CouncilContribution`.
2. **Phase B — synthesis**: the single `chairman` agent receives the structured
   contributions and produces the full Output Format report.
