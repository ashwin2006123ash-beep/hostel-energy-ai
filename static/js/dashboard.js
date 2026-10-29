/* ==========================================================================
   Hostel Energy AI - Simplified Dashboard Controller
   ========================================================================== */

let simpleUsageChartInstance = null;
let currentTimeframe = "7d";

document.addEventListener("DOMContentLoaded", function() {
  loadDashboardData();
});

function setTimeframe(tf, btnElement) {
  currentTimeframe = tf;
  document.querySelectorAll(".btn-group .btn-toggle").forEach(b => b.classList.remove("active"));
  if (btnElement) btnElement.classList.add("active");
  loadDashboardData();
}

function onFilterChange() {
  loadDashboardData();
}

// Main load orchestrator
async function loadDashboardData() {
  await Promise.all([
    loadDashboardStats(),
    loadSimpleUsageChart(),
    loadFlaggedRooms()
  ]);
}

// --------------------------------------------------------------------------
// 1. Load the 4 Primary KPI Cards
// --------------------------------------------------------------------------
async function loadDashboardStats() {
  const blockFilter = document.getElementById("filter-block") ? document.getElementById("filter-block").value : "all";
  try {
    const res = await fetch(`/api/dashboard/stats?timeframe=${currentTimeframe}&block_id=${blockFilter}`);
    if (!res.ok) {
      setFallbackKpis();
      return;
    }
    const data = await res.json();

    // 1. Total Consumption
    const consEl = document.getElementById("kpi-consumption");
    if (consEl) {
      consEl.innerHTML = `${(data.total_consumption_kwh || 0).toLocaleString()} <span style="font-size: 1.1rem; color: var(--text-muted); font-weight: 500;">kWh</span>`;
    }
    const periodLabelEl = document.getElementById("kpi-period-label");
    if (periodLabelEl) {
      periodLabelEl.innerText = data.period_label || `Last ${currentTimeframe}`;
    }

    // 2. Estimated Bill
    const billEl = document.getElementById("kpi-bill");
    if (billEl) {
      billEl.innerText = `₹${(data.estimated_bill_inr || 0).toLocaleString()}`;
    }

    // 3. Rooms Requiring Investigation
    const flaggedEl = document.getElementById("kpi-flagged-rooms");
    if (flaggedEl) {
      flaggedEl.innerHTML = `${data.flagged_rooms_count || 0} <span style="font-size: 1.1rem; color: var(--text-muted); font-weight: 500;">Rooms</span>`;
    }
    const critEl = document.getElementById("kpi-critical-rooms");
    if (critEl) critEl.innerText = `${data.critical_rooms_count || 0} Critical`;
    const warnEl = document.getElementById("kpi-warning-rooms");
    if (warnEl) warnEl.innerText = `${data.warning_rooms_count || 0} Warning`;

    // 4. Estimated Potential Savings
    const savEl = document.getElementById("kpi-savings");
    if (savEl) {
      savEl.innerText = `₹${(data.potential_savings_inr || 0).toLocaleString()}`;
    }
    const savKwhEl = document.getElementById("kpi-savings-kwh");
    if (savKwhEl) {
      savKwhEl.innerText = `${(data.potential_savings_kwh || 0).toLocaleString()} kWh`;
    }
  } catch (e) {
    console.error("Failed to load dashboard stats:", e);
    setFallbackKpis();
  }
}

function setFallbackKpis() {
  const ids = ["kpi-consumption", "kpi-bill", "kpi-flagged-rooms", "kpi-savings"];
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerText = "No data available";
  });
}

// --------------------------------------------------------------------------
// 2. Simple Usage Chart (Actual vs Expected Baseline)
// --------------------------------------------------------------------------
async function loadSimpleUsageChart() {
  const blockFilter = document.getElementById("filter-block") ? document.getElementById("filter-block").value : "all";
  const canvas = document.getElementById("simpleUsageChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  try {
    const res = await fetch(`/api/readings/history?block_id=${blockFilter}&timeframe=${currentTimeframe}`);
    if (!res.ok) return;
    const data = await res.json();

    if (!data.timestamps || data.timestamps.length === 0) {
      return;
    }

    const labels = data.timestamps.map(t => {
      const parts = t.split(" ");
      return `${parts[0].slice(5)} ${parts[1].slice(0, 5)}`;
    });

    // Anomaly points overlay
    const anomalyPoints = [];
    if (data.anomalies) {
      data.anomalies.forEach((anom, idx) => {
        if (anom && (anom.severity === "CRITICAL" || anom.severity === "HIGH")) {
          anomalyPoints.push({
            x: labels[idx],
            y: data.actual_kw[idx]
          });
        }
      });
    }

    if (simpleUsageChartInstance) {
      simpleUsageChartInstance.destroy();
    }

    // Gradient fill for actual
    const gradientActual = ctx.createLinearGradient(0, 0, 0, 300);
    gradientActual.addColorStop(0, "rgba(56, 189, 248, 0.28)");
    gradientActual.addColorStop(1, "rgba(56, 189, 248, 0.0)");

    simpleUsageChartInstance = new Chart(ctx, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Actual Consumption (kW)",
            data: data.actual_kw,
            borderColor: "#38bdf8",
            backgroundColor: gradientActual,
            borderWidth: 2.2,
            tension: 0.3,
            fill: true,
            pointRadius: 0,
            pointHoverRadius: 5,
            pointHoverBackgroundColor: "#38bdf8"
          },
          {
            label: "Expected AI Baseline (kW)",
            data: data.expected_kw,
            borderColor: "#a855f7",
            borderWidth: 2,
            borderDash: [5, 4],
            tension: 0.3,
            fill: false,
            pointRadius: 0,
            pointHoverRadius: 5,
            pointHoverBackgroundColor: "#a855f7"
          },
          {
            label: "Flagged Excursions",
            data: anomalyPoints,
            type: "scatter",
            backgroundColor: "#f43f5e",
            borderColor: "#fff",
            borderWidth: 1.5,
            pointRadius: 6,
            pointHoverRadius: 8
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: "index",
          intersect: false
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "rgba(15, 23, 42, 0.95)",
            titleColor: "#f8fafc",
            bodyColor: "#94a3b8",
            borderColor: "rgba(255, 255, 255, 0.1)",
            borderWidth: 1,
            padding: 10,
            callbacks: {
              label: function(context) {
                if (context.dataset.label === "Flagged Excursions") {
                  return ` ⚠️ Anomaly Alert: ${context.parsed.y} kW`;
                }
                return ` ${context.dataset.label}: ${context.parsed.y} kW`;
              }
            }
          }
        },
        scales: {
          x: {
            grid: { color: "rgba(255, 255, 255, 0.04)" },
            ticks: {
              color: "#64748b",
              maxTicksLimit: 10,
              font: { size: 11 }
            }
          },
          y: {
            grid: { color: "rgba(255, 255, 255, 0.05)" },
            ticks: {
              color: "#64748b",
              font: { size: 11 },
              callback: val => `${val} kW`
            }
          }
        }
      }
    });

  } catch (e) {
    console.error("Failed to render simple usage chart:", e);
  }
}

// --------------------------------------------------------------------------
// 3. Prioritized Rooms Needing Attention
// --------------------------------------------------------------------------
async function loadFlaggedRooms() {
  const blockFilter = document.getElementById("filter-block") ? document.getElementById("filter-block").value : "all";
  const sevFilter = document.getElementById("table-filter-severity") ? document.getElementById("table-filter-severity").value : "all";
  const statusFilter = document.getElementById("table-filter-status") ? document.getElementById("table-filter-status").value : "pending";
  const tbody = document.getElementById("flagged-rooms-body");
  if (!tbody) return;

  try {
    let url = `/api/rooms?limit=15&offset=0`;
    if (blockFilter !== "all") url += `&block_id=${blockFilter}`;
    if (sevFilter !== "all") url += `&severity=${sevFilter}`;
    if (statusFilter !== "all") url += `&status=${statusFilter}`;

    const res = await fetch(url);
    if (!res.ok) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No data available.</td></tr>`;
      return;
    }
    const data = await res.json();
    const rooms = data.rooms || [];

    const badgeEl = document.getElementById("table-count-badge");
    if (badgeEl) badgeEl.innerText = `${rooms.length} Flagged`;

    if (rooms.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7" style="text-align: center; color: var(--text-secondary); padding: 2rem;">
            <div style="font-size: 1.1rem; margin-bottom: 0.35rem; color: var(--accent-emerald);">✓ All Rooms Clear</div>
            <div style="font-size: 0.82rem; color: var(--text-muted);">No flagged rooms currently matching selected filter criteria.</div>
          </td>
        </tr>
      `;
      return;
    }

    let rowsHtml = "";
    rooms.forEach(r => {
      // Severity badge
      let sevBadge = `<span class="badge badge-normal">${r.severity}</span>`;
      if (r.severity === "CRITICAL") {
        sevBadge = `<span class="badge badge-critical">CRITICAL</span>`;
      } else if (r.severity === "HIGH" || r.severity === "WARNING") {
        sevBadge = `<span class="badge badge-warning">WARNING</span>`;
      }

      // Occupancy badge
      let occBadge = `<span class="badge badge-normal" style="background: rgba(148, 163, 184, 0.15); color: #cbd5e1;">Unknown</span>`;
      const occLower = (r.occupancy_status || "").toLowerCase();
      if (occLower.includes("vacant")) {
        occBadge = `<span class="badge badge-warning" style="background: rgba(245, 158, 11, 0.15); color: #fbbf24;">Likely Vacant</span>`;
      } else if (occLower.includes("occupied")) {
        occBadge = `<span class="badge badge-normal" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8;">Occupied</span>`;
      }

      // Status selector
      const statusSelect = `
        <select class="select-custom status-pill-select" onchange="updateRoomStatus(${r.id}, this.value)" style="font-size: 0.78rem; padding: 0.25rem 0.5rem;">
          <option value="pending" ${r.status === 'pending' ? 'selected' : ''}>Pending</option>
          <option value="investigating" ${r.status === 'investigating' ? 'selected' : ''}>Investigating</option>
          <option value="resolved" ${r.status === 'resolved' ? 'selected' : ''}>Resolved</option>
        </select>
      `;

      rowsHtml += `
        <tr id="room-row-${r.id}">
          <td>
            <div style="font-weight: 700; color: #fff;">${r.room_number || 'Room 101'}</div>
            <div style="font-size: 0.75rem; color: var(--text-muted);">${r.block_id} • Floor ${r.room_number ? r.room_number.replace(/\D/g, '')[0] || '1' : '1'}</div>
          </td>
          <td>
            <div>
              <span style="font-weight: 700; color: #f43f5e;">${r.actual_kw.toFixed(1)} kW</span>
              <span style="color: var(--text-muted); font-size: 0.8rem;"> vs ${r.expected_kw.toFixed(1)} kW</span>
            </div>
            <div style="font-size: 0.75rem; color: var(--accent-amber); font-weight: 600;">
              +${r.residual_kw.toFixed(1)} kW excess
            </div>
          </td>
          <td>${occBadge}</td>
          <td>
            <div style="display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.25rem;">
              ${sevBadge}
            </div>
            <div style="font-size: 0.82rem; color: var(--text-secondary); max-width: 240px; line-height: 1.3;">
              ${r.primary_cause}
            </div>
          </td>
          <td>
            <div style="font-size: 0.82rem; color: #cbd5e1; max-width: 260px; line-height: 1.35;">
              ${r.recommended_action || 'Inspect room for unattended appliances'}
            </div>
          </td>
          <td>${statusSelect}</td>
          <td>
            <button class="btn btn-secondary btn-sm" onclick="openDiagnosticModal(${r.id})" style="font-size: 0.78rem; padding: 0.35rem 0.65rem;">
              Audit Details
            </button>
          </td>
        </tr>
      `;
    });

    tbody.innerHTML = rowsHtml;
  } catch (e) {
    console.error("Failed to load flagged rooms:", e);
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">Error loading flagged rooms.</td></tr>`;
  }
}

// Update room status
async function updateRoomStatus(anomalyId, newStatus) {
  try {
    const res = await fetch(`/api/anomalies/${anomalyId}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus, notes: `Status updated to ${newStatus} via Warden Dashboard` })
    });
    if (res.ok) {
      // Reload stats and rooms list to keep sync
      loadDashboardStats();
      if (newStatus === "resolved") {
        const row = document.getElementById(`room-row-${anomalyId}`);
        if (row) {
          row.style.opacity = "0.4";
          setTimeout(() => loadFlaggedRooms(), 600);
        }
      }
    }
  } catch (e) {
    console.error("Failed to update room status:", e);
  }
}
