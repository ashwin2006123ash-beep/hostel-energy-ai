/* ==========================================================================
   Hostel Energy AI - What-If Simulator Controller
   ========================================================================== */

let simChartInstance = null;
let simDebounceTimer = null;

document.addEventListener("DOMContentLoaded", function() {
  runSimulation();
});

function updateSliderVal(id, val, suffix) {
  document.getElementById(`val-${id}`).innerText = `${val}${suffix}`;
  
  clearTimeout(simDebounceTimer);
  simDebounceTimer = setTimeout(() => {
    runSimulation();
  }, 250);
}

async function runSimulation() {
  const emptyCutoff = parseFloat(document.getElementById("input-empty-cutoff").value);
  const ledRetrofit = parseFloat(document.getElementById("input-led-retrofit").value);
  const fanEco = parseFloat(document.getElementById("input-fan-eco").value);
  const solarKwp = parseFloat(document.getElementById("input-solar-kwp").value);
  const curfewEnabled = document.getElementById("toggle-curfew").checked;
  const geyserEnabled = document.getElementById("toggle-geysers").checked;

  const payload = {
    empty_room_cutoff_pct: emptyCutoff,
    led_retrofit_pct: ledRetrofit,
    fan_eco_regulation_pct: fanEco,
    solar_pv_kwp: solarKwp,
    curfew_cutoff_enabled: curfewEnabled,
    geyser_timer_enabled: geyserEnabled
  };

  try {
    const res = await fetch("/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error("Simulation calculation failed");
    const data = await res.json();

    const s = data.savings;
    document.getElementById("sim-kwh-saved").innerHTML = `${s.monthly_kwh.toLocaleString()} <span style="font-size: 1rem; color: var(--text-secondary);">kWh</span>`;
    document.getElementById("sim-pct-saved").innerText = `${s.percentage_reduction}% total consumption reduction`;
    document.getElementById("sim-annual-cost").innerText = `₹${s.annual_cost_inr.toLocaleString()}`;
    document.getElementById("sim-monthly-cost").innerText = `₹${s.monthly_cost_inr.toLocaleString()} saved / month`;
    document.getElementById("sim-co2-tonnes").innerHTML = `${s.annual_co2_tonnes} <span style="font-size: 1rem; color: var(--text-secondary);">T/yr</span>`;
    document.getElementById("sim-monthly-co2").innerText = `${s.monthly_co2_kg.toLocaleString()} kg CO₂e / mo`;
    document.getElementById("sim-capex").innerText = `₹${s.estimated_capex_inr.toLocaleString()}`;
    document.getElementById("sim-payback").innerText = `${s.payback_months} Months`;

    // Render ECM components
    const compContainer = document.getElementById("ecm-components-list");
    let compHtml = "";
    for (const [key, comp] of Object.entries(data.components)) {
      compHtml += `
        <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.25); border: 1px solid var(--border-glass); border-radius: var(--radius-sm); padding: 0.75rem 1rem;">
          <div>
            <strong style="font-size: 0.88rem; color: #fff;">${comp.name}</strong>
            <div style="font-size: 0.75rem; color: var(--text-muted);">${comp.description}</div>
          </div>
          <div style="text-align: right;">
            <div style="font-family: var(--font-mono); font-weight: 700; color: var(--accent-emerald); font-size: 1rem;">
              -${comp.kwh_saved.toLocaleString()} kWh
            </div>
            <span style="font-size: 0.72rem; color: var(--text-secondary);">Monthly Offset</span>
          </div>
        </div>
      `;
    }
    compContainer.innerHTML = compHtml;

    // Render comparison chart
    renderComparisonChart(data.block_breakdown);

  } catch (e) {
    console.error("Simulation error", e);
  }
}

function renderComparisonChart(blockBreakdown) {
  const ctx = document.getElementById("simComparisonChart").getContext("2d");

  const labels = [];
  const baseKwh = [];
  const projKwh = [];

  for (const [blkId, blk] of Object.entries(blockBreakdown)) {
    labels.push(blkId);
    baseKwh.push(blk.base_kwh);
    projKwh.push(blk.projected_kwh);
  }

  if (simChartInstance) {
    simChartInstance.destroy();
  }

  simChartInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Current Baseline (kWh)",
          data: baseKwh,
          backgroundColor: "rgba(148, 163, 184, 0.4)",
          borderColor: "#94a3b8",
          borderWidth: 1,
          borderRadius: 4
        },
        {
          label: "Simulated Post-ECM (kWh)",
          data: projKwh,
          backgroundColor: "rgba(16, 185, 129, 0.6)",
          borderColor: "#10b981",
          borderWidth: 1,
          borderRadius: 4
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "top",
          labels: { color: "#94a3b8", font: { size: 10 } }
        },
        tooltip: {
          backgroundColor: "rgba(17, 24, 39, 0.95)"
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: "#94a3b8" }
        },
        y: {
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: { color: "#94a3b8", callback: v => v + " kWh" }
        }
      }
    }
  });
}
