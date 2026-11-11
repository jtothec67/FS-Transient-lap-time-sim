# Wind Rises Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the existing flat-card UI with an engineering-document themed single-page app featuring 8 folder tabs, the confirmed LGR livery palette, and a placeholder chat bar on the Base Simulator tab.

**Architecture:** Static HTML/CSS/JS — no framework. Tab switching is pure JS show/hide on `<section>` elements. The three existing backend API calls (`/api/metadata`, `/api/lap/run`, `/api/lift-coast/run`) are preserved unchanged. Only the three frontend static files and `CLAUDE.md` are touched.

**Tech Stack:** Vanilla HTML5, CSS3, JS (ES2020), Python/FastAPI backend (unchanged)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `CLAUDE.md` | Modify | Add Wind Rises theme rules |
| `src/app/static/index.html` | Rewrite | 8-tab structure, Base Simulator layout A |
| `src/app/static/styles.css` | Rewrite | Livery palette, monospace, no gradients |
| `src/app/static/app.js` | Rewrite | Tab switching + preserved API calls |

---

## Task 1: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Open CLAUDE.md and locate the Design Direction section**

The section currently reads:
```
## Design Direction
Theme is cool, engineery, and smart.
Use clear hierarchy, compact controls, and practical data views.
Do not add animation unless explicitly requested.
```

- [ ] **Step 2: Replace the Design Direction section**

Replace that section with:
```markdown
## Design Direction
Theme is inspired by "The Wind Rises" (Studio Ghibli) — engineering document aesthetic, folder tabs as navigation, clean spec sheet structure.
Use clear hierarchy, compact controls, and practical data views.
Do not add animation unless explicitly requested.
No gradients anywhere in the UI.
No purple.
No stock or default icons — use text labels only.
Graph and chart colors use the charting library defaults. The color palette is reserved for website chrome only.
```

- [ ] **Step 3: Update the Color Palette section**

The section currently lists 6 colors including asphalt gray. Replace it with:
```markdown
## Color Palette
Use the LGR car livery as the base.

- Green primary `#006B5C`
- Red accent `#C1122F`
- Carbon black `#101215`
- Silver `#A7AEB6`
- Off white `#F4F6F8`
- Light surface `#E8ECF0` (inactive tabs, card surfaces)
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update design direction to Wind Rises theme and fix palette"
```

---

## Task 2: Rewrite styles.css

**Files:**
- Rewrite: `src/app/static/styles.css`

- [ ] **Step 1: Replace the entire file with the new stylesheet**

```css
* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: 'Courier New', Courier, monospace;
  background: #F4F6F8;
  color: #101215;
}

.page-header {
  display: flex;
  align-items: baseline;
  gap: 16px;
  padding: 10px 16px;
  background: #101215;
  border-bottom: 2px solid #006B5C;
}
.page-title {
  font-size: 0.85rem;
  font-weight: bold;
  color: #F4F6F8;
  letter-spacing: 2px;
  text-transform: uppercase;
}
.page-subtitle {
  font-size: 0.75rem;
  color: #A7AEB6;
  letter-spacing: 1px;
}

.tab-bar {
  display: flex;
  padding: 8px 16px 0;
  background: #E8ECF0;
  border-bottom: 2px solid #A7AEB6;
  overflow-x: auto;
}
.tab {
  background: #E8ECF0;
  border: 1px solid #A7AEB6;
  border-bottom: 1px solid #A7AEB6;
  padding: 5px 14px;
  font-family: 'Courier New', Courier, monospace;
  font-size: 0.7rem;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: #A7AEB6;
  cursor: pointer;
  border-radius: 3px 3px 0 0;
  margin-right: 2px;
  white-space: nowrap;
}
.tab.active {
  background: #F4F6F8;
  color: #101215;
  border-top: 2px solid #C1122F;
  border-bottom: none;
  font-weight: bold;
}
.tab:hover:not(.active) {
  color: #101215;
}

main { padding: 16px; }
.tab-section { display: none; }
.tab-section.active { display: block; }

.sim-panel {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 12px;
  margin-bottom: 12px;
}

.panel {
  background: #FFFFFF;
  border: 1px solid #A7AEB6;
  padding: 12px;
}
.panel-label {
  font-size: 0.7rem;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: #006B5C;
  font-weight: bold;
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid #E8ECF0;
}

.field-label {
  display: block;
  font-size: 0.7rem;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: #A7AEB6;
  margin-top: 8px;
  margin-bottom: 3px;
}

input[type="text"],
input[type="number"] {
  width: 100%;
  padding: 6px 8px;
  font-family: 'Courier New', Courier, monospace;
  font-size: 0.8rem;
  background: #F4F6F8;
  border: 1px solid #A7AEB6;
  color: #101215;
  outline: none;
}
input:focus { border-color: #006B5C; }

button {
  font-family: 'Courier New', Courier, monospace;
  font-size: 0.75rem;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  cursor: pointer;
  border: none;
  padding: 8px 14px;
}

#runLapBtn {
  width: 100%;
  margin-top: 14px;
  background: #006B5C;
  color: #F4F6F8;
}
#runLapBtn:hover { background: #005548; }

.output-panel { display: flex; flex-direction: column; }

pre#lapOutput {
  flex: 1;
  background: #101215;
  color: #A7AEB6;
  padding: 10px;
  font-family: 'Courier New', Courier, monospace;
  font-size: 0.8rem;
  min-height: 200px;
  overflow: auto;
  border: none;
  margin: 0;
}

.meta-row {
  padding-top: 6px;
  margin-top: 6px;
  border-top: 1px solid #E8ECF0;
}
.scope-text {
  font-size: 0.7rem;
  color: #A7AEB6;
  letter-spacing: 1px;
}

.chat-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid #A7AEB6;
  background: #FFFFFF;
  padding: 8px 10px;
}
.chat-bar input[type="text"] {
  flex: 1;
  border: none;
  background: transparent;
  padding: 0;
  font-size: 0.8rem;
}
.chat-bar input[type="text"]:focus { border: none; }
.chat-bar input[type="text"]::placeholder { color: #A7AEB6; }

#chatSend {
  background: #006B5C;
  color: #F4F6F8;
  padding: 6px 12px;
}
#chatSend:disabled {
  background: #E8ECF0;
  color: #A7AEB6;
  cursor: not-allowed;
}

.section-title {
  font-size: 1rem;
  font-weight: bold;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: #101215;
  margin-bottom: 8px;
}
.section-sub {
  font-size: 0.8rem;
  color: #A7AEB6;
}
```

- [ ] **Step 2: Commit**

```bash
git add src/app/static/styles.css
git commit -m "style: Wind Rises theme — livery palette, monospace, no gradients"
```

---

## Task 3: Rewrite index.html

**Files:**
- Rewrite: `src/app/static/index.html`

- [ ] **Step 1: Replace the entire file**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>LGR Sim Workbench</title>
  <link rel="stylesheet" href="/static/styles.css" />
</head>
<body>

  <div class="page-header">
    <span class="page-title">LGR Lap Time Simulator</span>
    <span class="page-subtitle">Formula Student · Full Track QS · F24</span>
  </div>

  <nav class="tab-bar">
    <button class="tab active" data-tab="base-sim">Base Simulator</button>
    <button class="tab" data-tab="tyre">Tyre Model</button>
    <button class="tab" data-tab="aero">Aerodynamics</button>
    <button class="tab" data-tab="geometry">Geometry</button>
    <button class="tab" data-tab="performance">Performance</button>
    <button class="tab" data-tab="lift-coast">Lift and Coast</button>
    <button class="tab" data-tab="lessons">Lessons</button>
    <button class="tab" data-tab="credits">Credits</button>
  </nav>

  <main>

    <section id="base-sim" class="tab-section active">
      <div class="sim-panel">

        <div class="panel inputs-panel">
          <div class="panel-label">Inputs</div>
          <label class="field-label">Track Path</label>
          <input id="trackPath" type="text" placeholder="datasets/tracks/FSUK.txt" />
          <label class="field-label">Mass Override (kg)</label>
          <input id="massOverride" type="number" step="0.1" placeholder="300" />
          <label class="field-label">Aero CoP Override (m)</label>
          <input id="aeroCpOverride" type="number" step="0.01" placeholder="1.0" />
          <button id="runLapBtn">Run Simulation</button>
        </div>

        <div class="panel output-panel">
          <div class="panel-label">Output</div>
          <pre id="lapOutput"></pre>
          <div class="meta-row">
            <span class="scope-text" id="scope"></span>
          </div>
        </div>

      </div>
      <div class="chat-bar">
        <input type="text" id="chatInput" placeholder="Ask about this result..." />
        <button id="chatSend" disabled>Send</button>
      </div>
    </section>

    <section id="tyre" class="tab-section">
      <h2 class="section-title">Tyre Model Validation</h2>
      <p class="section-sub">In development.</p>
    </section>

    <section id="aero" class="tab-section">
      <h2 class="section-title">Aerodynamics</h2>
      <p class="section-sub">In development.</p>
    </section>

    <section id="geometry" class="tab-section">
      <h2 class="section-title">Geometry</h2>
      <p class="section-sub">In development.</p>
    </section>

    <section id="performance" class="tab-section">
      <h2 class="section-title">Performance</h2>
      <p class="section-sub">In development.</p>
    </section>

    <section id="lift-coast" class="tab-section">
      <h2 class="section-title">Lift and Coast</h2>
      <p class="section-sub">In development.</p>
    </section>

    <section id="lessons" class="tab-section">
      <h2 class="section-title">Lessons</h2>
      <p class="section-sub">In development.</p>
    </section>

    <section id="credits" class="tab-section">
      <h2 class="section-title">Credits</h2>
      <p class="section-sub">In development.</p>
    </section>

  </main>

  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add src/app/static/index.html
git commit -m "feat: 8-tab folder structure with Wind Rises layout"
```

---

## Task 4: Rewrite app.js

**Files:**
- Rewrite: `src/app/static/app.js`

- [ ] **Step 1: Replace the entire file**

```js
function initTabs() {
  const tabs = document.querySelectorAll('.tab');
  const sections = document.querySelectorAll('.tab-section');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      sections.forEach(s => s.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById(tab.dataset.tab).classList.add('active');
    });
  });
}

function parseNumber(value) {
  if (value === null || value === undefined || value === '') return null;
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

async function loadMetadata() {
  const res = await fetch('/api/metadata');
  const data = await res.json();
  document.getElementById('scope').textContent = data.model_scope ?? '';
}

async function runLap() {
  const trackPath = document.getElementById('trackPath').value.trim();
  const mass = parseNumber(document.getElementById('massOverride').value);
  const aeroCp = parseNumber(document.getElementById('aeroCpOverride').value);

  const parameter_overrides = {};
  if (mass !== null) parameter_overrides.mass = mass;
  if (aeroCp !== null) parameter_overrides.aero_cp = aeroCp;

  const out = document.getElementById('lapOutput');
  out.textContent = 'Running...';

  const res = await fetch('/api/lap/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ parameter_overrides, track_file_path: trackPath || null }),
  });
  const data = await res.json();
  out.textContent = JSON.stringify(data, null, 2);
}

document.getElementById('runLapBtn').addEventListener('click', runLap);

initTabs();
loadMetadata();
```

- [ ] **Step 2: Commit**

```bash
git add src/app/static/app.js
git commit -m "feat: tab switching and trimmed app.js — lift-coast moved to scaffold"
```

---

## Task 5: Launch and Verify

**Files:** None modified

- [ ] **Step 1: Launch the app on port 3005**

```powershell
.\tools\app\launch_sim_bt.ps1 -Port 3005
```

Expected: terminal prints `Launching LGR Sim Workbench on http://127.0.0.1:3005`

- [ ] **Step 2: Open http://127.0.0.1:3005 and verify the following**

Tab bar checks:
- 8 tabs visible across the top
- Active tab (Base Simulator) has a red top border stripe and white background
- Inactive tabs have light surface background and silver text
- Clicking any tab switches the visible section and updates the active state

Base Simulator checks:
- Two-column layout: inputs left (fixed 280px), output right (fills remaining)
- All three inputs render (Track Path, Mass Override, Aero CoP)
- Run Simulation button is green
- Output `<pre>` area is carbon black with silver text
- Scope text appears in the meta row below output
- Chat bar spans the full width below both panels with a disabled Send button

Scaffold tab checks:
- Each of the 7 non-active tabs shows only its title and "In development." in silver

Style checks:
- No gradients anywhere
- No purple
- All text is monospace (Courier New)
- Page header is carbon black with green bottom border

- [ ] **Step 3: Run a lap to verify the API call still works**

Enter no overrides, click Run Simulation.
Expected: `lapOutput` shows JSON response from `/api/lap/run` (same format as before).

- [ ] **Step 4: Commit verification note (optional)**

```bash
git commit --allow-empty -m "chore: verified Wind Rises frontend on port 3005"
```
