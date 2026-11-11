# ATLAS-Style Telemetry Visualisation

**Date:** 2026-04-19
**Branch:** dev/bt/web-app

## Goal

Replace the plain JSON output panel on the base simulator page with an ATLAS-inspired data visualisation workspace. Engineers see lap summary stats, stacked telemetry channel panes, and a G-G diagram after every run. The architecture is designed to scale to future tabs, channels, and multi-run overlay without structural rewrites.

## Layout

The right side of the base simulator page becomes a viz workspace with three zones:

**Summary strip** — full-width bar at the top. Shows lap time, max lat g, max long g, track name, run status badge, and a CSV download button. The download button is disabled until a run completes.

**Channel list sidebar** — narrow panel on the left of the chart area. Lists all channels from the registry, grouped by type (Speed, G-Forces, etc.). Each channel has a colour dot, name, and unit. Clicking a channel toggles it on or off. Active channels are full brightness; inactive channels are dimmed.

**Chart area** — fills the remaining space. A tab strip at the top drives which view is shown. Initially two tabs: Telemetry and G-G Diagram. Each tab is an entry in `VIZ_TABS` — adding a future tab (Track Map, Limiting Mode, etc.) is one array entry plus a render function.

The Telemetry tab shows stacked horizontal panes, one per active channel, all sharing the same distance X axis. The Speed pane gets more vertical space than G-force panes. Each pane has a colour-coded header with a live cursor readout. A shared vertical cursor line moves across all panes on hover.

The G-G tab shows a scatter of lat g vs long g for every track point.

## Channel Registry

A top-level constant in `app.js`:

```js
const CHANNEL_REGISTRY = {
  speeds_kmh: { label: 'Speed',  unit: 'km/h', color: '#4e9af1', group: 'Speed'    },
  g_lat:      { label: 'Lat G',  unit: 'g',    color: '#f1a24e', group: 'G-Forces' },
  g_long:     { label: 'Long G', unit: 'g',    color: '#e05d5d', group: 'G-Forces' },
}
```

Adding a channel in the future means one entry here plus a backend key. No other code changes.

## Viz Tab Registry

```js
const VIZ_TABS = [
  { key: 'telemetry', label: 'Telemetry', render: renderTelemetryTab },
  { key: 'gg',        label: 'G-G Diagram', render: renderGGTab },
]
```

Adding a tab means pushing one entry and writing a render function.

## Telemetry State

```js
let telemetryState = {
  runs: {},      // keyed by run ID, value is { meta, telemetry }
  activeRunId: null,
  activePanes: ['speeds_kmh', 'g_lat', 'g_long'],
}
```

Keyed by run ID from the start so future multi-run overlay adds a run entry without restructuring. For now only one run is stored and `activeRunId` points to it.

## Data Flow

### On Run

`run_lap` POST response gains a `telemetry` key:

```json
{
  "lap_time_s": 75.34,
  "max_abs_g_lat": 1.42,
  "max_abs_g_long": 1.18,
  "track_file_path": "datasets/tracks/FSUK.txt",
  "telemetry": {
    "distances_m": [...],
    "speeds_kmh": [...],
    "g_lat": [...],
    "g_long": [...]
  }
}
```

On success the frontend calls `storeTelemetry(data)` which writes to `telemetryState`, then calls `renderViz()` which redraws the active tab.

### CSV Download

Generated in the browser from `telemetryState` — no server round-trip. Columns: `distance_m`, then one column per channel in registry order. Filename: `lgr_lap_<track>_<laptime>s.csv`. Button is disabled until `telemetryState.activeRunId` is set.

## Backend Changes

### `lap_service.py`

`run_lap` extracts arrays from `LapTimeResults` before returning:

- `distances_m` — cumulative sum of `track.ds` (segment lengths)
- `speeds_kmh` — `results.final_speeds * 3.6`
- `g_lat` — `results.g_lat_channel`
- `g_long` — `results.g_long_channel`

Always included. Not behind a flag.

### No schema change needed

`run_lap` already returns a plain `dict`. Adding a `telemetry` key requires no Pydantic model change.

## Frontend Changes

### `app.js`

New constants: `CHANNEL_REGISTRY`, `VIZ_TABS`

New state: `telemetryState`

New functions:
- `initVizPanel()` — builds the DOM structure for summary strip, channel list, tab strip, chart area; called once on boot
- `storeTelemetry(data)` — writes run data to `telemetryState`
- `renderViz()` — calls active tab's render function
- `renderTelemetryTab()` — builds/updates stacked Chart.js line chart panes for active channels
- `renderGGTab()` — builds/updates Chart.js scatter chart
- `renderSummaryStrip(meta)` — updates lap time, g values, track name, run status
- `downloadCSV()` — generates and triggers CSV download
- `toggleChannel(key)` — updates `activePanes`, re-renders telemetry tab if active

Existing `runLap()` calls `storeTelemetry` and `renderViz` on success instead of writing to `<pre id="lapOutput">`. The `lapOutput` element is removed from the HTML.

### `index.html`

The output panel div is replaced with the viz workspace structure (summary strip, channel list, chart area). The `lapOutput` pre element is removed.

### `static/chart.js`

Chart.js minified bundle downloaded and served from `/static/chart.js`. No CDN.

### `styles.css`

New rules for: `.viz-panel`, `.summary-strip`, `.stat-item`, `.channel-list`, `.channel-item`, `.channel-item.inactive`, `.chart-area`, `.chart-pane`, `.chart-pane-header`, `.viz-tab-bar`, `.viz-tab`, `.viz-tab.active`, `.csv-btn`, `.csv-btn:disabled`

## Assumptions and Limits

- One run stored at a time. Overlay of multiple runs is not in scope.
- Channel list checkboxes toggle visibility only. Axis scale and range are automatic (Chart.js defaults).
- No zoom or pan on charts in this scope.
- G-G diagram does not overlay a theoretical friction ellipse in this scope.
- CSV includes all channels regardless of which are toggled active in the UI.
- `track.ds` is assumed to be available on the track object returned from the simulator. If not, distances are computed as equally-spaced indices.
