# Engineering integrity — NO quick fixes, NO facade UI

**NON-NEGOTIABLE.** Two failure modes are prohibited outright in Pantheon, for **every**
contributor — Claude Code, Copilot, any other AI agent, and humans alike:

1. **その場しのぎ (quick fixes / band-aids)** — silencing a symptom instead of fixing the cause.
2. **見かけだけの UI (facade UI)** — surfacing something that *looks* done/working but isn't.

Both deceive the user. This rule generalizes the same honesty principle behind
`revenue-integrity.md` (never fake monetization) to **all** code and UI. When the two rules
overlap (e.g. fake revenue on screen), both apply.

## A. Fix root causes — never paper over (その場しのぎ禁止)

When something fails — a test, a build, a runtime error, a flaky check — diagnose the **root
cause in real code** and fix *that*. The following are prohibited:

- **Bypassing gates/hooks**: `--no-test` to skip the merge test gate, `git commit --no-verify`,
  `--no-gpg-sign`, disabling the auto-commit or PreToolUse guards, or editing a gate/threshold so
  it stops failing. (CLAUDE.md already forbids `--no-verify`; this makes the intent absolute and
  repo-wide.) If a hook fails, fix the underlying issue.
- **Silencing failures**: adding `pytest.skip` / `xfail` / `@skipif`, commenting out an assertion,
  loosening a test "to make it green", or wrapping a failing path in `try/except: pass`.
  - The ONLY legitimate `skipif` is a **documented, genuine platform incompatibility**
    (e.g. the two chmod-0o600 tests that no-op on Windows). **Never skip to hide a flake — root-fix
    it.** (See the cp932 decode flake fixed in commit `b3b453d`: diagnosed and fixed at the source,
    not skipped, even though it was masking under a commit-recency gate.)
- **Masking instead of fixing**: blanket `try/except`, retry loops, `sleep()`, or hardcoded values
  used to slip past an error whose cause you do not yet understand.
- **"とりあえず動く" commits**: if you cannot explain *why* it now works, you have not fixed it.
  Keep digging, or escalate to the user — do not commit a guess.
- **Trading one correctness for another**: a workaround must not break a known-good behavior
  (do not break full-suite collection, the explicit 404 handling in `web/server.py`, etc.).

If you genuinely cannot root-fix within scope or time, **do not paper over it** — report it
honestly as 未完 / known issue and hand the decision to the user. Never hide it behind a green check.

## B. UI must be real — never a facade (見かけだけの UI 禁止)

Every UI element you ship must do what it appears to do, backed by a real, working path
(component → API → backend → state). The following are prohibited:

- **Dead controls**: buttons, links, or forms that are unwired or do nothing when used.
- **Unbacked UI presented as done**: a page or feature whose backend is not connected, shipped as
  if it works. (Cf. the publishing layer — WordPress/auto paths are *labeled* Phase 2, not faked.)
- **Fake / mock / seed data to look alive**: never populate UI with invented numbers to imply the
  product is working or monetized (same root cause as `revenue-integrity.md`).
- **Broken promises**: if UI copy says "shows X", actually render X. A lede or heading that
  promises a metric with nothing rendered is a defect, not a feature.

When part of a feature is not connected yet, **do not hide it — label it honestly**
(「未接続」「Phase 2」「概算 / 予測」「確定データなし」) so the user can tell real from pending.
Showing something as present when it is absent is the worst outcome — say what is missing
(cf. `NO_CONFIRMED_REVENUE_WARNING`, and silent-drop observability).

## How to comply

- **Hit a failure?** Reproduce → prove the root cause in real code → apply the minimal *real* fix →
  verify. Not a workaround, not a skip.
- **Adding UI?** Wire it end-to-end first. For any leg that is unfinished, ship an explicit label,
  not a stub that pretends.
- **Can't finish?** Report honestly and let the user decide. Honesty over the appearance of done.

Related rules: `revenue-integrity.md`. This is the general form of the recurring honesty fixes in
this repo (promised-metric surfacing, silent-drop observability, the publishing-layer honesty pass).
