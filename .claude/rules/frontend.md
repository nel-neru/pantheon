---
description: React 19 / Vite / TypeScript / Tailwind v4 conventions for the Pantheon web frontend
paths:
  - "web/frontend/**/*.{ts,tsx}"
---

# Frontend conventions (`web/frontend/`)

Stack: **React 19**, **Vite 6**, **TypeScript 5.7 (strict)**, **Tailwind v4** (`@tailwindcss/vite`),
**Radix UI** primitives, `react-router-dom` 7, `recharts`, `sonner`, `lucide-react`.

- Functional components + hooks only; follow React 19 hook rules (no conditional hooks, correct deps).
- TypeScript **strict** — no `any`; type props and API payloads explicitly.
- **There is no ESLint** — type-checking happens via `tsc -b` during `npm run build`. Run a build to type-check.
- Styling: **Tailwind utility classes**, no inline `style={{}}`; use Radix primitives for dialogs/menus/etc.
- Import alias `@` → `./src` (configured in `vite.config.ts` / `tsconfig.json`).
- Data: call the backend through `src/lib/api.ts`; live updates via `src/hooks/useWebSocket`. Dev server proxies `/api` and `/ws` to `http://localhost:8000`.

## Tests (vitest, co-located)

- Each page in `src/pages/X.tsx` has a co-located test `src/pages/__tests__/X.test.tsx` (vitest + `@testing-library/react`, jsdom; setup `src/test/setup.ts`).
- Run from `web/frontend/`: `npm test` (= `vitest run`; do NOT append `-- run`). Watch: `npm run test:watch`.
- When you add a page, add its route in `src/App.tsx`, its API call in `src/lib/api.ts`, and a co-located test. (`/add-web-page` scaffolds this.)

## Build

`npm run build` = `tsc -b && vite build` → outputs to `web/dist` (served by FastAPI). Keep the build green.
