/* ==========================================================================
   Hostel Energy AI - Live Room Fleet Grid & Dynamic Simulation Controller
   ========================================================================== */

let allLiveRooms = [];
let simStatus = {
  running: true,
  paused: false,
  interval_seconds: 10.0,
  tick_count: 0,
  next_update_seconds: 10.0
};
let countdownInterval = null;
let lastServerFetchTime = Date.now();

document.addEventListener("DOMContentLoaded", function() {
  loadLiveRoomsGrid();
  startCountdownTicker();

  // Auto-refresh and resync when user switches back to this tab
  window.addEventListener("focus", function() {
    loadLiveRoomsGrid();
  });
});

function startCountdownTicker() {
  if (countdownInterval) clearInterval(countdownInterval);
  countdownInterval = setInterval(() => {
    if (!simStatus.paused && simStatus.running) {
      if (simStatus.next_update_seconds > 0) {
        simStatus.next_update_seconds = Math.max(0, (simStatus.next_update_seconds - 1));
      }
      updateCountdownDisplay();
      if (simStatus.next_update_seconds <= 0) {
        // Time for next simulated update
        loadLiveRoomsGrid();
      }
    }
  }, 1000);
}

function updateCountdownDisplay() {
  const tickerEl = document.getElementById("sim-countdown-ticker");
  if (tickerEl) {
    if (simStatus.paused) {
      tickerEl.innerText = "Paused";
      tickerEl.style.color = "#fbbf24";
    } else {
      tickerEl.innerText = `~${Math.ceil(simStatus.next_update_seconds)}s`;
      tickerEl.style.color = "var(--accent-cyan)";
    }
  }

  const cycleCountEl = document.getElementById("sim-cycle-count");
  if (cycleCountEl) {
    cycleCountEl.innerText = simStatus.tick_count || 0;
  }

  const badgeEl = document.getElementById("sim-status-badge");
  const toggleBtnText = document.getElementById("sim-toggle-text");
  const toggleIcon = document.getElementById("sim-toggle-icon");

  if (badgeEl && toggleBtnText && toggleIcon) {
    if (simStatus.paused) {
      badgeEl.className = "badge";
      badgeEl.style.background = "rgba(245, 158, 11, 0.2)";
      badgeEl.style.color = "#fbbf24";
      badgeEl.style.borderColor = "rgba(245, 158, 11, 0.4)";
      badgeEl.innerHTML = `<span style="display: inline-block; width: 6px; height: 6px; background: #fbbf24; border-radius: 50%; margin-right: 4px;"></span> PAUSED`;

      toggleBtnText.innerText = "Resume Simulation";
      toggleIcon.innerText = "▶";
    } else {
      badgeEl.className = "badge";
      badgeEl.style.background = "rgba(16, 185, 129, 0.2)";
      badgeEl.style.color = "#34d399";
      badgeEl.style.borderColor = "rgba(16, 185, 129, 0.4)";
      badgeEl.innerHTML = `<span style="display: inline-block; width: 6px; height: 6px; background: #34d399; border-radius: 50%; margin-right: 4px;"></span> RUNNING (10s Cycle)`;

      toggleBtnText.innerText = "Pause Simulation";
      toggleIcon.innerText = "⏸";
    }
  }
}

async function loadLiveRoomsGrid() {
  const blockEl = document.getElementById("grid-filter-block");
  const stateEl = document.getElementById("grid-filter-state");
  const switchFilterEl = document.getElementById("grid-filter-switch");
  const occupancyEl = document.getElementById("grid-filter-occupancy");
  const container = document.getElementById("live-rooms-grid");
  if (!container) return;

  const block = blockEl ? blockEl.value : "all";
  const state = stateEl ? stateEl.value : "all";
  const switchFilter = switchFilterEl ? switchFilterEl.value : "all";
  const occupancy = occupancyEl ? occupancyEl.value : "all";

  try {
    let url = `/api/rooms/live?`;
    if (block !== "all") url += `&block_id=${encodeURIComponent(block)}`;
    if (state !== "all") url += `&room_state=${encodeURIComponent(state)}`;
    if (switchFilter !== "all") url += `&switch_state=${encodeURIComponent(switchFilter)}`;
    if (occupancy !== "all") url += `&occupancy_state=${encodeURIComponent(occupancy)}`;

    const res = await fetch(url);
    if (!res.ok) {
      container.innerHTML = `<div style="grid-column: 1 / -1; padding: 2rem; text-align: center; color: var(--text-muted);">Failed to load rooms.</div>`;
      return;
    }
    const data = await res.json();
    allLiveRooms = data.rooms || [];

    if (data.simulation) {
      simStatus = Object.assign({}, simStatus, data.simulation);
      updateCountdownDisplay();
    }

    onGridSearch();
  } catch (e) {
    console.error("Failed to load live rooms:", e);
    container.innerHTML = `<div style="grid-column: 1 / -1; padding: 2rem; text-align: center; color: var(--text-muted);">Error fetching live telemetry.</div>`;
  }
}

function onGridSearch() {
  const queryEl = document.getElementById("grid-search");
  const query = queryEl ? (queryEl.value || "").trim().toLowerCase() : "";
  if (!query) {
    renderRoomCards(allLiveRooms);
    return;
  }
  const filtered = allLiveRooms.filter(r => {
    return (r.room_id || "").toLowerCase().includes(query) ||
           (r.room_number || "").toLowerCase().includes(query) ||
           (r.block_id || "").toLowerCase().includes(query) ||
           (r.room_state || "").toLowerCase().includes(query) ||
           (r.effective_switch_state || "").toLowerCase().includes(query) ||
           (r.simulation_profile || "").toLowerCase().includes(query);
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
    const isOffline = r.sensor_status === "OFFLINE" || r.is_offline === true;
    const isTripped = r.room_state === "TRIPPED_SIMULATED" || r.room_state === "TRIPPED_CRITICAL";
    const isManualLocked = r.manual_off_lock === 1;
    const isManualOff = r.room_state === "MANUAL_OFF" || (isManualLocked && !isTripped);
    const isOptimized = r.optimization_state === "OPTIMIZED";
    const isSwitchOn = (r.effective_switch_state || "ON") === "ON";
    const simProfile = r.simulation_profile || "NORMAL_OCCUPIED";

    // Card boundary styling
    let cardClass = "room-card";
    if (isTripped) cardClass += " is-tripped";
    else if (isManualOff) cardClass += " is-manual-off";
    else if (isOffline) cardClass += " is-offline";
    else if (isOptimized) cardClass += " is-optimized";

    // Main Switch Indicator Badge
    let switchBadge = `<span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); font-size: 0.7rem;">⚡ SWITCH ON</span>`;
    if (isManualLocked) {
      switchBadge = `<span class="badge" style="background: rgba(245, 158, 11, 0.18); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.45); font-size: 0.7rem;">🔒 SWITCH OFF (LOCKED)</span>`;
    } else if (!isSwitchOn) {
      switchBadge = `<span class="badge" style="background: rgba(239, 68, 68, 0.18); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.5); font-size: 0.7rem;">🛑 SWITCH OFF (TRIPPED)</span>`;
    }
    
    // Status Badge
    let stateBadge = `<span class="badge badge-state-normal">● NORMAL</span>`;
    if (r.room_state === "TRIPPED_CRITICAL") {
      stateBadge = `<span class="badge badge-state-trip">🛑 CRITICAL TRIP</span>`;
    } else if (r.room_state === "TRIPPED_SIMULATED") {
      stateBadge = `<span class="badge badge-state-trip">🛑 TRIPPED</span>`;
    } else if (r.room_state === "MANUAL_OFF") {
      stateBadge = `<span class="badge badge-state-manual-off">⏻ MANUAL OFF</span>`;
    } else if (r.optimization_state === "OPTIMIZED") {
      stateBadge = `<span class="badge badge-state-optimized">🌱 OPTIMIZED</span>`;
    } else if (r.optimization_state === "OPTIMIZATION_PARTIAL") {
      stateBadge = `<span class="badge badge-state-partial">⚡ OPTIMIZING (PARTIAL)</span>`;
    } else if (r.optimization_state === "OPTIMIZATION_FAILED") {
      stateBadge = `<span class="badge badge-state-failed">⚠️ OPTIMIZATION FAILED</span>`;
    } else if (r.room_state === "TRIP_PENDING") {
      stateBadge = `<span class="badge badge-state-warning">⏳ TRIP PENDING</span>`;
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

    // Sensor Status Indicator
    const sensorBadge = isOffline 
      ? `<span class="badge" style="background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.35); font-size: 0.68rem;">Sensor: OFFLINE</span>`
      : `<span class="badge" style="background: rgba(16, 185, 129, 0.12); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); font-size: 0.68rem;">Sensor: ONLINE</span>`;

    // Power & Fluctuation Metrics Display
    let powerDisplayHtml = "";
    if (isOffline) {
      powerDisplayHtml = `
        <div style="font-size: 1.85rem; font-weight: 800; color: #94a3b8; font-family: var(--font-heading); margin-top: 0.2rem;">
          -- <span style="font-size: 1rem; font-weight: 500; color: var(--text-muted);">W</span>
        </div>
        <div style="font-size: 0.72rem; color: #94a3b8; margin-top: 0.25rem;">
          Previous: <strong>--</strong> • Change: <strong>--</strong>
        </div>
        <div style="font-size: 0.72rem; color: #f87171; margin-top: 0.2rem;">
          ⚠️ Sensor node OFFLINE (Telemetry unavailable)
        </div>
      `;
    } else {
      const isOver = r.power_w > r.threshold_w;
      const prevW = typeof r.previous_power_w === "number" ? r.previous_power_w : r.power_w;
      const changeW = typeof r.power_change_w === "number" ? r.power_change_w : 0.0;
      const changePct = typeof r.power_change_pct === "number" ? r.power_change_pct : 0.0;

      // Visual Fluctuation indicator
      let fluctuationHtml = "";
      if (changeW > 0) {
        fluctuationHtml = `<span style="color: #fbbf24; font-weight: 700;">▲ +${changeW.toFixed(1)} W (+${changePct.toFixed(1)}%)</span>`;
      } else if (changeW < 0) {
        fluctuationHtml = `<span style="color: #34d399; font-weight: 700;">▼ ${changeW.toFixed(1)} W (${changePct.toFixed(1)}%)</span>`;
      } else {
        fluctuationHtml = `<span style="color: #94a3b8; font-weight: 600;">= 0.0 W (0.0%)</span>`;
      }

      const excessText = (r.excess_power_w && r.excess_power_w > 0) 
        ? `<span style="color: #fbbf24; font-weight: 700;">(+${r.excess_power_w} W Excess)</span>` 
        : "";

      powerDisplayHtml = `
        <div style="font-size: 1.85rem; font-weight: 800; color: ${isOver ? '#f87171' : (isOptimized ? '#34d399' : 'var(--accent-cyan)')}; font-family: var(--font-heading); margin-top: 0.2rem;">
          ${r.power_w.toFixed(1)} <span style="font-size: 1rem; font-weight: 500; color: var(--text-muted);">W</span>
        </div>
        <div style="font-size: 0.74rem; color: var(--text-secondary); margin-top: 0.25rem;">
          Previous: <strong>${prevW.toFixed(1)} W</strong> • Change: ${fluctuationHtml}
        </div>
        <div style="font-size: 0.72rem; color: var(--text-secondary); margin-top: 0.2rem;">
          Limit: <strong>${r.threshold_w} W</strong> • Target: <strong style="color: var(--accent-cyan);">${r.optimization_target_w || 800} W</strong> ${excessText}
        </div>
      `;
    }

    // Quick optimize action button
    const canQuickOptimize = !isOffline && !isManualLocked && !isTripped && r.power_w > (r.optimization_target_w || 800);
    const optimizeBtn = canQuickOptimize ? `
      <button class="btn btn-cyan btn-sm" onclick="event.preventDefault(); quickOptimizeRoom('${r.room_id}')" style="font-size: 0.68rem; padding: 0.15rem 0.45rem;">
        ⚡ AI Optimize
      </button>
    ` : "";

    // Simulation Profile options
    const profiles = [
      { id: "NORMAL_OCCUPIED", label: "Normal Occupied (50–700 W)" },
      { id: "LIKELY_VACANT", label: "Likely Vacant (0–35 W)" },
      { id: "HIGH_USAGE", label: "High Usage (Climbing)" },
      { id: "OPTIMIZING", label: "Optimizing (Shedding)" },
      { id: "MANUAL_OFF", label: "Manual OFF Room (0 W)" },
      { id: "TRIPPED", label: "Tripped Room (0 W)" },
      { id: "SENSOR_OFFLINE", label: "Sensor Offline (--)" }
    ];

    let profileOptions = profiles.map(p => {
      const selected = p.id === simProfile ? "selected" : "";
      return `<option value="${p.id}" ${selected}>${p.label}</option>`;
    }).join("");

    html += `
      <div class="${cardClass}">
        <div>
          <!-- Header -->
          <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.75rem;">
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

          <!-- Occupancy, Relay & Sensor Status -->
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; flex-wrap: wrap; gap: 0.35rem;">
            <div style="display: flex; gap: 0.35rem; align-items: center; flex-wrap: wrap;">
              ${occBadge}
              ${sensorBadge}
              <span style="font-size: 0.72rem; color: var(--text-muted); font-family: var(--font-mono);">
                Relay: <strong style="color: ${r.relay_state === 'TRIPPED_SIMULATED' ? '#f87171' : (r.relay_state === 'OPEN_MANUAL' ? '#fbbf24' : 'var(--accent-emerald)')};">${r.relay_state}</strong>
              </span>
            </div>
            ${optimizeBtn}
          </div>

          <!-- Live Power Large Display -->
          <div style="background: rgba(10, 15, 28, 0.65); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 8px; padding: 0.8rem; margin-bottom: 0.75rem; text-align: center;">
            <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.04em;">Active Power & 10s Dynamic Variation</div>
            ${powerDisplayHtml}
          </div>

          <!-- Detailed Electrical Matrix -->
          <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.35rem; font-size: 0.72rem; text-align: center; margin-bottom: 0.75rem;">
            <div style="background: rgba(255, 255, 255, 0.03); padding: 0.35rem 0.2rem; border-radius: 4px;">
              <div style="color: var(--text-muted);">Voltage</div>
              <div style="font-weight: 700; color: #fff; margin-top: 0.15rem;">${isOffline ? '--' : (r.voltage_v ? r.voltage_v + ' V' : '--')}</div>
            </div>
            <div style="background: rgba(255, 255, 255, 0.03); padding: 0.35rem 0.2rem; border-radius: 4px;">
              <div style="color: var(--text-muted);">Current</div>
              <div style="font-weight: 700; color: #fff; margin-top: 0.15rem;">${isOffline ? '--' : (r.current_a ? r.current_a + ' A' : '--')}</div>
            </div>
            <div style="background: rgba(255, 255, 255, 0.03); padding: 0.35rem 0.2rem; border-radius: 4px;">
              <div style="color: var(--text-muted);">Energy</div>
              <div style="font-weight: 700; color: #fff; margin-top: 0.15rem;">${isOffline ? '--' : (r.energy_kwh || '0') + ' kWh'}</div>
            </div>
            <div style="background: rgba(255, 255, 255, 0.03); padding: 0.35rem 0.2rem; border-radius: 4px;">
              <div style="color: var(--text-muted);">PF</div>
              <div style="font-weight: 700; color: #fff; margin-top: 0.15rem;">${isOffline ? '--' : (r.power_factor || '0.95')}</div>
            </div>
          </div>

          <!-- Simulation Profile Selector -->
          <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 6px; padding: 0.4rem 0.6rem; margin-bottom: 0.75rem; display: flex; align-items: center; justify-content: space-between; gap: 0.4rem;">
            <label style="font-size: 0.68rem; color: var(--text-muted); white-space: nowrap;">Sim Profile:</label>
            <select class="select-custom" style="font-size: 0.7rem; padding: 0.2rem 0.4rem; height: auto; flex: 1; min-width: 0;" onchange="onRoomProfileChange('${r.room_id}', this.value)">
              ${profileOptions}
            </select>
          </div>
        </div>

        <!-- Footer: Links to Room Switch Control & Investigation -->
        <div style="border-top: 1px solid rgba(255, 255, 255, 0.06); padding-top: 0.65rem; display: flex; justify-content: space-between; align-items: center; font-size: 0.74rem;">
          <a href="/rooms/${r.room_id}" style="color: var(--accent-cyan); font-weight: 600; text-decoration: none;">
            Main Switch Control &rarr;
          </a>
          <span style="font-size: 0.68rem; color: var(--text-muted);">
            ${r.last_update ? 'Updated: ' + r.last_update.split(' ')[1] : 'Live'}
          </span>
        </div>
      </div>
    `;
  });

  container.innerHTML = html;
}

async function onRoomProfileChange(roomId, newProfile) {
  try {
    const res = await fetch(`/api/rooms/${roomId}/simulation-profile`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile: newProfile })
    });
    const data = await res.json();
    if (res.ok && data.status === "success") {
      // Step simulator once to reflect the new profile immediately
      await fetch(`/api/simulation/step`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ elapsed_seconds: 10.0 })
      });
      loadLiveRoomsGrid();
    } else {
      alert(`Could not set profile for ${roomId}: ${data.message || "Unknown error"}`);
    }
  } catch (e) {
    console.error("Profile change error:", e);
    alert("Network error updating simulation profile.");
  }
}

async function toggleSimulationPause() {
  const endpoint = simStatus.paused ? "/api/simulation/resume" : "/api/simulation/pause";
  try {
    const res = await fetch(endpoint, { method: "POST" });
    const data = await res.json();
    if (res.ok && data.simulation) {
      simStatus = Object.assign({}, simStatus, data.simulation);
      updateCountdownDisplay();
    }
  } catch (e) {
    console.error("Failed to toggle simulation pause:", e);
  }
}

async function stepSimulationNow() {
  try {
    const res = await fetch("/api/simulation/step", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ elapsed_seconds: 10.0 })
    });
    const data = await res.json();
    if (res.ok) {
      if (data.simulation) {
        simStatus = Object.assign({}, simStatus, data.simulation);
        simStatus.next_update_seconds = simStatus.interval_seconds;
      }
      loadLiveRoomsGrid();
    }
  } catch (e) {
    console.error("Failed to step simulation:", e);
  }
}

async function confirmResetSimulation() {
  const confirmed = confirm(
    "Are you sure you want to reset demo rooms to baseline telemetry?\n\n" +
    "• This resets room power readings to baseline benchmark profiles.\n" +
    "• Important historical incident records and trip history will NOT be deleted.\n" +
    "• Real hardware relays remain permanently disabled."
  );
  if (!confirmed) return;

  try {
    const res = await fetch("/api/simulation/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operator: "Hostel Warden (Dashboard Reset)" })
    });
    const data = await res.json();
    if (res.ok) {
      if (data.simulation) {
        simStatus = Object.assign({}, simStatus, data.simulation);
      }
      loadLiveRoomsGrid();
    } else {
      alert("Failed to reset simulation: " + (data.message || "Unknown error"));
    }
  } catch (e) {
    console.error("Reset simulation error:", e);
    alert("Network error resetting simulation.");
  }
}

async function quickOptimizeRoom(roomId) {
  try {
    const res = await fetch(`/api/rooms/${roomId}/optimize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operator: "Warden (Live Grid Quick Action)" })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      alert(`Room ${roomId} Optimized: Reduced by ${data.reduction_achieved_w} W (New Power: ${data.resulting_power_w} W).`);
      loadLiveRoomsGrid();
    } else {
      alert(`Optimization Alert for ${roomId}: ${data.error || "Could not complete optimization."}`);
      loadLiveRoomsGrid();
    }
  } catch (e) {
    console.error("Quick optimization error:", e);
    alert("Network error executing power optimization.");
  }
}
