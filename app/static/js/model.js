async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  return await res.json();
}

function fmt(x, digits = 4) {
  if (x === null || x === undefined) return "—";
  if (typeof x === "number") return x.toFixed(digits);
  return String(x);
}

function setHTML(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = html;
}

function rollingMAE(series, key, window) {
  const out = [];
  for (let i = 0; i < series.length; i++) {
    const start = Math.max(0, i - window + 1);
    const chunk = series.slice(start, i + 1).filter(r => r[key] !== null && r[key] !== undefined);
    if (!chunk.length) {
      out.push(null);
      continue;
    }
    const avg = chunk.reduce((s, r) => s + r[key], 0) / chunk.length;
    out.push(avg);
  }
  return out;
}

let chartActualPred = null;
let chartError = null;
let chartRolling = null;

function buildLineChart(canvasId, labels, datasets) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;

  return new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      animation: false,
      scales: {
        x: { display: true },
        y: { display: true }
      },
      plugins: {
        legend: { display: true }
      }
    }
  });
}

async function loadModelSection() {
  const summary = await fetchJSON("/model/summary");
  const history = await fetchJSON("/model/history?limit=300");

  // Info
  setHTML("model-info", `
    <div><b>Version:</b> ${summary.model_version}</div>
    <div><b>Window size:</b> ${summary.window_size ?? "—"}</div>
    <div><b>Ingest interval (min):</b> ${summary.ingest_interval_minutes ?? "—"}</div>
    <div><b>Last trained:</b> ${summary.last_trained_at ?? "—"}</div>
    <div><b>Last processed price id:</b> ${summary.last_processed_price_id ?? "—"}</div>
  `);

  // Performance
  const beats = summary.beats_baseline_50;
  const beatsText = (beats === null) ? "—" : (beats ? "YES" : "NO");
  setHTML("model-performance", `
    <div><b>Rolling MAE(50):</b> ${fmt(summary.rolling_mae_50, 2)}</div>
    <div><b>Baseline MAE(50):</b> ${fmt(summary.rolling_baseline_mae_50, 2)}</div>
    <div><b>Beats baseline (50):</b> ${beatsText}</div>
    <div><b>Trend:</b> ${summary.trend ?? "—"}</div>
    <hr/>
    <div><b>Rolling MAE(200):</b> ${fmt(summary.rolling_mae_200, 2)}</div>
    <div><b>Baseline MAE(200):</b> ${fmt(summary.rolling_baseline_mae_200, 2)}</div>
  `);

  // Prepare chart series
  // We'll chart using created_at as x labels (short)
  const labels = history.map(r => {
    const d = new Date(r.created_at);
    return d.toISOString().slice(11, 19); // HH:MM:SS
  });

  // Actual vs predicted:
  // y_true exists only after scoring; y_pred exists always
  const yPred = history.map(r => r.y_pred);
  const yTrue = history.map(r => r.y_true);

  // Error series
  const absErr = history.map(r => r.abs_error);
  const baseAbsErr = history.map(r => r.baseline_abs_error);

  // Rolling MAE
  const rModel = rollingMAE(history, "abs_error", 50);
  const rBase = rollingMAE(history, "baseline_abs_error", 50);

  // Destroy existing charts to avoid duplicates on refresh
  if (chartActualPred) chartActualPred.destroy();
  if (chartError) chartError.destroy();
  if (chartRolling) chartRolling.destroy();

  chartActualPred = buildLineChart("chart-actual-pred", labels, [
    { label: "Predicted", data: yPred, spanGaps: true },
    { label: "Actual", data: yTrue, spanGaps: true },
  ]);

  chartError = buildLineChart("chart-error", labels, [
    { label: "Abs Error (Model)", data: absErr, spanGaps: true },
    { label: "Abs Error (Baseline)", data: baseAbsErr, spanGaps: true },
  ]);

  chartRolling = buildLineChart("chart-rolling", labels, [
    { label: "Rolling MAE(50) Model", data: rModel, spanGaps: true },
    { label: "Rolling MAE(50) Baseline", data: rBase, spanGaps: true },
  ]);

  const completed = history
  .filter(r => r.y_true !== null && r.y_true !== undefined)
  .slice(-5);  // last 5 completed

const tbody = document.getElementById("last5-body");
if (tbody) {
  tbody.innerHTML = "";

  completed.forEach(r => {
    const tr = document.createElement("tr");

    const better =
      r.abs_error !== null &&
      r.baseline_abs_error !== null &&
      r.abs_error < r.baseline_abs_error;

    tr.innerHTML = `
      <td style="padding:6px">${new Date(r.observed_timestamp).toISOString().slice(11,19)}</td>
      <td style="padding:6px">$${r.y_pred?.toFixed(2)}</td>
      <td style="padding:6px">$${r.y_true?.toFixed(2)}</td>
      <td style="padding:6px">${r.abs_error?.toFixed(2)}</td>
      <td style="padding:6px">${r.baseline_abs_error?.toFixed(2)}</td>
      <td style="padding:6px; font-weight:600; color:${better ? '#22c55e' : '#ef4444'}">
        ${better ? "Yes" : "No"}
      </td>
    `;

    tbody.appendChild(tr);
  });
}
}

async function boot() {
  try {
    await loadModelSection();
  } catch (e) {
    console.error(e);
    setHTML("model-info", "Failed to load model info.");
    setHTML("model-performance", "Failed to load model performance.");
  }

  // refresh every 60s
  setInterval(async () => {
    try {
      await loadModelSection();
    } catch (e) {
      console.error(e);
    }
  }, 60000);
}

boot();