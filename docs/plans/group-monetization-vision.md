# Pantheon Group Structure & Monetization Vision

**Status**: High-level enduring vision. This document focuses on the conceptual model and long-term direction. Current implementation details live separately in the plans/ area and are expected to evolve or be archived.

## Core Idea

Pantheon (via the Meta-Improvement Organization + Platform) acts as a **headquarters / meta-organization** that designs, strengthens, and continuously evolves multiple purpose-driven child Organizations — including revenue-focused ones (affiliate marketing operations, SNS account growth, Note/content sales, etc.).

Child organizations specialize in their domain. The HQ focuses on:
- Organizational design and evolution
- Capability and skill development
- Cross-org learning and pattern propagation
- Self-improvement of the overall system and tooling

This creates a recursive flywheel: better HQ capabilities → better child orgs and automation tools → real-world outcomes and feedback → even stronger HQ and platform.

## Guiding Principles

1. **Trust substrate first** — Ambitious group or monetization work should be built on a trustworthy self-improving foundation (consistent policy, learning loops, safe execution, etc.).

2. **HQ strengthens designs and substrate, not (initially) executes revenue actions** — Primary value comes from improving org structures, workflows, prompts, tools, and automation used by revenue orgs, rather than direct control of external accounts or publishing.

3. **Recursive flywheel over flat multi-org** — Real compounding comes from the HQ layer actively diagnosing, intervening in, and evolving child organizations over time.

4. **Generalize the core improvement contract** — Extend existing patterns for proposal-driven change, policy gates, and learning (analyze → proposal → policy → execution + feedback) rather than creating parallel mechanisms.

5. **Safety and auditability remain non-negotiable**.

6. **State and artifacts discipline** — Respect established locations for different kinds of artifacts (global platform state, per-org state, transient planning in dedicated areas).

## Enduring Architectural Grounding

- PlatformStateManager as the central point for managing multiple child Organizations.
- Meta-Improvement Organization as the dedicated self-evolving core (inspired by corporate HQ functions for org evolution, knowledge sharing, performance optimization, etc.).
- GroupHQState and cross-org collaboration primitives as existing seeds for HQ-level oversight.
- The core improvement machinery (proposals, policy engine, PreTask orchestration, skill/YAML system, GenericSkillAgent) as the reusable substrate for all organizations.

This vision is intended to be relatively stable over time. Specific phased work, current tasks, hygiene rules for ongoing efforts, and detailed implementation steps are kept in the plans/ area so they can be cleaned up or archived once complete, without polluting the design-level vision.