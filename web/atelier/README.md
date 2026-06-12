# Pantheon Atelier — *The Observatory*

A clean-room, **art-forward** GUI for Pantheon, built from zero. It runs **in parallel**
to the existing `web/frontend/` (which is untouched) and talks to the **same FastAPI
backend** on `:8000` — no new endpoints, just a new way of seeing.

> Concept: your self-growing AI organizations form a living **constellation**. Health
> becomes brightness, agent count becomes size, running sessions become a pulse. The
> language is a museum catalogue — high-contrast serif (Fraunces), hairline rules,
> exhibition plates, two themes (**Nocturne** ink / **Daylight** paper), gold-leaf as the
> brand accent and ice as the live-data accent.

## Screens

| № | Route | Name | What it is |
|---|-------|------|------------|
| 01 | `/` | **Observatory** | The signature **Firmament** canvas (orgs × live sessions × handoffs) + headline figures + live transmissions + daemon/governor systems. |
| 02 | `/pantheon` | **Pantheon** | Organizations as a catalogue of plates, each with a deterministic constellation **sigil**, health/autonomy meters, agents & pending counts. |
| 03 | `/atelier` | **Atelier** | Design styles as **palette specimens** + personas as voices — "wear any aesthetic, any voice". |
| 04 | `/signals` | **Signals** | Collected trends as a scored broadsheet, with *collect now* / *convert to proposals*. |
| 05 | `/inbox` | **Inbox** | The review desk — approve/reject improvement proposals (across all orgs) and cross-org handoffs. |
| 06 | `/handbook` | **Handbook** | The monetization operating manual — WEB flow vs CLI flow (toggle), the end-to-end flywheel, approval gates, the "draft factory → manual publish" reality, and 24h-autonomy tips. Source-verified. |

## Run it

The backend must be running first:

```powershell
pantheon serve --port 8000
```

Then, from `web/atelier/`:

```powershell
npm install        # first time only
npm run dev        # → http://localhost:5273  (proxies /api + /ws to :8000)
```

Other scripts:

```powershell
npm run build      # tsc --noEmit + vite build → web/atelier/dist (its OWN folder; never touches web/dist)
npm test           # vitest (smoke + unit)
npm run preview    # serve the production build locally
```

## Design system

- **Tokens & themes** live in [`src/styles/theme.css`](src/styles/theme.css) as CSS custom
  properties under `[data-theme="nocturne"]` / `[data-theme="daylight"]`. Toggle via the
  masthead sun/moon; the choice persists in `localStorage` (`atelier-theme`).
- **Type**: `Fraunces` variable serif (display/numerals) + `Inter` variable (body) +
  system mono (catalogue numbers/IDs), all self-hosted via `@fontsource-variable/*`
  (offline-friendly — no Google Fonts request).
- **Icons & sigils** are hand-drawn inline SVG ([`Icon.tsx`](src/components/Icon.tsx),
  [`Sigil.tsx`](src/components/Sigil.tsx)) — zero icon-font dependency, on-brand.
- **Motion** respects `prefers-reduced-motion` (the Firmament renders a single static
  frame; all transitions collapse).

## How it stays isolated

- Separate npm project, separate `node_modules`, separate `dist/`. Dev port is **5273**
  (legacy is 5173), so both can run side by side.
- Uses the same API contract and the same `pantheon_api_token` localStorage key, so if you
  set `PANTHEON_API_TOKEN` on the backend, opening `…/?token=xxx` once authorizes both GUIs.
- The backend still serves the **legacy** build from `web/dist` by default. Atelier is opt-in:
  `pantheon serve --ui atelier` (or `PANTHEON_UI=atelier`) serves `web/atelier/dist` at the
  root instead — build it first (`cd web/atelier && npm run build`); if the build is missing
  the server warns and falls back to legacy. The dev-server route (port 5273 proxying :8000)
  also still works. Nothing about the existing GUI changes.

## Status (iteration 1)

A complete vertical slice: the design language + the five highest-value screens, wired to
real data. Not yet a 1:1 port of every legacy page (sessions detail, knowledge editor,
settings, etc.) — those are deliberately deferred so the art direction could land first.
