/* ==========================================================================
   Hostel Energy AI - AI Detective Controller
   ========================================================================== */

document.addEventListener("DOMContentLoaded", function() {
  loadDetectiveAnomalies();
});

function reloadAnomaliesList() {
  loadDetectiveAnomalies();
}

async function loadDetectiveAnomalies() {
  const sev = document.getElementById("filter-det-severity").value;
  const blk = document.getElementById("filter-det-block").value;
  const st = document.getElementById("filter-det-status").value;
  const tbody = document.getElementById("detective-table-body");
  const countLabel = document.getElementById("anomalies-count-label");

  if (!tbody) return;

  tbody.innerHTML = `<tr><td colspan="11" style="text-align: center; color: var(--text-muted); padding: 2rem;">Loading cases...</td></tr>`;

  try {
    let url = `/api/anomalies?limit=50&severity=${sev}&block_id=${blk}&status=${st}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error("Failed to load anomalies");
    const data = await res.json();

    countLabel.innerText = `Showing ${data.anomalies.length} of ${data.total} recorded cases`;

    if (data.anomalies.length === 0) {
      tbody.innerHTML = `<tr><td colspan="11" style="text-align: center; color: var(--text-muted); padding: 2rem;">No anomalies matching the selected filters.</td></tr>`;
      return;
    }

    // Compute average residual
    const totalResidual = data.anomalies.reduce((acc, a) => acc + a.residual_kw, 0);
    const avgRes = (totalResidual / data.anomalies.length).toFixed(1);
    const avgResEl = document.getElementById("det-avg-residual");
    if (avgResEl) avgResEl.innerHTML = `+${avgRes} <span style="font-size: 1rem; color: var(--text-secondary);">kW</span>`;

    let html = "";
    data.anomalies.forEach(a => {
      let sevBadge = `<span class="badge badge-low">LOW</span>`;
      if (a.severity === "CRITICAL") sevBadge = `<span class="badge badge-critical">CRITICAL</span>`;
      else if (a.severity === "HIGH") sevBadge = `<span class="badge badge-high">HIGH</span>`;
      else if (a.severity === "MEDIUM") sevBadge = `<span class="badge badge-medium">MEDIUM</span>`;

      let statusBadge = `<span style="font-size: 0.75rem; color: var(--text-secondary); background: rgba(255,255,255,0.05); padding: 0.2rem 0.5rem; border-radius: 4px;">${a.status}</span>`;
      if (a.status === "Investigating") statusBadge = `<span class="badge badge-medium">Investigating</span>`;
      else if (a.status === "Resolved") statusBadge = `<span class="badge badge-low">Resolved</span>`;
      else if (a.status === "False_Positive") statusBadge = `<span class="badge" style="background: rgba(148,163,184,0.15); color: #cbd5e1;">False Pos</span>`;

      html += `
        <tr>
          <td style="font-family: var(--font-mono); color: var(--text-muted); font-size: 0.78rem;">#${a.id}</td>
          <td style="font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-secondary);">${a.timestamp}</td>
          <td><strong>${a.block_id}</strong></td>
          <td style="font-weight: 600;">${a.actual_kw} kW</td>
          <td style="color: var(--accent-cyan);">${a.expected_kw} kW</td>
          <td style="color: var(--accent-rose); font-weight: 700;">+${a.residual_kw} kW</td>
          <td style="font-family: var(--font-mono); font-size: 0.8rem;">${(a.anomaly_score * 100).toFixed(0)}%</td>
          <td>${sevBadge}</td>
          <td style="font-size: 0.84rem; max-width: 250px;">${a.primary_cause}</td>
          <td>${statusBadge}</td>
          <td>
            <button class="btn btn-primary btn-sm" onclick="openDiagnosticModal(${a.id})">Inspect Evidence</button>
          </td>
        </tr>
      `;
    });

    tbody.innerHTML = html;

  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="11" style="text-align: center; color: var(--accent-rose); padding: 2rem;">Error: ${e.message}</td></tr>`;
  }
}
