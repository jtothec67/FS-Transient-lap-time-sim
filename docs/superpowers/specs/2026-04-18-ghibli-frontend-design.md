# LGR Sim Frontend Design — Wind Rises Theme

**Date:** 2026-04-18
**Status:** Approved
**Scope:** Replace `index.html`, `styles.css`, `app.js` with new themed frontend. No backend changes.

---

## Aesthetic Direction

Theme: engineering document / aerodynamic specification sheet, inspired by "The Wind Rises" (Studio Ghibli). Clean, structured, paper-like. Feels like a printed technical spec sheet a Formula Student aero engineer would carry.

Rules:
- No gradients anywhere in the UI
- No purple
- No stock or default icons
- No animation unless explicitly requested later
- Monospace typography throughout (Courier New)
- Graph/chart colors use charting library defaults — the palette is for website chrome only

---

## Color Palette

| Token | Hex | Role |
|---|---|---|
| Green | `#006B5C` | Primary actions, active labels, field borders on focus |
| Red | `#C1122F` | Active tab top-border stripe, accent markers |
| Carbon black | `#101215` | Body text, output terminal background |
| Silver | `#A7AEB6` | Secondary text, dividers, tab border |
| Off-white | `#F4F6F8` | Page background, active tab background |
| Light surface | `#E8ECF0` | Inactive tab backgrounds, card/panel surfaces |

---

## Typography

- Font stack: `'Courier New', Courier, monospace`
- Labels: `font-size: 0.7rem; letter-spacing: 2px; text-transform: uppercase; color: #006B5C`
- Body text: `font-size: 0.85rem; color: #101215`
- Secondary/meta: `font-size: 0.75rem; color: #A7AEB6`
- Output terminal text: `color: #A7AEB6` on `background: #101215`

---

## Page Structure

Single HTML page. No framework. Tab switching via JS show/hide on `<section>` elements.

### Tab Bar

8 physical folder tabs at the top of the page, full width:

1. Base Simulator
2. Tyre Model Validation
3. Aerodynamics
4. Geometry
5. Performance
6. Lift and Coast
7. Lessons
8. Credits

Tab styling:
- Container: `border-bottom: 2px solid #A7AEB6`
- Active tab: `background: #F4F6F8; border-top: 2px solid #C1122F; border-left: 1px solid #A7AEB6; border-right: 1px solid #A7AEB6; border-bottom: none`
- Inactive tab: `background: #E8ECF0; border: 1px solid #A7AEB6; color: #A7AEB6`
- Tab label: uppercase, letter-spaced, monospace, `font-size: 0.7rem`

### Page Header

Slim strip above the tab bar:
- Left: `LGR LAP TIME SIMULATOR` in carbon black, bold monospace
- Right: `Formula Student · Full Track QS · F24` in silver

---

## Tab 1 — Base Simulator (Hero)

Layout A: two-column panel with chat bar below.

### Top row

Full-width page header strip (team name + subtitle).

### Main panel (two columns)

**Left — Inputs**
- Panel label: `INPUTS`
- Track path input (text, optional override)
- Mass override input (number, optional)
- Aero CoP override input (number, optional)
- RUN SIMULATION button (green background, off-white text, monospace)

**Right — Output**
- Panel label: `OUTPUT`
- Terminal-style `<pre>` output area (carbon black background, silver text)
- Min height 200px

### Chat bar (below both columns, full width)

- Single-line text input: placeholder `Ask about this result...`
- SEND button (green)
- Disabled/placeholder state — no LLM wired yet. Button is inert, input accepts text only.
- Border top: `1px solid #A7AEB6` to separate from the panels above

---

## Tabs 2-8 — Scaffold Only

Each tab section contains:
- Section header: tab name in large monospace, carbon black
- Subtitle in silver: `In development — content coming soon.`
- Empty `<div class="tab-content-body">` for future content

User will define content for each tab properly when it comes to it. No placeholder sim controls or fake data.

---

## Files Changed

| File | Change |
|---|---|
| `src/app/static/index.html` | Full rewrite — new tab structure, new layout |
| `src/app/static/styles.css` | Full rewrite — new palette, no gradients, monospace |
| `src/app/static/app.js` | Update tab switching logic, preserve existing API calls |
| `CLAUDE.md` | Add Wind Rises theme rules, no-gradient/purple/icon rules |

No changes to any backend file.

---

## CLAUDE.md Additions

Add to Design Direction section:

```
Theme is inspired by "The Wind Rises" (Studio Ghibli) — engineering document aesthetic.
Folder tabs at the top serve as the main navigation.
No gradients anywhere.
No purple.
No stock or default icons.
Graph and chart colors use charting library defaults. The color palette is for website chrome only.
```

---

## Launch

After implementation, launch with:

```powershell
.\tools\app\launch_sim_bt.ps1 -Port 3005
```

---

## Out of Scope

- LLM chat wiring (placeholder only)
- Content for tabs 2-8 (scaffold only)
- Any backend changes
- Responsive/mobile layout
