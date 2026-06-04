---
description: Scaffold a new React 19 page in the Pantheon frontend — component + route + API call + co-located vitest test — following existing page conventions.
argument-hint: "[PageName] [route]   e.g. Metrics /metrics"
---

Add a new frontend page for: **$ARGUMENTS** (PageName then route path).

Work in `web/frontend/`. Mirror an existing page in `src/pages/` (open one first to copy its
structure, imports, and test style). Stack: React 19, Vite, TS strict, Tailwind v4, Radix UI,
`react-router-dom` 7. Data via `src/lib/api.ts`; live updates via `src/hooks/useWebSocket`.

Touch all four:

1. **Page**: `src/pages/<PageName>.tsx` — a functional component, Tailwind utility classes (no inline
   styles), no `any`. If it shows backend data, fetch via a typed function in `src/lib/api.ts`.
2. **Route**: register `<route>` → `<PageName>` in `src/App.tsx` (and any nav/menu component).
3. **API** (if needed): add a typed `fetch`/client function in `src/lib/api.ts`. If a backend
   endpoint is missing, use the `fastapi-endpoint` skill to add it (keep `web/server.py` 404 intact).
4. **Test**: `src/pages/__tests__/<PageName>.test.tsx` (vitest + `@testing-library/react`), mirroring
   a neighbor's test — render, assert key UI, mock the api module.

Verify (from `web/frontend/`):
```
npm test           # vitest run
npm run build      # tsc -b && vite build  (the TS type-check gate — keep it green)
```
There is no ESLint; the build is the type-check. Do not touch backend Python beyond api.ts needs.
