/* ==========================================================================
   Hostel Energy AI - Interactive Digital Twin Controller
   ========================================================================== */

let twinData = null;
let activeBlockId = "Block-A";
let activeFloorNumber = 1;

document.addEventListener("DOMContentLoaded", function() {
  loadDigitalTwinData();
});

async function loadDigitalTwinData() {
  const container = document.getElementById("blocks-container");
  if (!container) return;

  try {
    const res = await fetch("/api/digital-twin/status");
    if (!res.ok) throw new Error("Failed to load digital twin status");
    twinData = await res.json();

    renderBlockCards();
    updateFloorDrilldown();
  } catch (e) {
    container.innerHTML = `<div style="grid-column: span 2; color: var(--accent-rose); text-align: center; padding: 2rem;">Error: ${e.message}</div>`;
  }
}

function renderBlockCards() {
  const container = document.getElementById("blocks-container");
  if (!container || !twinData) return;

  let html = "";
  for (const [blkId, blk] of Object.entries(twinData.blocks)) {
    const hasAnomaly = blk.active_anomaly !== null;
    const cardClass = hasAnomaly && blk.active_anomaly.severity === "CRITICAL" ? "glass-panel block-card has-critical" : "glass-panel block-card";

    let anomalyBadge = "";
    if (hasAnomaly) {
      let bClass = blk.active_anomaly.severity === "CRITICAL" ? "badge-critical" : "badge-high";
      anomalyBadge = `<span class="badge ${bClass}">⚠️ ${blk.active_anomaly.severity}: ${blk.active_anomaly.cause}</span>`;
    } else {
      anomalyBadge = `<span class="badge badge-low">Normal Baseline</span>`;
    }

    // Generate Floor Rows
    let floorsHtml = "";
    blk.floors.forEach(fl => {
      let fillCol = "var(--accent-cyan)";
      if (fl.heat_level_pct >= 75) fillCol = "var(--accent-rose)";
      else if (fl.heat_level_pct >= 50) fillCol = "var(--accent-amber)";

      floorsHtml += `
        <div class="floor-row" onclick="selectBlockFloor('${blkId}', ${fl.floor_number})" style="cursor: pointer;">
          <div>
            <strong style="font-size: 0.88rem; color: #fff;">Floor ${fl.floor_number}</strong>
            <div style="font-size: 0.75rem; color: var(--text-muted);">
              ${fl.occupancy} Occupants • ${fl.power_density_w_sqm} W/m²
            </div>
            <div class="floor-heat-bar" style="width: 140px;">
              <div class="floor-heat-fill" style="width: ${fl.heat_level_pct}%; background: ${fillCol};"></div>
            </div>
          </div>
          <div style="text-align: right;">
            <div style="font-family: var(--font-heading); font-size: 1.1rem; font-weight: 700; color: #fff;">
              ${fl.power_kw} kW
            </div>
            <span style="font-size: 0.72rem; color: ${fillCol}; font-weight: 600;">Heat Index: ${fl.heat_level_pct}%</span>
          </div>
        </div>
      `;
    });

    html += `
      <div class="${cardClass}" id="card-${blkId}" style="border: ${blkId === activeBlockId ? '1px solid var(--accent-cyan)' : '1px solid var(--border-glass)'};">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1rem;">
          <div>
            <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.25rem;">
              <h3 style="font-size: 1.25rem;">${blkId}: ${blk.name}</h3>
              <span style="font-size: 0.75rem; color: var(--text-secondary); background: rgba(255,255,255,0.05); padding: 0.2rem 0.5rem; border-radius: 4px;">${blk.type}</span>
            </div>
            <div style="font-size: 0.8rem; color: var(--text-secondary);">
              Capacity: ${blk.capacity} students (${blk.floors_count} floors) • Occupancy: ${blk.current_occupancy} (${blk.occupancy_rate_pct}%)
            </div>
          </div>
          <div style="text-align: right;">
            <div style="font-family: var(--font-heading); font-size: 1.7rem; font-weight: 800; color: var(--accent-cyan); line-height: 1;">
              ${blk.current_power_kw} <span style="font-size: 0.9rem; color: var(--text-secondary);">kW</span>
            </div>
            <div style="margin-top: 0.35rem;">${anomalyBadge}</div>
          </div>
        </div>

        <div style="margin-top: 1rem;">
          <h4 style="font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); margin-bottom: 0.5rem;">
            Floor Heat Map & Power Distribution
          </h4>
          ${floorsHtml}
        </div>
      </div>
    `;
  }

  container.innerHTML = html;
}

function selectBlockFloor(blkId, floorNum) {
  activeBlockId = blkId;
  activeFloorNumber = floorNum;
  renderBlockCards();
  updateFloorDrilldown();
}

function selectFloor(floorNum, btnElement) {
  activeFloorNumber = floorNum;
  document.querySelectorAll("#floor-tabs .btn-toggle").forEach(b => b.classList.remove("active"));
  if (btnElement) btnElement.classList.add("active");
  updateFloorDrilldown();
}

function updateFloorDrilldown() {
  if (!twinData || !twinData.blocks[activeBlockId]) return;

  const blk = twinData.blocks[activeBlockId];
  document.getElementById("selected-block-title").innerText = `${activeBlockId}: ${blk.name} — Floor ${activeFloorNumber} Spatial Telemetry`;

  // Update tabs to match floors_count
  const tabsContainer = document.getElementById("floor-tabs");
  let tabsHtml = "";
  for (let fl = 1; fl <= blk.floors_count; fl++) {
    const isActive = fl === activeFloorNumber ? "active" : "";
    tabsHtml += `<button class="btn-toggle ${isActive}" onclick="selectFloor(${fl}, this)">Floor ${fl}</button>`;
  }
  tabsContainer.innerHTML = tabsHtml;

  // Retrieve current floor data
  const floorData = blk.floors.find(f => f.floor_number === activeFloorNumber) || blk.floors[0];
  const flKw = floorData.power_kw;

  // Synthesize zone proportions
  const dormKw = (flKw * 0.48).toFixed(1);
  const studyKw = (flKw * 0.22).toFixed(1);
  const corrKw = (flKw * 0.30).toFixed(1);

  document.getElementById("zone-dorm-kw").innerText = `${dormKw} kW`;
  document.getElementById("zone-study-kw").innerText = `${studyKw} kW`;
  document.getElementById("zone-corridor-kw").innerText = `${corrKw} kW`;

  document.getElementById("zone-dorm-bar").style.width = `${Math.min(100, flKw * 18)}%`;
  document.getElementById("zone-study-bar").style.width = `${Math.min(100, flKw * 12)}%`;
  document.getElementById("zone-corridor-bar").style.width = `${Math.min(100, flKw * 15)}%`;
}
