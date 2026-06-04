# Pantheon Web — dashboard wireframes (reference)

Low-fidelity wireframes for the AI-operation dashboard + work board (stack: React 19 / Vite / Tailwind
v4 / Radix / recharts / react-router 7). These are a **design reference**, not a spec — confirm
against the live pages in `web/frontend/src/pages/` before implementing. Data via `src/lib/api.ts`
(`/api`), live updates via `useWebSocket` (`/ws`).

## Shell (layout)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ☰  Pantheon            [ search ⌘K ]                 ● live   ⚙  ?  ◐ theme │
├──────────┬───────────────────────────────────────────────────────────────┤
│ Overview │                                                                 │
│ Sessions │   < page content >                                              │
│ Agents   │                                                                 │
│ Proposals│                                                                 │
│ Work board                                                                 │
│ Orgs     │                                                                 │
│ Settings │                                                                 │
└──────────┴───────────────────────────────────────────────────────────────┘
  ● live = WebSocket status (sonner toast on disconnect/reconnect)
```

## Overview (operation dashboard)

```
┌ Overview ──────────────────────────────────────────────────────────────────┐
│ ┌ Health ─────┐ ┌ Active agents ┐ ┌ Proposals ──┐ ┌ Velocity ───┐           │
│ │   82 / 100  │ │      3 ▶       │ │ 7 pending   │ │  ▁▃▅▇▆ +12%  │           │
│ │  ▲ +4 (7d)  │ │   1 ⏸ awaiting │ │ 2 awaiting  │ │             │           │
│ └─────────────┘ └───────────────┘ └─────────────┘ └─────────────┘           │
│ ┌ Live activity (ws) ───────────────────────┐ ┌ Org health (recharts) ────┐ │
│ │ 12:03 code-review · MyApp · proposal #34   │ │  ╭─╮   radial / line       │ │
│ │ 12:01 executor   · MyApp · branch work/..  │ │  ╰─╯   per-org score        │ │
│ │ 11:58 analyze    · Shop  · 5 findings      │ │                            │ │
│ └────────────────────────────────────────────┘ └────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Sessions (agent runs; ties to wmux "1 workspace/agent")

```
┌ Sessions ───────────────────────────────────────────────────────────────────┐
│ [ + New session ]                            filter: ▾ all  ▾ org   🔄        │
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │ ● running  · sess-7a · MyApp · code-review     · 00:42 · 18k tok · [open] │ │
│ │ ⏸ awaiting · sess-7b · MyApp · executor        · needs approval  · [open] │ │
│ │ ✓ done     · sess-6f · Shop  · analyze         · 5 proposals     · [open] │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│ Detail (drawer): live terminal/log tail · agent + skills · token/cost · stop  │
└───────────────────────────────────────────────────────────────────────────────┘
```

## Proposals (Human-in-the-Loop approval)

```
┌ Proposals · MyApp ────────────────────────────────────────────────────────────┐
│ tabs:  ▣ Pending(7)  Approved(3)  Rejected(2)  Done(11)        bulk: [approve…] │
│ ┌────────────────────────────────────────────────────────────────────────────┐│
│ │ #34  🔴 high   security   "Validate query filter input"   src/app.py         ││
│ │      impact: prevents injection · difficulty: medium      [view] [✓] [✗]     ││
│ │ #33  🟡 med    perf       "Cache org health computation"  core/metrics/..    ││
│ └────────────────────────────────────────────────────────────────────────────┘│
│ View (modal): description · diff preview · policy decision · → apply (branch/PR)│
└────────────────────────────────────────────────────────────────────────────────┘
```

## Work board (external task board / kanban)

```
┌ Work board ───────────────────────────────────────────────────────────────────┐
│  Backlog            In progress          Awaiting review        Done            │
│ ┌───────────┐      ┌───────────┐        ┌───────────┐         ┌───────────┐     │
│ │ goal: ECサイト│   │ #34 sec fix │       │ #29 refactor│        │ #11 docs  │     │
│ │ analyze Shop │    │ (executor)  │       │ (PR open)   │        │ #08 tests │     │
│ └───────────┘      └───────────┘        └───────────┘         └───────────┘     │
│  drag to move · card = proposal/goal/session · WS keeps columns live            │
└────────────────────────────────────────────────────────────────────────────────┘
```

## States to design for every view
- **loading** (skeletons), **empty** ("no sessions yet — start one"), **error** (retry + toast),
  **disconnected** (WS down banner). Keep Tailwind utility classes; use Radix for dialogs/menus/toasts.
```
[ empty ]                         [ error ]
  ╭──────────────────────╮          ⚠ Couldn't load proposals
  │  Nothing here yet.    │          [ Retry ]   (sonner toast)
  │  [ Start a session ]  │
  ╰──────────────────────╯
```
