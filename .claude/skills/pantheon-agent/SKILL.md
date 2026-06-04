---
name: pantheon-agent
description: How to correctly add or modify a Pantheon in-app agent and/or skill (the product's OWN agent framework — not Claude Code subagents). Use when editing agents/, the AgentSkill enum, or skills/*.yaml, or when asked to add a specialist agent or skill.
paths:
  - "agents/**/*.py"
  - "core/intelligence/agent_skill_engine.py"
  - "core/models/organization.py"
  - "skills/*.yaml"
---

# Add / modify a Pantheon agent or skill

> This is about **Pantheon's own** agent framework (`agents/`, `SpecialistAgent`, `AgentSkill`),
> NOT Claude Code subagents in `.claude/agents/`. They are different layers.

Read `reference.md` in this skill for the exact `BaseAgent` contract and the skill-YAML schema.

## Add a new specialist agent

1. Create `agents/<name>_agent.py` subclassing `BaseAgent` (`agents/base.py`). Implement
   `async def run(self, task: AgentTask) -> AgentResult`. Use `safe_run()` for error handling and
   wrap your system prompt with `self.apply_skills_to_prompt(BASE_PROMPT)` to inject skill personas.
2. Generation goes through the `claude` CLI provider (`core/runtime/claude_code`); guard offline
   paths with `claude_available()` and keep the existing heuristic fallback so tests pass with
   `PANTHEON_NO_CLAUDE=1`.
3. If the agent should be routable, ensure it is constructible via `agents/agent_factory.py` and
   registered with `CapabilityRegistry`.
4. Add `tests/test_<name>_agent.py` (pytest; `tmp_path` + `monkeypatch` of `get_platform_home`).

## Add a new skill (the `AgentSkill` kind)

A skill is an **enum member + a YAML file**, loaded by `SkillLoader` (NOT a hardcoded dict):

1. Add the member to `AgentSkill` in `core/models/organization.py`, e.g.
   `SECURITY_AUDIT = "security_audit"` (value = snake_case, matches the YAML filename).
2. Create `skills/security_audit.yaml` with the schema in `reference.md`
   (`schema_version, id, name, description, persona, focus, output_hint, tags`). `id` MUST equal the
   enum value. `AgentSkillEngine` will pick it up automatically via `skill_loader`.
3. Remember: `SpecialistAgent.skills` requires **min 2, max 3** skills (Pydantic-enforced).
4. Add/extend a test that constructs a `SpecialistAgent` with the new skill and asserts the prompt
   addon appears (see existing skill tests).

## Verify

```
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/python.exe -m ruff check agents/ core/ skills/ --fix
```
