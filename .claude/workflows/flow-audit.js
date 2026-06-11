export const meta = {
  name: 'flow-audit',
  description: 'Audit every Pantheon usage flow against the Atlas catalog: verify each flow in parallel (run its tests, check its known issues), then roll up honest health.',
  whenToUse: 'When you want a comprehensive, parallel health check of all usage flows — e.g. before a release, or after broad changes, to confirm which flows are solid/partial/fragile and whether flows.json status needs updating.',
  phases: [
    { title: 'Load catalog', detail: 'read core/atlas/data/flows.json' },
    { title: 'Audit flows', detail: 'one auditor per flow: run its verification tests + check its known issues' },
    { title: 'Roll up', detail: 'aggregate honest per-flow status and flag flows.json drift' },
  ],
}

const CATALOG_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['flows'],
  properties: {
    flows: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['id', 'name', 'status'],
        properties: {
          id: { type: 'string' },
          name: { type: 'string' },
          status: { type: 'string' },
          verification: { type: 'array', items: { type: 'string' } },
          known_issue_count: { type: 'number' },
        },
      },
    },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['id', 'status', 'verification_result', 'issues_remaining', 'next_step'],
  properties: {
    id: { type: 'string' },
    status: { type: 'string', enum: ['solid', 'partial', 'fragile', 'unknown'] },
    verification_result: { type: 'string', enum: ['pass', 'fail', 'skipped', 'unknown'] },
    issues_remaining: { type: 'number' },
    next_step: { type: 'string' },
    notes: { type: 'string' },
  },
}

phase('Load catalog')
const catalog = await agent(
  'Read core/atlas/data/flows.json in the Pantheon repo and return its flows. For each flow include id, name, status, the verification test files (array), and known_issue_count (length of known_issues). Return ONLY the structured object.',
  { label: 'load:flows', phase: 'Load catalog', schema: CATALOG_SCHEMA },
)

const flows = (catalog?.flows ?? []).filter((f) => (args?.id ? f.id === args.id : true))
log(`Auditing ${flows.length} flow(s)`)

phase('Audit flows')
const verdicts = (
  await parallel(
    flows.map((flow) => () =>
      agent(
        `You are auditing ONE Pantheon usage flow end-to-end.\n\nFlow: ${flow.id} — ${flow.name}\nDocumented status: ${flow.status}\nVerification tests: ${JSON.stringify(flow.verification ?? [])}\nKnown issues recorded: ${flow.known_issue_count ?? 0}\n\nSteps:\n1. Run the verification tests with the venv: .venv/Scripts/python.exe -m pytest <files> -q (Bash, forward slashes). Treat the 2 known pre-existing Windows failures (chmod 0o600) as NOT regressions; anything else is real.\n2. Read core/atlas/data/flows.json for THIS flow's known_issues, open each cited file, and judge whether it is still present or already fixed (cite file:line). Do not guess — read the code.\n3. Decide an honest status: solid (tests pass, no issue left), partial (works but a medium issue remains), fragile (a high issue remains or tests fail).\nReturn ONLY the structured verdict.`,
        { label: `audit:${flow.id}`, phase: 'Audit flows', schema: VERDICT_SCHEMA },
      ),
    ),
  )
).filter(Boolean)

phase('Roll up')
const byStatus = { solid: 0, partial: 0, fragile: 0, unknown: 0 }
const drift = []
for (const v of verdicts) {
  byStatus[v.status] = (byStatus[v.status] ?? 0) + 1
  const documented = flows.find((f) => f.id === v.id)?.status
  if (documented && documented !== v.status) drift.push({ id: v.id, documented, actual: v.status })
}
log(`Health: ${byStatus.solid} solid / ${byStatus.partial} partial / ${byStatus.fragile} fragile`)
if (drift.length) log(`flows.json status drift on ${drift.length} flow(s): ${drift.map((d) => d.id).join(', ')}`)

return { audited: verdicts.length, byStatus, drift, verdicts }
