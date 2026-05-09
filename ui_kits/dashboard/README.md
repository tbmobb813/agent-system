# Dashboard UI Kit

Recreates the Next.js dashboard at `frontend-dashboard/web/` from the
`tbmobb813/agent-system` repo as a click-thru prototype. The kit covers the
three screens that carry the visual system end-to-end and stubs the rest as
empty panels.

## Files

| File | What's in it |
|---|---|
| `index.html`     | Hash-routed app shell. Loads React + Babel, mounts `<App>`, provides theme switcher. |
| `data.js`        | Mock recent tasks, model breakdown, budget, nav cards, canned SSE stream. |
| `Components.jsx` | Primitives: `Panel`, `Eyebrow`, `SectionTitle`, `Chip`, `ButtonAccent`, `ButtonGhost`, `NavLink`, `StatusDot`, `StatusText`, `Code`. |
| `AppShell.jsx`   | Header (brand mark + nav + theme select + operator avatar) and footer. |
| `Dashboard.jsx`  | Hero greeting, status pills, budget meter, model split, recent tasks, nav cards. |
| `AgentView.jsx`  | Composer + streaming output. Click **Run** to replay the canned trace. |
| `HistoryView.jsx`| Filterable table of past runs (query text + status pills). |

## Source mapping

The visual mapping back to the codebase:

- `app/page.tsx` (homepage) → `Dashboard.jsx`
- `app/agent/page.tsx` (agent runner) → `AgentView.jsx`
- `app/history/page.tsx` (run log) → `HistoryView.jsx`
- `app/globals.css` tokens (`--accent`, `--surface`, etc.) → `colors_and_type.css`
- `cost_router.py` model tiers → cost-router order shown in the model split panel.

## Things to know

- **No backend.** The streaming view replays a fixed event sequence from
  `data.js`. Switch models in the dropdown, but the canned response stays the
  same.
- **Theme switcher works.** Pick Starforge / Retro Grid / Clean Tech to see the
  same surfaces under each palette.
- **Hash routing.** `#/agent`, `#/history`, etc. — every nav link, card, and
  button uses the same handler so the back button works.
- **Empty placeholders are intentional.** `/costs`, `/analytics`, `/documents`,
  `/settings`, `/commands` show "This screen is intentionally empty" so the kit
  doesn't pretend to be production.

## Open in isolation

The kit reads `colors_and_type.css` from the project root and the brand glyph
from `assets/`. Keep those at the same relative paths if you copy this kit
elsewhere.
