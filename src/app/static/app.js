const CHANNEL_REGISTRY = {
  speeds_kmh:          { label: 'Speed',             unit: 'km/h', color: '#4e9af1', group: 'Speed',       flex: 2,
    tip: 'Vehicle speed along the track, in km/h. Always non-negative.' },
  g_lat:               { label: 'Lat G',             unit: 'g',    color: '#f1a24e', group: 'G-Forces',    flex: 1,
    tip: 'Lateral acceleration, in g. Sign follows the local track curvature. Positive in a left-hand turn, negative in a right-hand turn. Computed from quasi-static equilibrium. Transient yaw response and counter-steer lag are not modelled.' },
  g_long:              { label: 'Long G',            unit: 'g',    color: '#e05d5d', group: 'G-Forces',    flex: 1,
    tip: 'Longitudinal acceleration, in g. Positive when accelerating along the track direction, negative when braking. Magnitudes under braking usually exceed magnitudes under acceleration because braking is tyre-limited while acceleration is power-limited.' },
  mu_util:             { label: 'Mu Utilisation',    unit: '',     color: '#d4a017', group: 'Grip',        flex: 1,
    tip: 'Magnitude of combined lateral and longitudinal g divided by base mu. 1.0 means the car is at the tyre grip ceiling. Values slightly above 1.0 are physically possible because tyre peak mu can exceed the base mu at low load.' },
  curvature_1pm:       { label: 'Curvature',         unit: '1/m',  color: '#5fa78d', group: 'Track',       flex: 1,
    tip: 'Signed track curvature, in 1/m. Positive for a left-hand turn, negative for a right-hand turn. Zero on a straight.' },
  normal_load_front_n: { label: 'Front Axle Load',   unit: 'N',    color: '#7896c9', group: 'Tyre Loads',  flex: 1,
    tip: 'Total vertical load on the front axle, in N. Rises under braking and at high speed when aero downforce is applied with a forward centre of pressure.' },
  normal_load_rear_n:  { label: 'Rear Axle Load',    unit: 'N',    color: '#c97878', group: 'Tyre Loads',  flex: 1,
    tip: 'Total vertical load on the rear axle, in N. Rises under acceleration and at high speed when aero downforce is applied with a rearward centre of pressure.' },
};

const GG_V_GRADIENT_STOPS = [
  [0.00, [ 33, 102, 172]],
  [0.25, [ 67, 162, 202]],
  [0.50, [102, 194, 165]],
  [0.75, [253, 174,  97]],
  [1.00, [215,  48,  39]],
];

const GG_V_GRADIENT_CSS = 'linear-gradient(to right, ' +
  GG_V_GRADIENT_STOPS.map(([, rgb]) => `rgb(${rgb.join(',')})`).join(', ') + ')';

function speedToColor(t) {
  const clamped = Math.max(0, Math.min(1, t));
  for (let i = 0; i < GG_V_GRADIENT_STOPS.length - 1; i++) {
    const [t0, c0] = GG_V_GRADIENT_STOPS[i];
    const [t1, c1] = GG_V_GRADIENT_STOPS[i + 1];
    if (clamped <= t1) {
      const f = (clamped - t0) / (t1 - t0);
      const r = Math.round(c0[0] + (c1[0] - c0[0]) * f);
      const g = Math.round(c0[1] + (c1[1] - c0[1]) * f);
      const b = Math.round(c0[2] + (c1[2] - c0[2]) * f);
      return `rgb(${r},${g},${b})`;
    }
  }
  const last = GG_V_GRADIENT_STOPS[GG_V_GRADIENT_STOPS.length - 1][1];
  return `rgb(${last.join(',')})`;
}

const VIZ_TABS = [
  {
    key: 'telemetry',
    label: 'Telemetry',
    render: () => renderTelemetryTab(),
    legend: [
      { channelKey: 'speeds_kmh',          group: 'Speed' },
      { channelKey: 'g_lat',               group: 'G-Forces' },
      { channelKey: 'g_long',              group: 'G-Forces' },
      { channelKey: 'mu_util',             group: 'Grip' },
      { channelKey: 'curvature_1pm',       group: 'Track' },
      { channelKey: 'normal_load_front_n', group: 'Tyre Loads' },
      { channelKey: 'normal_load_rear_n',  group: 'Tyre Loads' },
    ],
  },
  {
    key: 'gg',
    label: 'G-G-V Diagram',
    render: () => renderGGTab(),
    legend: [
      { label: 'V', unit: 'km/h', color: GG_V_GRADIENT_CSS, group: 'Speed' },
    ],
  },
  {
    key: 'track',
    label: 'Track Map',
    render: () => renderTrackTab(),
    legend: [
      { label: 'V', unit: 'km/h', color: GG_V_GRADIENT_CSS, group: 'Speed' },
    ],
  },
];

let telemetryState = {
  runs: {},
  activeRunId: null,
  activePanes: ['speeds_kmh', 'g_lat', 'g_long'],
  activeTabKey: 'telemetry',
  isRunning: false,
};

let parameterDefaults = null;

let _chartInstances = {};
let _trackResizeObserver = null;

function destroyAllCharts() {
  if (_trackResizeObserver) {
    _trackResizeObserver.disconnect();
    _trackResizeObserver = null;
  }
  for (const key of Object.keys(_chartInstances)) {
    const c = _chartInstances[key];
    if (c && typeof c.destroy === 'function') {
      try { c.destroy(); } catch { /* ignore teardown errors */ }
    }
    delete _chartInstances[key];
  }
}

function showSimLoader(area, label = 'Running simulation') {
  area.innerHTML = `
    <div class="sim-loading">
      <div class="sim-loading-bars">
        <span></span><span></span><span></span><span></span><span></span>
        <span></span><span></span><span></span><span></span><span></span>
      </div>
      <div class="sim-loading-label">${label}</div>
    </div>`;
}

async function apiFetch(input, init) {
  const res = await fetch(input, init);
  if (res.status === 401) {
    window.location.href = '/login';
    throw new Error('Not authenticated');
  }
  return res;
}

async function initUserBar() {
  try {
    const res = await apiFetch('/api/me');
    if (!res.ok) return;
    const body = await res.json();
    const emailEl = document.getElementById('userBarEmail');
    if (emailEl) emailEl.textContent = body.email || '';
  } catch (e) {
    // apiFetch already redirects on 401; nothing to do here
  }
  const logoutBtn = document.getElementById('userBarLogout');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', () => {
      const form = document.createElement('form');
      form.method = 'POST';
      form.action = '/logout';
      document.body.appendChild(form);
      form.submit();
    });
  }
}

function initTabs() {
  const tabs = document.querySelectorAll('.tab[role="tab"]');
  const sections = document.querySelectorAll('.tab-section[role="tabpanel"]');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => {
        t.classList.remove('active');
        t.setAttribute('aria-selected', 'false');
      });
      sections.forEach(s => s.classList.remove('active'));
      tab.classList.add('active');
      tab.setAttribute('aria-selected', 'true');
      document.getElementById(tab.dataset.tab).classList.add('active');
    });
  });
}

function initInnerTabs() {
  document.querySelectorAll('.inner-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const panel = tab.closest('.panel');
      panel.querySelectorAll('.inner-tab').forEach(t => t.classList.remove('active'));
      panel.querySelectorAll('.inner-tab-section').forEach(s => s.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById(tab.dataset.innerTab).classList.add('active');
    });
  });
}

function resolveLegendItem(entry) {
  if (entry.channelKey) {
    const ch = CHANNEL_REGISTRY[entry.channelKey];
    return {
      channelKey: entry.channelKey,
      label: ch.label,
      unit: ch.unit,
      color: ch.color,
      group: entry.group || ch.group,
      tip: ch.tip,
      toggleable: true,
    };
  }
  return {
    channelKey: null,
    label: entry.label,
    unit: entry.unit,
    color: entry.color,
    group: entry.group,
    tip: entry.tip,
    toggleable: false,
  };
}

function renderChannelList(tab) {
  const list = document.getElementById('channelList');
  list.innerHTML = '';

  const listHeader = document.createElement('div');
  listHeader.className = 'channel-list-header';
  listHeader.textContent = 'Channels';
  list.appendChild(listHeader);

  const items = (tab.legend || []).map(resolveLegendItem);
  const groups = {};
  items.forEach(item => {
    if (!groups[item.group]) groups[item.group] = [];
    groups[item.group].push(item);
  });

  Object.entries(groups).forEach(([group, groupItems]) => {
    const groupHeader = document.createElement('div');
    groupHeader.className = 'channel-group-header';
    groupHeader.textContent = group;
    list.appendChild(groupHeader);

    groupItems.forEach(item => {
      const isActive = !item.toggleable || telemetryState.activePanes.includes(item.channelKey);
      const el = document.createElement('div');
      el.className = 'channel-item' + (isActive ? '' : ' inactive');
      if (item.channelKey) el.dataset.channelKey = item.channelKey;
      if (!item.toggleable) el.style.cursor = 'default';
      const tipHtml = item.tip
        ? ` <button type="button" class="info-tip" aria-label="More info" aria-hidden="true" data-tip="${escapeHtml(item.tip)}" onclick="event.stopPropagation()">i</button>`
        : '';
      el.innerHTML =
        `<div class="channel-dot" style="background:${item.color}"></div>` +
        `<div><span class="channel-item-name">${item.label}</span>${tipHtml}` +
        `<span class="channel-item-unit">${item.unit}</span></div>`;
      if (item.toggleable) {
        el.addEventListener('click', () => toggleChannel(item.channelKey));
      }
      list.appendChild(el);
    });
  });
}

function initVizPanel() {
  const activeTab = VIZ_TABS.find(t => t.key === telemetryState.activeTabKey) || VIZ_TABS[0];
  renderChannelList(activeTab);

  const tabBar = document.getElementById('vizTabBar');
  VIZ_TABS.forEach(tab => {
    const btn = document.createElement('button');
    btn.className = 'viz-tab' + (tab.key === telemetryState.activeTabKey ? ' active' : '');
    btn.textContent = tab.label;
    btn.addEventListener('click', () => {
      telemetryState.activeTabKey = tab.key;
      tabBar.querySelectorAll('.viz-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderChannelList(tab);
      const area = document.getElementById('vizChartArea');
      if (telemetryState.isRunning) {
        showSimLoader(area);
      } else if (telemetryState.activeRunId) {
        tab.render();
      } else {
        area.innerHTML = '';
      }
    });
    tabBar.appendChild(btn);
  });
}

function storeTelemetry(data) {
  telemetryState.runs = {};
  const runId = `run_${Date.now()}`;
  telemetryState.runs[runId] = {
    meta: {
      lap_time_s: data.lap_time_s,
      max_abs_g_lat: data.max_abs_g_lat,
      max_abs_g_long: data.max_abs_g_long,
      track_file_path: data.track_file_path,
    },
    telemetry: data.telemetry,
  };
  telemetryState.activeRunId = runId;
}

function renderViz() {
  const run = telemetryState.runs[telemetryState.activeRunId];
  if (!run) return;
  renderSummaryStrip(run.meta);
  const activeTab = VIZ_TABS.find(t => t.key === telemetryState.activeTabKey);
  if (activeTab) activeTab.render();
}

function renderSummaryStrip(meta) {
  document.getElementById('stat-lap-time').textContent = meta.lap_time_s.toFixed(2);
  document.getElementById('stat-max-lat-g').textContent = meta.max_abs_g_lat.toFixed(2);
  document.getElementById('stat-max-long-g').textContent = meta.max_abs_g_long.toFixed(2);
  const trackName = meta.track_file_path.replace(/\\/g, '/').split('/').pop().replace(/\.[^.]+$/, '');
  document.getElementById('stat-track').textContent = trackName;
  const status = document.getElementById('run-status');
  status.textContent = 'RUN OK';
  status.className = 'run-status ok';
  document.getElementById('csvDownloadBtn').disabled = false;
}

function renderTelemetryTab() {
  const run = telemetryState.runs[telemetryState.activeRunId];
  if (!run) return;

  const area = document.getElementById('vizChartArea');
  area.innerHTML = '';

  destroyAllCharts();

  const { telemetry } = run;

  telemetryState.activePanes.forEach(key => {
    const ch = CHANNEL_REGISTRY[key];
    if (!ch) return;

    const pane = document.createElement('div');
    pane.className = `chart-pane ${ch.flex === 2 ? 'chart-pane--lg' : 'chart-pane--sm'}`;
    pane.id = `pane-${key}`;

    const header = document.createElement('div');
    header.className = 'chart-pane-header';
    header.style.borderLeft = `3px solid ${ch.color}`;
    header.innerHTML =
      `<span class="chart-pane-title" style="color:${ch.color}">${ch.label}</span>` +
      `<span class="chart-pane-unit">${ch.unit}</span>`;

    const body = document.createElement('div');
    body.className = 'chart-pane-body';

    const canvas = document.createElement('canvas');
    canvas.id = `chart-${key}`;
    canvas.setAttribute('aria-label', `${ch.label} channel over distance for the current run`);
    body.appendChild(canvas);

    pane.appendChild(header);
    pane.appendChild(body);
    area.appendChild(pane);

    _chartInstances[key] = new Chart(canvas, {
      type: 'line',
      data: {
        labels: telemetry.distances_m,
        datasets: [{
          data: telemetry[key],
          borderColor: ch.color,
          borderWidth: 1.5,
          pointRadius: 0,
          fill: false,
          tension: 0,
        }],
      },
      options: {
        animation: false,
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: {
            type: 'linear',
            grid: { color: '#E8ECF0' },
            ticks: { color: '#A7AEB6', font: { size: 9 }, maxTicksLimit: 8 },
            title: { display: true, text: 'Distance (m)', color: '#A7AEB6', font: { size: 9 } },
          },
          y: {
            grid: { color: '#E8ECF0' },
            ticks: { color: '#A7AEB6', font: { size: 9 }, maxTicksLimit: 5 },
          },
        },
      },
    });
  });
}

function renderGGTab() {
  const run = telemetryState.runs[telemetryState.activeRunId];
  if (!run) return;

  const area = document.getElementById('vizChartArea');
  area.innerHTML = '';

  destroyAllCharts();

  const { g_lat, g_long, speeds_kmh } = run.telemetry;

  let vMin = Infinity;
  let vMax = -Infinity;
  for (const v of speeds_kmh) {
    if (v < vMin) vMin = v;
    if (v > vMax) vMax = v;
  }
  const vRange = vMax - vMin || 1;
  const pointColors = speeds_kmh.map(v => speedToColor((v - vMin) / vRange));

  const container = document.createElement('div');
  container.className = 'gg-chart-container';
  const canvas = document.createElement('canvas');
  canvas.id = 'chart-gg';
  canvas.setAttribute('aria-label', 'G-G-V diagram showing lateral and longitudinal acceleration coloured by speed');
  container.appendChild(canvas);
  area.appendChild(container);

  _chartInstances['gg'] = new Chart(canvas, {
    type: 'scatter',
    data: {
      datasets: [{
        data: g_lat.map((lat, i) => ({ x: lat, y: g_long[i], v: speeds_kmh[i] })),
        borderColor: pointColors,
        backgroundColor: pointColors,
        pointRadius: 2,
        pointHoverRadius: 3,
      }],
    },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const d = ctx.raw;
              return `Lat ${d.x.toFixed(2)} g, Long ${d.y.toFixed(2)} g, V ${d.v.toFixed(0)} km/h`;
            },
          },
        },
      },
      scales: {
        x: {
          title: { display: true, text: 'Lat G', color: '#A7AEB6', font: { size: 10 } },
          grid: { color: '#E8ECF0' },
          ticks: { color: '#A7AEB6', font: { size: 9 } },
        },
        y: {
          title: { display: true, text: 'Long G', color: '#A7AEB6', font: { size: 10 } },
          grid: { color: '#E8ECF0' },
          ticks: { color: '#A7AEB6', font: { size: 9 } },
        },
      },
    },
  });

  renderGGVScale(area, vMin, vMax);
}

function renderGGVScale(area, vMin, vMax) {
  const scale = document.createElement('div');
  scale.className = 'gg-v-scale';
  scale.innerHTML =
    `<span class="gg-v-scale-label">V (km/h)</span>` +
    `<span class="gg-v-scale-min">${Math.round(vMin)}</span>` +
    `<span class="gg-v-scale-bar" style="background:${GG_V_GRADIENT_CSS}"></span>` +
    `<span class="gg-v-scale-max">${Math.round(vMax)}</span>`;
  area.appendChild(scale);
}

function renderTrackTab() {
  const run = telemetryState.runs[telemetryState.activeRunId];
  if (!run) return;

  const area = document.getElementById('vizChartArea');
  area.innerHTML = '';

  destroyAllCharts();

  const { x_m, y_m, speeds_kmh, distances_m } = run.telemetry;
  if (!x_m || !y_m || x_m.length === 0) {
    area.innerHTML = '<div class="sweep-placeholder">Track coordinates not available in this run.</div>';
    return;
  }

  let vMin = Infinity;
  let vMax = -Infinity;
  for (const v of speeds_kmh) {
    if (v < vMin) vMin = v;
    if (v > vMax) vMax = v;
  }
  const vRange = vMax - vMin || 1;
  const segColor = (i) => speedToColor((speeds_kmh[i] - vMin) / vRange);

  const points = x_m.map((x, i) => ({ x, y: y_m[i], v: speeds_kmh[i], s: distances_m?.[i] }));

  let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity;
  for (let i = 0; i < x_m.length; i++) {
    if (x_m[i] < xMin) xMin = x_m[i];
    if (x_m[i] > xMax) xMax = x_m[i];
    if (y_m[i] < yMin) yMin = y_m[i];
    if (y_m[i] > yMax) yMax = y_m[i];
  }
  const xSpan = xMax - xMin || 1;
  const ySpan = yMax - yMin || 1;
  const span = Math.max(xSpan, ySpan) * 1.05;
  const xMid = (xMin + xMax) / 2;
  const yMid = (yMin + yMax) / 2;
  const xLo = xMid - span / 2;
  const xHi = xMid + span / 2;
  const yLo = yMid - span / 2;
  const yHi = yMid + span / 2;

  const container = document.createElement('div');
  container.className = 'track-map-container';
  const square = document.createElement('div');
  square.className = 'track-map-square';
  const canvas = document.createElement('canvas');
  canvas.id = 'chart-track';
  canvas.setAttribute('aria-label', 'Track map showing the circuit layout coloured by speed');
  square.appendChild(canvas);
  container.appendChild(square);
  area.appendChild(container);

  const sizeSquare = () => {
    const w = container.clientWidth;
    const h = container.clientHeight;
    const side = Math.max(80, Math.min(w, h));
    square.style.width  = side + 'px';
    square.style.height = side + 'px';
    if (_chartInstances['track']) _chartInstances['track'].resize();
  };
  sizeSquare();
  _trackResizeObserver = new ResizeObserver(sizeSquare);
  _trackResizeObserver.observe(container);

  _chartInstances['track'] = new Chart(canvas, {
    type: 'scatter',
    data: {
      datasets: [{
        data: points,
        showLine: true,
        pointRadius: 0,
        pointHoverRadius: 3,
        borderWidth: 2.5,
        borderColor: '#A7AEB6',
        segment: {
          borderColor: (ctx) => segColor(ctx.p0DataIndex),
        },
        spanGaps: false,
      }],
    },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      aspectRatio: 1,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const d = ctx.raw;
              const s = (d.s != null) ? `${d.s.toFixed(0)} m, ` : '';
              return `${s}V ${d.v.toFixed(0)} km/h`;
            },
          },
        },
      },
      scales: {
        x: {
          type: 'linear',
          min: xLo,
          max: xHi,
          title: { display: true, text: 'X (m)', color: '#A7AEB6', font: { size: 10 } },
          grid: { color: '#E8ECF0' },
          ticks: { color: '#A7AEB6', font: { size: 9 } },
        },
        y: {
          type: 'linear',
          min: yLo,
          max: yHi,
          title: { display: true, text: 'Y (m)', color: '#A7AEB6', font: { size: 10 } },
          grid: { color: '#E8ECF0' },
          ticks: { color: '#A7AEB6', font: { size: 9 } },
        },
      },
    },
  });

  renderGGVScale(area, vMin, vMax);
}

function toggleChannel(key) {
  const idx = telemetryState.activePanes.indexOf(key);
  if (idx === -1) {
    telemetryState.activePanes.push(key);
  } else {
    telemetryState.activePanes.splice(idx, 1);
  }
  document.querySelectorAll('.channel-item').forEach(el => {
    el.classList.toggle('inactive', !telemetryState.activePanes.includes(el.dataset.channelKey));
  });
  if (telemetryState.activeTabKey === 'telemetry' && telemetryState.activeRunId) {
    renderTelemetryTab();
  }
}

function downloadCSV() {
  const run = telemetryState.runs[telemetryState.activeRunId];
  if (!run) return;
  const { telemetry, meta } = run;

  const channelKeys = Object.keys(CHANNEL_REGISTRY);
  const headers = ['distance_m', ...channelKeys.map(k =>
    `${CHANNEL_REGISTRY[k].label.toLowerCase().replace(/\s+/g, '_')}_${CHANNEL_REGISTRY[k].unit.replace('/', '_per_')}`,
  )];

  const allKeys = ['distances_m', ...channelKeys];
  const n = telemetry.distances_m.length;
  const rows = [headers.join(',')];
  for (let i = 0; i < n; i++) {
    rows.push(allKeys.map(k => {
      const val = telemetry[k]?.[i];
      return val !== undefined ? Number(val).toFixed(4) : '';
    }).join(','));
  }

  const blob = new Blob([rows.join('\n')], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  const trackName = meta.track_file_path.replace(/\\/g, '/').split('/').pop().replace(/\.[^.]+$/, '');
  a.href = url;
  a.download = `lgr_lap_${trackName}_${meta.lap_time_s.toFixed(2)}s.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function populateParameters(p) {
  parameterDefaults = JSON.parse(JSON.stringify(p));
  document.getElementById('p-general-name').value = p.general?.name ?? '';
  document.getElementById('p-general-mass').value = p.general?.mass ?? '';
  document.getElementById('p-general-base_mu').value = p.general?.base_mu ?? '';
  document.getElementById('p-aero-frontal_area').value = p.aerodynamics?.frontal_area ?? '';
  document.getElementById('p-aero-drag_coefficient').value = p.aerodynamics?.drag_coefficient ?? '';
  document.getElementById('p-aero-downforce_coefficient').value = p.aerodynamics?.downforce_coefficient ?? '';
  document.getElementById('p-aero-aero_cp').value = p.aerodynamics?.aero_cp ?? '';
  document.getElementById('p-geom-wheelbase').value = p.geometry?.wheelbase ?? '';
  document.getElementById('p-geom-front_track_width').value = p.geometry?.front_track_width ?? '';
  document.getElementById('p-geom-rear_track_width').value = p.geometry?.rear_track_width ?? '';
  document.getElementById('p-geom-cog_z').value = p.geometry?.cog_z ?? '';
  document.getElementById('p-geom-cog_longitudinal_pos').value = p.geometry?.cog_longitudinal_pos ?? '';
  document.getElementById('p-geom-max_cog_z').value = p.geometry?.max_cog_z ?? '';
  document.getElementById('p-vd-roll_stiffness').value = p.vehicle_dynamics?.roll_stiffness ?? '';
  document.getElementById('p-vd-max_roll_angle_deg').value = p.vehicle_dynamics?.max_roll_angle_deg ?? '';
  document.getElementById('p-dt-wheel_radius').value = p.drivetrain?.wheel_radius ?? '';
  document.getElementById('p-dt-final_drive_ratio').value = p.drivetrain?.final_drive_ratio ?? '';
  document.getElementById('p-dt-gear_ratios').value = (p.drivetrain?.gear_ratios ?? []).join(', ');
  document.getElementById('p-dt-transmission_efficiency').value = p.drivetrain?.transmission_efficiency ?? '';
}

function removeInactiveParameterField(id) {
  const input = document.getElementById(id);
  if (!input) return;
  const label = input.previousElementSibling;
  const hint = input.nextElementSibling;
  if (label && label.classList.contains('field-label')) label.remove();
  if (hint && hint.classList.contains('field-hint')) hint.remove();
  input.remove();
}

function removeInactiveParameterFields() {
  removeInactiveParameterField('p-vd-suspension_stiffness');
  removeInactiveParameterField('p-vd-damping_coefficient');
}

async function populateConfig(c) {
  const ds = c.datasets || {};
  document.getElementById('c-powertrain-display').textContent  = ds.powertrain?.label        || '--';
  document.getElementById('c-tyre-lat-display').textContent    = ds.tyre_lateral?.label      || '--';
  document.getElementById('c-tyre-long-display').textContent   = ds.tyre_longitudinal?.label || '--';

  document.getElementById('c-sim-full_telemetry_mode').checked = c.full_telemetry_mode ?? true;
  document.getElementById('c-ambient-air_density').value       = c.ambient_conditions?.air_density ?? '';

  const maxBrake = c.solver?.max_brake_decel_g;
  document.getElementById('c-solver-max_brake_decel_g').value = (maxBrake == null) ? '' : maxBrake;
  document.getElementById('c-solver-use_rollover_speed_cap').checked = c.solver?.use_rollover_speed_cap ?? true;

  await populateTrackDropdown(ds.track?.id || null);

  initTyreTab();
}

async function populateTrackDropdown(currentTrackId) {
  const select = document.getElementById('c-track-id');
  try {
    const res = await apiFetch('/api/track/datasets');
    if (!res.ok) return;
    const tracks = await res.json();
    select.innerHTML = '';
    tracks.forEach(t => {
      const opt = document.createElement('option');
      opt.value = t.id;
      opt.textContent = t.label;
      if (t.id === currentTrackId) opt.selected = true;
      select.appendChild(opt);
    });
  } catch {
    select.innerHTML = '<option value="">Could not load tracks</option>';
  }
}

async function loadParametersAndConfig() {
  try {
    const [pRes, cRes] = await Promise.all([
      apiFetch('/api/parameters'),
      apiFetch('/api/config'),
    ]);
    if (!pRes.ok || !cRes.ok) throw new Error('Failed to load defaults');
    populateParameters(await pRes.json());
    populateConfig(await cRes.json());
  } catch {
    const errorEl = document.getElementById('runError');
    if (errorEl) {
      errorEl.textContent = 'Could not load defaults. Check that the server is running.';
      errorEl.style.display = 'block';
    }
  }
}

function collectParameters() {
  const errors = [];

  function getFloat(id, label) {
    const el = document.getElementById(id);
    const val = parseFloat(el.value);
    if (isNaN(val)) {
      el.classList.add('field-error');
      errors.push(`${label} must be a number`);
    } else {
      el.classList.remove('field-error');
    }
    return val;
  }

  function getString(id) {
    const el = document.getElementById(id);
    el.classList.remove('field-error');
    return el.value.trim();
  }

  function getArray(id, label) {
    const el = document.getElementById(id);
    const parts = el.value.split(',').map(s => parseFloat(s.trim()));
    if (parts.some(isNaN)) {
      el.classList.add('field-error');
      errors.push(`${label} must be comma-separated numbers`);
    } else {
      el.classList.remove('field-error');
    }
    return parts;
  }

  const params = {
    general: {
      name: getString('p-general-name'),
      mass: getFloat('p-general-mass', 'Mass'),
      base_mu: getFloat('p-general-base_mu', 'Base mu'),
    },
    aerodynamics: {
      frontal_area: getFloat('p-aero-frontal_area', 'Frontal area'),
      drag_coefficient: getFloat('p-aero-drag_coefficient', 'Drag coefficient'),
      downforce_coefficient: getFloat('p-aero-downforce_coefficient', 'Downforce coefficient'),
      aero_cp: getFloat('p-aero-aero_cp', 'Aero CoP'),
    },
    geometry: {
      wheelbase: getFloat('p-geom-wheelbase', 'Wheelbase'),
      front_track_width: getFloat('p-geom-front_track_width', 'Front track width'),
      rear_track_width: getFloat('p-geom-rear_track_width', 'Rear track width'),
      cog_z: getFloat('p-geom-cog_z', 'CoG Z'),
      cog_longitudinal_pos: getFloat('p-geom-cog_longitudinal_pos', 'CoG longitudinal position'),
      max_cog_z: getFloat('p-geom-max_cog_z', 'Max CoG Z'),
    },
    vehicle_dynamics: {
      roll_stiffness: getFloat('p-vd-roll_stiffness', 'Roll stiffness'),
      suspension_stiffness: parameterDefaults?.vehicle_dynamics?.suspension_stiffness ?? 0,
      damping_coefficient: parameterDefaults?.vehicle_dynamics?.damping_coefficient ?? 0,
      max_roll_angle_deg: getFloat('p-vd-max_roll_angle_deg', 'Max roll angle'),
    },
    drivetrain: {
      wheel_radius: getFloat('p-dt-wheel_radius', 'Wheel radius'),
      final_drive_ratio: getFloat('p-dt-final_drive_ratio', 'Final drive ratio'),
      gear_ratios: getArray('p-dt-gear_ratios', 'Gear ratios'),
      transmission_efficiency: getFloat('p-dt-transmission_efficiency', 'Transmission efficiency'),
    },
  };

  return { params, errors };
}

function collectConfig() {
  const errors = [];

  function getFloat(id, label) {
    const el = document.getElementById(id);
    const val = parseFloat(el.value);
    if (isNaN(val)) {
      el.classList.add('field-error');
      errors.push(`${label} must be a number`);
    } else {
      el.classList.remove('field-error');
    }
    return val;
  }

  function getOptionalFloat(id) {
    const el = document.getElementById(id);
    el.classList.remove('field-error');
    const raw = el.value.trim();
    if (raw === '') return null;
    const val = parseFloat(raw);
    if (isNaN(val)) {
      el.classList.add('field-error');
      errors.push('Max brake decel must be a number or blank');
      return null;
    }
    return val;
  }

  function getBool(id) {
    return document.getElementById(id).checked;
  }

  function getSelect(id) {
    const el = document.getElementById(id);
    el.classList.remove('field-error');
    return el.value || null;
  }

  const cfg = {
    track_id: getSelect('c-track-id'),
    full_telemetry_mode: getBool('c-sim-full_telemetry_mode'),
    use_rollover_speed_cap: getBool('c-solver-use_rollover_speed_cap'),
    max_brake_decel_g: getOptionalFloat('c-solver-max_brake_decel_g'),
    air_density: getFloat('c-ambient-air_density', 'Air density'),
  };

  return { cfg, errors };
}

async function loadMetadata() {
  const res = await apiFetch('/api/metadata');
  const data = await res.json();
  const el = document.getElementById('scope');
  if (el) el.textContent = data.model_scope ?? '';
}

async function runLap() {
  const { params, errors: paramErrors } = collectParameters();
  const { cfg, errors: cfgErrors } = collectConfig();
  const allErrors = [...paramErrors, ...cfgErrors];

  const errorEl = document.getElementById('runError');

  if (allErrors.length > 0) {
    errorEl.textContent = allErrors.join('\n');
    errorEl.style.display = 'block';
    return;
  }
  errorEl.style.display = 'none';

  const status = document.getElementById('run-status');
  status.textContent = 'Running...';
  status.className = 'run-status';

  const btn = document.getElementById('runLapBtn');
  btn.disabled = true;

  const chartArea = document.getElementById('vizChartArea');
  telemetryState.isRunning = true;
  showSimLoader(chartArea);

  let data;
  try {
    const overrides = {};
    if (cfg.track_id) overrides.track_id = cfg.track_id;
    if (cfg.air_density != null && !isNaN(cfg.air_density)) overrides.air_density = cfg.air_density;
    if (cfg.full_telemetry_mode != null) overrides.full_telemetry_mode = cfg.full_telemetry_mode;
    if (cfg.use_rollover_speed_cap != null) overrides.use_rollover_speed_cap = cfg.use_rollover_speed_cap;
    if (cfg.max_brake_decel_g != null) overrides.max_brake_decel_g = cfg.max_brake_decel_g;
    const res = await apiFetch('/api/lap/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ parameters: params, overrides }),
    });
    data = await res.json();
    if (!res.ok) {
      telemetryState.isRunning = false;
      const detail = data.detail;
      let msg;
      if (typeof detail === 'string') {
        msg = detail;
      } else if (Array.isArray(detail)) {
        msg = detail.map(e => `${(e.loc || []).join('.')}: ${e.msg}`).join('\n');
      } else {
        msg = JSON.stringify(data, null, 2);
      }
      showRunFailure(chartArea, status, errorEl, msg);
      btn.disabled = false;
      return;
    }
  } catch (err) {
    telemetryState.isRunning = false;
    showRunFailure(chartArea, status, errorEl, 'Could not reach the server. Try again.');
    btn.disabled = false;
    console.error('runLap network error', err);
    return;
  }

  telemetryState.isRunning = false;
  try {
    storeTelemetry(data);
    renderViz();
  } catch (err) {
    console.error('runLap render error', err);
    const msg = (err && err.message) ? err.message : String(err);
    showRunFailure(chartArea, status, errorEl, 'Telemetry received but the chart failed to render. ' + msg);
  } finally {
    btn.disabled = false;
  }
}

function showRunFailure(chartArea, status, errorEl, msg) {
  status.textContent = 'RUN FAILED';
  status.className = 'run-status error';
  errorEl.textContent = msg;
  errorEl.style.display = 'block';
  chartArea.innerHTML = `
    <div class="sim-error-tile">
      <div class="sim-error-tile-title">Run failed</div>
      <div class="sim-error-tile-msg">${escapeHtml(msg)}</div>
      <div class="sim-error-tile-hint">Press Run Simulation to try again.</div>
    </div>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
}

// ── Lesson link handling ────────────────────────────────────────────────────

function resolvePath(baseDir, rel) {
  const parts = [...baseDir.split('/'), ...rel.split('/')];
  const resolved = [];
  for (const p of parts) {
    if (p === '..') resolved.pop();
    else if (p !== '' && p !== '.') resolved.push(p);
  }
  return resolved.join('/');
}

function showToast(message) {
  let toast = document.getElementById('lgr-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'lgr-toast';
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.classList.add('visible');
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => toast.classList.remove('visible'), 4000);
}

function processLessonLinks(container, lessonFile) {
  const baseDir = 'docs/lessons';

  container.querySelectorAll('a[href]').forEach(link => {
    const href = link.getAttribute('href');
    if (!href || href.startsWith('http') || href.startsWith('#')) return;

    const resolved = resolvePath(baseDir, href);
    const isMd = resolved.endsWith('.md');

    if (isMd) {
      const isLesson = resolved.startsWith('docs/lessons/');
      link.classList.add('md-link');
      link.addEventListener('click', e => {
        e.preventDefault();
        if (isLesson) {
          const filename = resolved.split('/').pop();
          const item = document.querySelector(`.lesson-item[data-src="${filename}"]`);
          if (item) {
            item.click();
          } else {
            showToast('This lesson is not yet in the guide.');
          }
        } else {
          showToast('This document is not yet linked to a page.');
        }
      });
    } else {
      link.classList.add('code-link');
      link.setAttribute('title', resolved);
      link.addEventListener('click', e => {
        e.preventDefault();
        showToast('Open this file in your editor: ' + resolved);
      });
    }
  });
}

// ── Math pre-processing ──────────────────────────────────────────────────────
// Extract math before marked.js sees it to prevent _ and ^ mangling.

function renderMarkdownWithMath(md, options = {}) {
  const stash = [];

  const save = (math, display) => {
    const key = `\x02MATH${stash.length}\x03`;
    stash.push({ key, math, display });
    return key;
  };

  let processed = md
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, m) => save(m, true))
    .replace(/\\\(([\s\S]*?)\\\)/g, (_, m) => save(m, false))
    .replace(/\$\$([\s\S]*?)\$\$/g, (_, m) => save(m, true))
    .replace(/\$([^\$\n]+?)\$/g, (_, m) => save(m, false));

  if (options.escapeHtml) {
    processed = escapeHtml(processed);
  }

  let html = marked.parse(processed);

  for (const { key, math, display } of stash) {
    const rendered = katex.renderToString(math, { displayMode: display, throwOnError: false });
    html = html.replace(key, rendered);
  }

  return html;
}

// ── Lessons ─────────────────────────────────────────────────────────────────

async function loadLesson(filename, title) {
  const body = document.getElementById('lessonBody');
  const label = document.getElementById('lessonTitle');
  body.textContent = 'Loading...';
  label.textContent = title;
  const res = await apiFetch('/lessons/' + filename);
  const md = await res.text();
  body.innerHTML = renderMarkdownWithMath(md);
  body.querySelectorAll('img[src]').forEach(img => {
    const src = img.getAttribute('src');
    if (src && !src.startsWith('http') && !src.startsWith('/')) {
      img.setAttribute('src', '/lessons/' + src);
    }
  });
  processLessonLinks(body, filename);
}

function initLessons() {
  const items = document.querySelectorAll('.lesson-item');
  items.forEach(item => {
    item.addEventListener('click', () => {
      items.forEach(i => i.classList.remove('active'));
      item.classList.add('active');
      loadLesson(item.dataset.src, item.textContent.trim());
    });
  });
  const first = document.querySelector('.lesson-item');
  if (first) loadLesson(first.dataset.src, first.textContent.trim());
}

// ── Chat Panel ───────────────────────────────────────────────────────────────

let chatHistory = [];

function positionChatPanel() {
  const tabBar = document.querySelector('.tab-bar');
  const top = tabBar.getBoundingClientRect().bottom;
  const panel = document.getElementById('chatPanel');
  panel.style.top = top + 'px';
  panel.style.height = `calc(100vh - ${top}px)`;
}

function toggleChatPanel(forceOpen) {
  const panel = document.getElementById('chatPanel');
  const btn = document.getElementById('askBtn');
  const open = forceOpen !== undefined ? forceOpen : panel.classList.contains('hidden');
  panel.classList.toggle('hidden', !open);
  btn.classList.toggle('active', open);
  btn.textContent = open ? 'Close' : 'Ask';
  if (open) document.getElementById('chatQuestion').focus();
}

function appendChatMessage(role, content, sources) {
  const thread = document.getElementById('chatMessages');
  const msg = document.createElement('div');
  msg.className = `chat-msg ${role}`;
  if (role === 'assistant') {
    msg.innerHTML = renderMarkdownWithMath(content, { escapeHtml: true });
  } else {
    msg.textContent = content;
  }

  if (sources && sources.length > 0) {
    const pillRow = document.createElement('div');
    pillRow.className = 'chat-sources';
    sources.forEach(src => {
      const pill = document.createElement('span');
      pill.className = 'chat-source-pill';
      pill.textContent = src.section;
      pill.title = src.file;
      pill.addEventListener('click', () => navigateToLesson(src.file));
      pillRow.appendChild(pill);
    });
    msg.appendChild(pillRow);
  }

  thread.appendChild(msg);
  thread.scrollTop = thread.scrollHeight;
  return msg;
}

function navigateToLesson(file) {
  const item = document.querySelector(`.lesson-item[data-src="${file}"]`);
  if (!item) {
    showToast('This lesson is not yet available in the guide.');
    return;
  }
  const lessonsTab = document.querySelector('.tab[data-tab="lessons"]');
  if (lessonsTab) lessonsTab.click();
  item.click();
}

async function sendChatMessage() {
  const input = document.getElementById('chatQuestion');
  const btn = document.getElementById('chatSubmit');
  const question = input.value.trim();
  if (!question) return;

  input.value = '';
  input.disabled = true;
  btn.disabled = true;

  appendChatMessage('user', question);
  const loading = (() => {
    const thread = document.getElementById('chatMessages');
    const el = document.createElement('div');
    el.className = 'chat-msg assistant chat-loading';
    el.innerHTML = '<span></span><span></span><span></span>';
    thread.appendChild(el);
    thread.scrollTop = thread.scrollHeight;
    return el;
  })();

  try {
    const res = await apiFetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, history: chatHistory }),
    });

    loading.remove();

    if (res.status === 503) {
      appendChatMessage('assistant', 'The assistant is not available right now. Try again shortly.');
    } else if (!res.ok) {
      appendChatMessage('assistant', 'Something went wrong. Try again.');
    } else {
      const data = await res.json();
      appendChatMessage('assistant', data.answer, data.sources);
      chatHistory.push({ role: 'user', content: question });
      chatHistory.push({ role: 'assistant', content: data.answer });
    }
  } catch {
    loading.remove();
    appendChatMessage('assistant', 'Could not reach the server. Try again.');
  } finally {
    input.disabled = false;
    btn.disabled = false;
    input.focus();
  }
}

// ── Sweep param dropdown ─────────────────────────────────────────────────────

const SWEEP_PARAM_HINTS = {
  list:    'Multiple sets separated by semicolons, e.g. [2.75,2.0,1.667];[3.2,2.3,1.9]',
  string:  'Comma-separated explicit values, e.g. F25_IC_Car,F26_IC_Car',
  numeric: 'Range: min,max (uses steps). Explicit list: 250,275,300,325,350',
};

const DEFERRED_PARAMETERS = new Set(['suspension_stiffness', 'damping_coefficient']);

async function populateSweepTrackDropdown() {
  const select = document.getElementById('sw-track-id');
  try {
    const res = await apiFetch('/api/track/datasets');
    if (!res.ok) return;
    const tracks = await res.json();
    tracks.forEach(t => {
      const opt = document.createElement('option');
      opt.value = t.id;
      opt.textContent = t.label;
      select.appendChild(opt);
    });
  } catch {
    // leave with only the default option
  }
}

async function initSweepParams() {
  const sel = document.getElementById('sw-param');
  populateSweepTrackDropdown();
  try {
    const res  = await apiFetch('/api/parameters');
    const data = await res.json();

    sel.innerHTML = '';
    Object.entries(data).forEach(([section, fields]) => {
      const group = document.createElement('optgroup');
      group.label = section.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
      Object.entries(fields).forEach(([key, val]) => {
        if (key === 'name') return;
        if (DEFERRED_PARAMETERS.has(key)) return;
        const opt = document.createElement('option');
        opt.value = key;
        const typeTag = Array.isArray(val) ? 'list' : typeof val === 'string' ? 'str' : `${val}`;
        opt.textContent = `${key}  (${typeTag})`;
        opt.dataset.valtype = Array.isArray(val) ? 'list' : typeof val;
        group.appendChild(opt);
      });
      if (group.children.length) sel.appendChild(group);
    });

    updateSweepParamHint();
    sel.addEventListener('change', updateSweepParamHint);
  } catch {
    sel.innerHTML = '<option value="">Could not load parameters</option>';
  }
}

function updateSweepParamHint() {
  const sel      = document.getElementById('sw-param');
  const opt      = sel.options[sel.selectedIndex];
  const valType  = opt ? opt.dataset.valtype : 'number';
  const hintEl   = document.getElementById('sw-param-hint');
  const valHint  = document.getElementById('sw-values-hint');

  if (valType === 'list') {
    hintEl.textContent  = 'List parameter. Provide candidate sets in the Values field.';
    valHint.textContent = SWEEP_PARAM_HINTS.list;
  } else if (valType === 'string') {
    hintEl.textContent  = 'String parameter. Provide comma-separated candidate values.';
    valHint.textContent = SWEEP_PARAM_HINTS.string;
  } else {
    hintEl.textContent  = '';
    valHint.textContent = SWEEP_PARAM_HINTS.numeric;
  }
}

// ── Parameter Sweep ─────────────────────────────────────────────────────────

let sweepState = { lastResult: null };
let _sweepChart = null;

async function runSweep() {
  const param   = document.getElementById('sw-param').value;
  const values  = document.getElementById('sw-values').value.trim();
  const steps   = parseInt(document.getElementById('sw-steps').value.trim(), 10) || 5;
  const trackId = document.getElementById('sw-track-id').value.trim();

  const errorEl = document.getElementById('sweepError');
  errorEl.style.display = 'none';

  if (!param)  { errorEl.textContent = 'Select a parameter.';  errorEl.style.display = 'block'; return; }
  if (!values) { errorEl.textContent = 'Values are required.';          errorEl.style.display = 'block'; return; }

  const status = document.getElementById('sweep-run-status');
  status.textContent = 'Running...';
  status.className = 'run-status';

  const btn = document.getElementById('runSweepBtn');
  btn.disabled = true;

  const container = document.getElementById('sweepChartContainer');
  container.innerHTML = `
    <div class="sim-loading">
      <div class="sim-loading-bars">
        <span></span><span></span><span></span><span></span><span></span>
        <span></span><span></span><span></span><span></span><span></span>
      </div>
      <div class="sim-loading-label">Running sweep</div>
    </div>`;

  try {
    const body = { param, values, steps };
    if (trackId) body.overrides = { track_id: trackId };

    const res = await apiFetch('/api/sweep/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      container.innerHTML = '';
      status.textContent = 'FAILED';
      status.className = 'run-status error';
      errorEl.textContent = data.detail ?? JSON.stringify(data);
      errorEl.style.display = 'block';
    } else {
      sweepState.lastResult = data;
      renderSweepResults(data);
      status.textContent = 'SWEEP OK';
      status.className = 'run-status ok';
      document.getElementById('swCsvDownloadBtn').disabled = false;
    }
  } catch {
    container.innerHTML = '';
    status.textContent = 'FAILED';
    status.className = 'run-status error';
    errorEl.textContent = 'Could not reach the server. Try again.';
    errorEl.style.display = 'block';
  } finally {
    btn.disabled = false;
  }
}

function renderSweepResults(data) {
  document.getElementById('sw-stat-best-time').textContent  = data.best.lap_time_s.toFixed(2);
  document.getElementById('sw-stat-best-val').textContent   = data.best.label;
  document.getElementById('sw-stat-worst-time').textContent = data.worst.lap_time_s.toFixed(2);
  document.getElementById('sw-stat-worst-val').textContent  = data.worst.label;
  document.getElementById('sw-stat-delta').textContent      = (data.worst.lap_time_s - data.best.lap_time_s).toFixed(2);

  const container = document.getElementById('sweepChartContainer');
  container.innerHTML = '<canvas id="sweepChart"></canvas>';

  if (_sweepChart) { _sweepChart.destroy(); _sweepChart = null; }

  const labels   = data.results.map(r => r.label);
  const lapTimes = data.results.map(r => r.lap_time_s);

  _sweepChart = new Chart(document.getElementById('sweepChart').getContext('2d'), {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Lap Time',
        data: lapTimes,
        borderColor: '#006B5C',
        borderWidth: 2,
        pointRadius: 5,
        pointBackgroundColor: '#006B5C',
        tension: 0.3,
        fill: false,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { title: { display: true, text: data.canonical_param } },
        y: { title: { display: true, text: 'Lap Time (s)' } },
      },
      plugins: { legend: { display: false } },
    },
  });
}

function downloadSweepCSV() {
  const data = sweepState.lastResult;
  if (!data) return;

  const header = [data.canonical_param, 'lap_time_s'];
  const rows   = data.results.map(r => [r.label, r.lap_time_s.toFixed(4)]);
  const csv    = [header, ...rows].map(r => r.join(',')).join('\n');

  const trackName = data.track_file_path.replace(/\\/g, '/').split('/').pop().replace(/\.[^.]+$/, '');
  const blob = new Blob([csv], { type: 'text/csv' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = `lgr_sweep_${data.canonical_param}_${trackName}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Tyre Verification ───────────────────────────────────────────────────────

let _tyreCharts = {};

const TYRE_LAT_DATASET_ID  = 'round_8_12psi';
const TYRE_LONG_DATASET_ID = 'round_6_12psi';

async function initTyreTab() {
  const latDisplay  = document.getElementById('tyre-lat-display');
  const longDisplay = document.getElementById('tyre-long-display');
  try {
    const res = await apiFetch('/api/tyre/datasets');
    if (!res.ok) return;
    const body = await res.json();
    const lat  = (body.lateral      || []).find(d => d.id === TYRE_LAT_DATASET_ID);
    const long = (body.longitudinal || []).find(d => d.id === TYRE_LONG_DATASET_ID);
    if (lat)  latDisplay.textContent  = lat.label;
    if (long) longDisplay.textContent = long.label;
  } catch (e) {
    // leave as '--' if the request fails
  }
}

async function runTyreVerify() {
  const variant = document.getElementById('tyre-model-variant').value;

  const errorEl = document.getElementById('tyreError');
  errorEl.style.display = 'none';

  const status = document.getElementById('tyre-run-status');
  status.textContent = 'Running...';
  status.className = 'run-status';

  const btn = document.getElementById('runTyreBtn');
  btn.disabled = true;

  const area = document.getElementById('tyreChartsArea');
  area.innerHTML = `
    <div class="sim-loading" style="min-height:200px">
      <div class="sim-loading-bars">
        <span></span><span></span><span></span><span></span><span></span>
        <span></span><span></span><span></span><span></span><span></span>
      </div>
      <div class="sim-loading-label">Running tyre verification</div>
    </div>`;

  const muMultiplier = parseFloat(document.getElementById('tyre-mu-multiplier').value) || 1.0;

  try {
    const res  = await apiFetch('/api/tyre/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lat_dataset: TYRE_LAT_DATASET_ID, long_dataset: TYRE_LONG_DATASET_ID, model_variant: variant, mu_multiplier: muMultiplier }),
    });
    const data = await res.json();
    if (!res.ok) {
      area.innerHTML = '';
      status.textContent = 'FAILED';
      status.className = 'run-status error';
      errorEl.textContent = data.detail ?? JSON.stringify(data);
      errorEl.style.display = 'block';
    } else {
      renderTyreResults(data);
      status.textContent = 'DONE';
      status.className = 'run-status ok';
    }
  } catch {
    area.innerHTML = '';
    status.textContent = 'FAILED';
    status.className = 'run-status error';
    errorEl.textContent = 'Could not reach the server. Try again.';
    errorEl.style.display = 'block';
  } finally {
    btn.disabled = false;
  }
}

function _buildTyreChart(canvasId, chartData, xlabel, ylabel) {
  const datasets = [];
  chartData.ttc.forEach(s => {
    datasets.push({ type: 'scatter', label: s.label, data: s.points,
      backgroundColor: s.color, pointRadius: 2, pointHoverRadius: 4 });
  });
  chartData.model.forEach(s => {
    datasets.push({ type: 'line', label: s.label, data: s.points,
      borderColor: s.color, borderWidth: 2, pointRadius: 0, fill: false, tension: 0 });
  });
  return new Chart(document.getElementById(canvasId).getContext('2d'), {
    type: 'scatter',
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { title: { display: true, text: xlabel } },
        y: { title: { display: true, text: ylabel } },
      },
      plugins: {
        legend: { position: 'right', labels: { boxWidth: 10, font: { size: 9 } } },
      },
    },
  });
}

function renderTyreResults(data) {
  const passed = data.validation_passed;
  const resultEl = document.getElementById('tyre-stat-result');
  resultEl.textContent = passed ? 'PASS' : 'FAIL';
  resultEl.className   = 'stat-value stat-value--sm ' + (passed ? 'tyre-stat-pass' : 'tyre-stat-fail');
  document.getElementById('tyre-stat-lat-rmse').textContent  = data.lateral_rmse_pct.toFixed(2);
  document.getElementById('tyre-stat-long-rmse').textContent = data.longitudinal_rmse_pct.toFixed(2);
  document.getElementById('tyre-stat-threshold').textContent = data.rmse_threshold_pct;

  const muNote = document.getElementById('tyre-stat-mu-note');
  const eff = data.base_mu;
  const mult = data.mu_multiplier;
  const latRef = data.lat_ref_mu;
  const longRef = data.long_ref_mu;
  if (latRef != null && longRef != null) {
    const multStr = (mult != null && Math.abs(mult - 1.0) > 0.001) ? ` · multiplier ${mult.toFixed(2)}` : '';
    muNote.textContent = `native lat ${latRef.toFixed(2)} · long ${longRef.toFixed(2)} · effective ${eff.toFixed(2)}${multStr}`;
    muNote.style.display = 'inline';
  } else {
    muNote.style.display = 'none';
  }

  Object.values(_tyreCharts).forEach(c => c.destroy());
  _tyreCharts = {};

  const area = document.getElementById('tyreChartsArea');
  area.innerHTML = `
    <div class="tyre-chart-section">
      <div class="tyre-chart-title">Lateral Force Fy — TTC vs Model</div>
      <div class="tyre-chart-wrap"><canvas id="tyreLatChart"></canvas></div>
    </div>
    <div class="tyre-chart-section">
      <div class="tyre-chart-title">Longitudinal Force Fx — TTC vs Model</div>
      <div class="tyre-chart-wrap"><canvas id="tyreLongChart"></canvas></div>
    </div>
    <div class="tyre-table-section">
      <div class="tyre-chart-title">Per-load Errors</div>
      ${_buildTyreErrorTable(data.rows)}
    </div>`;

  _tyreCharts.lat  = _buildTyreChart('tyreLatChart',  data.lateral_chart,  'Slip Angle (deg)',           'Lateral Force Fy (N)');
  _tyreCharts.long = _buildTyreChart('tyreLongChart', data.longitudinal_chart, 'Slip Ratio (dataset units)', 'Longitudinal Force Fx (N)');
}

function _buildTyreErrorTable(rows) {
  const cols = ['channel','normal_load_N','rmse_pct_of_peak','mae_pct_of_peak','peak_true_N','peak_pred_N'];
  const heads = ['Channel','Load (N)','RMSE % peak','MAE % peak','Peak TTC (N)','Peak Model (N)'];
  const header = heads.map(h => `<th>${h}</th>`).join('');
  const body = rows.map(r => {
    const cells = cols.map(c => {
      const v = r[c];
      return `<td>${typeof v === 'number' ? v.toFixed ? v.toFixed(2) : v : v}</td>`;
    }).join('');
    return `<tr>${cells}</tr>`;
  }).join('');
  return `<table class="tyre-error-table"><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table>`;
}

// ── Boot ────────────────────────────────────────────────────────────────────

document.getElementById('tyre-mu-multiplier').addEventListener('input', e => {
  document.getElementById('tyre-mu-multiplier-val').textContent = parseFloat(e.target.value).toFixed(2);
});

document.getElementById('runLapBtn').addEventListener('click', runLap);
document.getElementById('csvDownloadBtn').addEventListener('click', downloadCSV);
document.getElementById('runSweepBtn').addEventListener('click', runSweep);
document.getElementById('runTyreBtn').addEventListener('click', runTyreVerify);
document.getElementById('swCsvDownloadBtn').addEventListener('click', downloadSweepCSV);
document.getElementById('askBtn').addEventListener('click', () => toggleChatPanel());
document.getElementById('chatSubmit').addEventListener('click', sendChatMessage);
document.getElementById('chatQuestion').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.target.disabled) sendChatMessage();
});

function setScopeModalOpen(open) {
  const modal = document.getElementById('scopeModal');
  modal.classList.toggle('hidden', !open);
}
document.getElementById('scopeOpenBtn').addEventListener('click', () => setScopeModalOpen(true));
document.getElementById('scopeCloseBtn').addEventListener('click', () => setScopeModalOpen(false));
document.getElementById('scopeBackdrop').addEventListener('click', () => setScopeModalOpen(false));
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') setScopeModalOpen(false);
});

function initInfoTips() {
  const floater = document.createElement('div');
  floater.className = 'tooltip-floater';
  floater.setAttribute('role', 'tooltip');
  document.body.appendChild(floater);

  function showFor(target) {
    const text = target.getAttribute('data-tip');
    if (!text) return;
    floater.textContent = text;
    floater.classList.add('visible');
    const r = target.getBoundingClientRect();
    const ttRect = floater.getBoundingClientRect();
    const ttW = ttRect.width;
    const ttH = ttRect.height;
    const margin = 10;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let left = r.right + margin;
    if (left + ttW > vw - 8) left = r.left - margin - ttW;
    if (left < 8) left = 8;
    let top = r.top + r.height / 2 - ttH / 2;
    if (top < 8) top = 8;
    if (top + ttH > vh - 8) top = vh - 8 - ttH;
    floater.style.left = left + 'px';
    floater.style.top = top + 'px';
  }
  function hide() {
    floater.classList.remove('visible');
  }

  document.addEventListener('mouseover', (e) => {
    const tip = e.target.closest && e.target.closest('.info-tip');
    if (tip) showFor(tip);
  });
  document.addEventListener('mouseout', (e) => {
    const tip = e.target.closest && e.target.closest('.info-tip');
    if (tip) hide();
  });
  document.addEventListener('focusin', (e) => {
    const tip = e.target.closest && e.target.closest('.info-tip');
    if (tip) showFor(tip);
  });
  document.addEventListener('focusout', (e) => {
    const tip = e.target.closest && e.target.closest('.info-tip');
    if (tip) hide();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') hide();
  });
  window.addEventListener('scroll', hide, true);
  window.addEventListener('resize', hide);
}

initUserBar();
initTabs();
initInnerTabs();
initVizPanel();
initInfoTips();
removeInactiveParameterFields();
initSweepParams();
initTyreTab();
initLessons();
loadMetadata();
loadParametersAndConfig();
positionChatPanel();
window.addEventListener('resize', positionChatPanel);
