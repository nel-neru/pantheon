---
name: Diagram first
description: Lead architecture/flow explanations with a Mermaid diagram, then concise prose. Good for onboarding and design discussions.
keep-coding-instructions: true
---

When explaining Pantheon's architecture, a data/control flow, a request path, or how subsystems
relate, **start with a Mermaid diagram** (```mermaid block), then add concise prose underneath.

- Prefer `flowchart`/`sequenceDiagram`/`classDiagram` as fits.
- Keep node labels short; put detail in the prose below.
- For code-level answers (a specific bug, a one-line fix, a command), skip the diagram and answer
  directly — diagrams are for structure, not trivia.
- Keep the existing coding rules and conventions in force (this style only changes how you explain).
