/* ==========================================================================
   Hostel Energy AI - Live Room Fleet Grid Controller
   ========================================================================== */

let allLiveRooms = [];

document.addEventListener("DOMContentLoaded", function() {
  loadLiveRoomsGrid();
  // Auto-refresh when user switches back to this tab
  window.addEventListener("focus", loadLiveRoomsGrid);
});

async function loadLiveRoomsGrid() {
  const block = document.getElementById("grid-filter-block").value;
  const state = document.getElementById("grid-filter-state").value;
  const switchFilter = document.getElementById("grid-filter-switch") ? document.getElementById("grid-filter-switch").value : "all";
  const occupancy = document.getElementById("grid-filter-occupancy").value;
  const container = document.getElementById("live-rooms-grid");
  if (!container) return;

  try {
    let url = `/api/rooms/live?`;
    if (block !== "all") url += `&block_id=${block}`;
    if (state !== "all") url += `&room_state=${state}`;
    if (switchFilter !== "all") url += `&switch_state=${switchFilter}`;
    if (occupancy !== "all") url += `&occupancy_state=${occupancy}`;

    const res = await fetch(url);
    if (!res.ok) {
      container.innerHTML = `<div style="grid-column: 1 / -1; padding: 2rem; text-align: center; color: var(--text-muted);">Failed to load rooms.</div>`;
      return;
    }
    const data = await res.json();
    allLiveRooms = data.rooms || [];
    renderRoomCards(allLiveRooms);
  } catch (e) {
    console.error("Failed to load live rooms:", e);
    container.innerHTML = `<div style="grid-column: 1 / -1; padding: 2rem; text-align: center; color: var(--text-muted);">Error fetching live telemetry.</div>`;
  }
}

function onGridSearch() {
  const query = (document.getElementById("grid-search").value || "").trim().toLowerCase();
  if (!query) {
    renderRoomCards(allLiveRooms);
    return;
  }
  const filtered = allLiveRooms.filter(r => {
    return (r.room_id || "").toLowerCase().includes(query) ||
           (r.room_number || "").toLowerCase().includes(query) ||
           (r.block_id || "").toLowerCase().includes(query) ||
           (r.room_state || "").toLowerCase().includes(query) ||
           (r.effective_switch_state || "").toLowerCase().includes(query);
  });
  renderRoomCards(filtered);
}

function renderRoomCards(rooms) {
  const container = document.getElementById("live-rooms-grid");
  if (!container) return;

  if (rooms.length === 0) {
    container.innerHTML = `
      <div style="grid-column: 1 / -1; padding: 3rem; text-align: center; color: var(--text-muted);">
        No rooms found matching the current filter criteria.
      </div>
    `;
    return;
  }

  let html = "";
  rooms.forEach(r => {
    const isTripped = r.room_state === "TRIPPED_SIMULATED";
    const isManualLocked = r.manual_off_lock === 1;
    const isSwitchOn = (r.effective_switch_state || "ON") === "ON";

    // Main Switch Indicator Badge
    let switchBadge = `<span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); font-size: 0.7rem;">⚡ SWITCH ON</span>`;
    if (isManualLocked) {
      switchBadge = `<span class="badge" style="background: rgba(245, 158, 11, 0.18); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.45); font-size: 0.7rem;">🔒 SWITCH OFF (LOCKED)</span>`;
    } else if (!isSwitchOn) {
      switchBadge = `<span class="badge" style="background: rgba(239, 68, 68, 0.18); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.5); font-size: 0.7rem;">🛑 SWITCH OFF (TRIPPED)</span>`;
    }
    
    // Status Badge
    let stateBadge = `<span class="badge badge-state-normal">● NORMAL</span>`;
    if (r.room_state === "TRIPPED_SIMULATED") {
      stateBadge = `<span class="badge badge-state-trip">🛑 TRIPPED</span>`;
    } else if (r.room_state === "MANUAL_OFF") {
      stateBadge = `<span class="badge" style="background: rgba(244, 63, 94, 0.18); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.35);">⏻ MANUAL OFF</span>`;
    } else if (r.room_state === "TRIP_PENDING") {
      stateBadge = `<span class="badge badge-state-warning">⚠️ TRIP PENDING</span>`;
    } else if (r.room_state === "HIGH_USAGE") {
      stateBadge = `<span class="badge badge-state-warning">⚡ HIGH USAGE</span>`;
    } else if (r.room_state === "ANOMALY_DETECTED") {
      stateBadge = `<span class="badge badge-state-warning">🔍 ANOMALY</span>`;
    } else if (r.room_state === "SENSOR_OFFLINE") {
      stateBadge = `<span class="badge badge-state-offline">● SENSOR OFFLINE</span>`;
    } else if (r.room_state === "DATA_STALE") {
      stateBadge = `<span class="badge badge-state-warning">⏱️ DATA STALE</span>`;
    }

    // Occupancy
    let occBadge = `<span class="badge badge-normal" style="background: rgba(56, 189, 248, 0.12); color: #38bdf8;">Occupied</span>`;
    if ((r.occupancy_state || "").toLowerCase().includes("vacant")) {
      occBadge = `<span class="badge badge-warning" style="background: rgba(245, 158, 11, 0.12); color: #fbbf24;">Likely Vacant</span>`;
    } else if ((r.occupancy_state || "").toLowerCase().includes("unknown")) {
      occBadge = `<span class="badge badge-normal" style="background: rgba(148, 163, 184, 0.12); color: #cbd5e1;">Unknown</span>`;
    }

    html += `
      <a href="/rooms/${r.room_id}" class="room-card ${(!isSwitchOn || isTripped) ? 'is-tripped' : ''}">
        <div>
          <!-- Header -->
          <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.85rem;">
            <div>
              <div style="font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; font-weight: 600;">
                ${r.block_id} • Floor ${r.floor || 1}
              </div>
              <h3 style="font-size: 1.25rem; font-weight: 800; color: #fff; margin-top: 0.15rem;">
                ${r.room_number} <span style="font-size: 0.78rem; color: var(--text-muted); font-family: var(--font-mono);">(${r.room_id})</span>
              </h3>
            </div>
            <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 0.35rem;">
              ${switchBadge}
              ${stateBadge}
            </div>
          </div>

          <!-- Occupancy & Relay Status -->
          <div style="display: flex; gap: 0.45rem; align-items: center; margin-bottom: 1rem; flex-wrap: wrap;">
            ${occBadge}
            <span style="font-size: 0.74rem; color: var(--text-muted); font-family: var(--font-mono);">
              Relay: <strong style="color: ${r.relay_state === 'TRIPPED_SIMULATED' ? '#f87171' : (r.relay_state === 'OPEN_MANUAL' ? '#fbbf24' : 'var(--accent-emerald)')};">${r.relay_state}</strong>
            </span>
          </div>

          <!-- Live Power Large Display -->
          <div style="background: rgba(10, 15, 28, 0.65); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 8px; padding: 0.85rem; margin-bottom: 1rem; text-align: center;">
            <div style="font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase;">Active Power vs Threshold</div>
            <div style="font-size: 1.85rem; font-weight: 800; color: ${r.power_w > r.threshold_w ? '#f87171' : 'var(--accent-cyan)'}; font-family: var(--font-heading); margin-top: 0.2rem;">
              ${r.power_w} <span style="font-size: 1rem; font-weight: 500; color: var(--text-muted);">W</span>
            </div>
            <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.2rem;">
              Limit: <strong>${r.threshold_w} W</strong> (Vacant: <strong>${r.empty_threshold_w} W</strong>)
            </div>
          </div>

          <!-- Detailed Electrical Matrix -->
          <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.35rem; font-size: 0.72rem; text-align: center; margin-bottom: 0.85rem;">
            <div style="background: rgba(255, 255, 255, 0.03); padding: 0.4rem 0.2rem; border-radius: 4px;">
              <div style="color: var(--text-muted);">Voltage</div>
              <div style="font-weight: 700; color: #fff; margin-top: 0.15rem;">${r.voltage_v || '--'} V</div>
            </div>
            <div style="background: rgba(255, 255, 255, 0.03); padding: 0.4rem 0.2rem; border-radius: 4px;">
              <div style="color: var(--text-muted);">Current</div>
              <div style="font-weight: 700; color: #fff; margin-top: 0.15rem;">${r.current_a || '--'} A</div>
            </div>
            <div style="background: rgba(255, 255, 255, 0.03); padding: 0.4rem 0.2rem; border-radius: 4px;">
              <div style="color: var(--text-muted);">Energy</div>
              <div style="font-weight: 700; color: #fff; margin-top: 0.15rem;">${r.energy_kwh || '0'} kWh</div>
            </div>
            <div style="background: rgba(255, 255, 255, 0.03); padding: 0.4rem 0.2rem; border-radius: 4px;">
              <div style="color: var(--text-muted);">PF</div>
              <div style="font-weight: 700; color: #fff; margin-top: 0.15rem;">${r.power_factor || '0.95'}</div>
            </div>
          </div>
        </div>

        <!-- Footer: Switch action & Sensor update timestamp -->
        <div style="border-top: 1px solid rgba(255, 255, 255, 0.06); padding-top: 0.75rem; display: flex; justify-content: space-between; align-items: center; font-size: 0.74rem; color: var(--text-muted);">
          <span>By: <strong style="color: #cbd5e1;">${(r.last_switch_by || 'System').split(' ')[0]}</strong></span>
          <span style="color: var(--accent-cyan); font-weight: 600;">Main Switch Control &rarr;</span>
        </div>
      </a>
    `;
  });

  container.innerHTML = html;
}
