/* ==========================================================================
   Hostel Energy AI - Fair League Controller
   ========================================================================== */

let secChartInstance = null;

document.addEventListener("DOMContentLoaded", function() {
  loadLeagueData();
  loadVerifiedSavings();
});

async function loadLeagueData() {
  const tbody = document.getElementById("league-table-body");
  if (!tbody) return;

  try {
    const res = await fetch("/api/league");
    if (!res.ok) throw new Error("Failed to load league standings");
    const data = await res.json();
    const standings = data.standings;

    let html = "";
    const chartLabels = [];
    const chartValues = [];
    const chartColors = [];

    standings.forEach(s => {
      let rankBadge = `<span style="font-weight: 800; font-size: 1.1rem; color: #fff;">#${s.rank}</span>`;
      let rankColor = "#38bdf8";
      if (s.rank === 1) {
        rankBadge = `<span style="font-size: 1.3rem;">🥇</span>`;
        rankColor = "#10b981";
      } else if (s.rank === 2) {
        rankBadge = `<span style="font-size: 1.3rem;">🥈</span>`;
        rankColor = "#06b6d4";
      } else if (s.rank === 3) {
        rankBadge = `<span style="font-size: 1.3rem;">🥉</span>`;
        rankColor = "#f59e0b";
      }

      chartLabels.push(s.block_id);
      chartValues.push(s.sec_kwh_per_occ_day);
      chartColors.push(rankColor);

      // Star string
      const stars = "★".repeat(s.star_rating) + "☆".repeat(5 - s.star_rating);

      // Badges
      let badgesHtml = s.badges.map(b => `<span class="badge badge-low" style="margin-right: 0.25rem;">${b.label}</span>`).join("");
      if (!badgesHtml) badgesHtml = `<span style="color: var(--text-muted); font-size: 0.78rem;">Standard</span>`;

      html += `
        <tr>
          <td style="text-align: center;">${rankBadge}</td>
          <td>
            <strong style="font-size: 0.95rem; color: #fff;">${s.block_id}</strong>
            <div style="font-size: 0.78rem; color: var(--text-muted);">${s.block_name}</div>
          </td>
          <td><span style="font-size: 0.78rem; color: var(--text-secondary);">${s.block_type}</span></td>
          <td style="font-size: 0.82rem; color: var(--text-secondary);">${s.capacity} cap • ${s.floor_area_sqm} m²</td>
          <td>
            <strong style="color: var(--accent-cyan); font-family: var(--font-mono); font-size: 0.95rem;">${s.sec_kwh_per_occ_day}</strong>
            <span style="font-size: 0.72rem; color: var(--text-muted);"> kWh/occ-day</span>
          </td>
          <td>
            <strong style="color: #fff; font-family: var(--font-mono);">${s.eui_kwh_per_sqm_month}</strong>
            <span style="font-size: 0.72rem; color: var(--text-muted);"> kWh/m²</span>
          </td>
          <td style="color: ${s.night_waste_ratio_pct > 18 ? 'var(--accent-rose)' : 'var(--text-secondary)'}; font-family: var(--font-mono);">
            ${s.night_waste_ratio_pct}%
          </td>
          <td style="color: #facc15; font-size: 0.95rem; letter-spacing: 2px;">${stars}</td>
          <td>
            <span style="font-family: var(--font-heading); font-size: 1.15rem; font-weight: 800; color: #fff;">
              ${s.composite_index}
            </span>
            <span style="font-size: 0.72rem; color: var(--text-muted);">/100</span>
          </td>
          <td>${badgesHtml}</td>
        </tr>
      `;
    });

    tbody.innerHTML = html;
    renderSecChart(chartLabels, chartValues, chartColors);

  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; color: var(--accent-rose); padding: 2rem;">Error: ${e.message}</td></tr>`;
  }
}

function renderSecChart(labels, values, colors) {
  const ctx = document.getElementById("secComparisonChart").getContext("2d");

  if (secChartInstance) {
    secChartInstance.destroy();
  }

  secChartInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [{
        label: "kWh / Occupant-Day",
        data: values,
        backgroundColor: colors,
        borderRadius: 4
      }]
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "rgba(17, 24, 39, 0.95)",
          callbacks: {
            label: item => ` Specific Energy: ${item.raw} kWh/occupant-day`
          }
        }
      },
      scales: {
        x: {
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: { color: "#94a3b8", callback: v => v + " kWh" }
        },
        y: {
          grid: { display: false },
          ticks: { color: "#fff", font: { weight: "600" } }
        }
      }
    }
  });
}

async function loadVerifiedSavings() {
  const container = document.getElementById("verified-actions-list");
  if (!container) return;

  try {
    const res = await fetch("/api/savings");
    if (!res.ok) return;
    const data = await res.json();

    let html = "";
    data.actions.forEach(a => {
      html += `
        <div style="background: rgba(0,0,0,0.25); border: 1px solid var(--border-glass); border-radius: var(--radius-sm); padding: 0.85rem 1rem;">
          <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.35rem;">
            <div>
              <strong style="color: #fff; font-size: 0.9rem;">${a.action_title}</strong>
              <div style="font-size: 0.75rem; color: var(--text-muted);">${a.block_id} • Implemented ${a.implementation_date.slice(0, 10)}</div>
            </div>
            <span class="badge badge-verified">Verified</span>
          </div>
          <div style="display: flex; gap: 1.25rem; margin-top: 0.5rem; font-size: 0.82rem;">
            <div>
              <span style="color: var(--text-muted);">Adjusted Baseline:</span>
              <strong style="color: var(--text-secondary);"> ${a.weather_adjusted_baseline_kwh.toLocaleString()} kWh</strong>
            </div>
            <div>
              <span style="color: var(--text-muted);">Verified Saved:</span>
              <strong style="color: var(--accent-emerald);"> ${a.verified_savings_kwh.toLocaleString()} kWh (₹${a.verified_cost_saved_inr.toLocaleString()})</strong>
            </div>
          </div>
        </div>
      `;
    });

    container.innerHTML = html;
  } catch (e) {
    console.error("Failed to load verified actions", e);
  }
}
