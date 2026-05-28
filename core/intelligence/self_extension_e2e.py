"""
SelfExtensionE2ECycle — 自律的自己拡張E2Eサイクル確認 (L-14)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class E2ECycleResult:
    gap_detected: bool
    design_generated: bool
    code_generated: bool
    tests_passed: bool
    proposal_created: bool
    summary: str


class SelfExtensionE2ECycle:
    """Coordinate a self-extension cycle end to end."""

    def __init__(self, gap_analyzer=None, tool_design_agent=None, code_writer=None, tester=None):
        self.gap_analyzer = gap_analyzer
        self.tool_design_agent = tool_design_agent
        self.code_writer = code_writer
        self.tester = tester

    def run_cycle(self, **_kwargs) -> E2ECycleResult:
        gaps = self.gap_analyzer.analyze() if self.gap_analyzer else []
        if not gaps:
            return E2ECycleResult(False, False, False, False, False, "No capability gaps detected.")

        gap = gaps[0]
        spec = self.tool_design_agent.design(gap) if self.tool_design_agent else None
        code_output = self.code_writer.write_code(spec) if (self.code_writer and spec) else None

        if self.tester and code_output:
            if hasattr(self.tester, "run_full_validation"):
                validation = self.tester.run_full_validation(code_output, None)
                tests_passed = bool(getattr(validation, "overall_pass", False))
            elif callable(self.tester):
                tests_passed = bool(self.tester(code_output))
            else:
                tests_passed = False
        else:
            tests_passed = False

        proposal_created = bool(spec and code_output and tests_passed)
        summary = (
            f"gap_detected={bool(gaps)}, design_generated={bool(spec)}, code_generated={bool(code_output)}, "
            f"tests_passed={tests_passed}, proposal_created={proposal_created}"
        )
        return E2ECycleResult(
            gap_detected=True,
            design_generated=bool(spec),
            code_generated=bool(code_output),
            tests_passed=tests_passed,
            proposal_created=proposal_created,
            summary=summary,
        )
