/* ==========================================================================
   Hostel Energy AI - Room Command Center Controller
   ========================================================================== */

document.addEventListener("DOMContentLoaded", function() {
  loadCommandCenterData();
  // Poll every 10 seconds for real-time demonstration
  setInterval(loadCommandCenterData, 10000);
});

async function loadCommandCenterData() {
  try {
    const res = await fetch("/api/command-center/stats");
    if (!res.ok) return;
    const data = await res.json();

    // 1. Primary Summary Cards
    const onlineEl = document.getElementById("stat-rooms-online");
    if (onlineEl) {
      onlineEl.innerHTML = `${data.rooms_online} <span style="font-size: 1.1rem; color: var(--text-muted); font-weight: 500;">/ ${data.total_rooms}</span>`;
    }

    const highEl = document.getElementById("stat-rooms-high");
    if (highEl) highEl.innerText = data.rooms_high_usage;

    const anomEl = document.getElementById("stat-active-anomalies");
    if (anomEl) anomEl.innerText = data.active_anomalies;

    const tripEl = document.getElementById("stat-simulated-trips");
    if (tripEl) {
      tripEl.innerHTML = `${data.simulated_trips} <span style="font-size: 0.85rem; color: var(--text-muted); font-weight: 500;">(${data.rooms_switched_off || 0} OFF)</span>`;
    }

    const wattsEl = document.getElementById("campus-live-watts");
    if (wattsEl) wattsEl.innerText = `${(data.campus_live_watts || 0).toLocaleString()} W`;

    const labelHigh = document.getElementById("label-high-threshold");
    if (labelHigh && data.high_power_threshold_w) {
      labelHigh.innerText = Math.round(data.high_power_threshold_w);
    }

    // 2. Rooms Requiring Attention
    renderAttentionRooms(data.attention_rooms || []);
  } catch (e) {
    console.error("Failed to load command center stats:", e);
  }
}

function renderAttentionRooms(rooms) {
  const container = document.getElementById("attention-rooms-list");
  const countBadge = document.getElementById("attention-count-badge");
  if (!container) return;

  if (countBadge) countBadge.innerText = `${rooms.length} Action Items`;

  if (rooms.length === 0) {
    container.innerHTML = `
      <div style="padding: 2.5rem; text-align: center; color: var(--accent-emerald);">
        <div style="font-size: 1.3rem; margin-bottom: 0.4rem;">✓ All Monitored Rooms Operating Normally</div>
        <div style="font-size: 0.85rem; color: var(--text-muted);">No active simulated trips, sustained vacant draws, or sensor faults.</div>
      </div>
    `;
    return;
  }

  let html = "";
  rooms.forEach(r => {
    // Status styling
    let stateBadge = `<span class="badge badge-warning">${r.room_state}</span>`;
    let borderCol = "rgba(245, 158, 11, 0.4)";
    let isTripped = false;

    if (r.room_state === "TRIPPED_SIMULATED") {
      stateBadge = `<span class="safety-badge" style="font-size: 0.7rem; padding: 0.2rem 0.6rem;">🛑 TRIPPED — SIMULATION ONLY</span>`;
      borderCol = "rgba(239, 68, 68, 0.6)";
      isTripped = true;
    } else if (r.room_state === "MANUAL_OFF") {
      stateBadge = `<span class="badge" style="background: rgba(244, 63, 94, 0.18); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.4); font-size: 0.7rem;">⏻ MANUAL OFF</span>`;
      borderCol = "rgba(244, 63, 94, 0.6)";
      isTripped = true;
    } else if (r.room_state === "TRIP_PENDING") {
      stateBadge = `<span class="badge badge-critical">⚠️ TRIP PENDING</span>`;
      borderCol = "rgba(239, 68, 68, 0.4)";
    } else if (r.room_state === "SENSOR_OFFLINE") {
      stateBadge = `<span class="badge badge-normal" style="background: rgba(100, 116, 139, 0.2); color: #94a3b8;">SENSOR OFFLINE</span>`;
      borderCol = "rgba(100, 116, 139, 0.4)";
    }

    // Switch state pill
    let switchBadge = `<span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #34d399; font-size: 0.68rem; border: 1px solid rgba(16, 185, 129, 0.4);">⚡ SWITCH ON</span>`;
    if (r.manual_off_lock === 1) {
      switchBadge = `<span class="badge" style="background: rgba(245, 158, 11, 0.18); color: #fbbf24; font-size: 0.68rem; border: 1px solid rgba(245, 158, 11, 0.45);">🔒 SWITCH OFF (LOCKED)</span>`;
    } else if (r.effective_switch_state === "OFF") {
      switchBadge = `<span class="badge" style="background: rgba(239, 68, 68, 0.18); color: #f87171; font-size: 0.68rem; border: 1px solid rgba(239, 68, 68, 0.5);">🛑 SWITCH OFF</span>`;
    }

    // Occupancy styling
    let occBadge = `<span class="badge badge-normal" style="background: rgba(148, 163, 184, 0.12); color: #cbd5e1;">${r.occupancy_state}</span>`;
    if ((r.occupancy_state || "").toLowerCase().includes("vacant")) {
      occBadge = `<span class="badge badge-warning" style="background: rgba(245, 158, 11, 0.15); color: #fbbf24;">Likely Vacant</span>`;
    }

    html += `
      <div class="glass-panel" style="padding: 1.25rem 1.5rem; border-left: 4px solid ${borderCol}; background: ${isTripped ? 'rgba(239, 68, 68, 0.04)' : 'var(--bg-card)'};">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 0.75rem;">
          <div>
            <div style="display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;">
              <h4 style="font-size: 1.15rem; font-weight: 700; color: #fff;">${r.block_id} / ${r.room_number}</h4>
              ${switchBadge}
              ${stateBadge}
              ${occBadge}
            </div>
            <div style="font-size: 0.78rem; color: var(--text-muted); margin-top: 0.2rem;">
              Room ID: <strong style="color: #fff;">${r.room_id}</strong> • Duration: <strong style="color: var(--accent-amber);">${r.duration_minutes} min</strong>
            </div>
          </div>
          <div style="text-align: right;">
            <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">Active Load vs Limit</div>
            <div style="font-size: 1.25rem; font-weight: 800; color: ${r.power_w > r.threshold_w ? '#f87171' : 'var(--accent-cyan)'}; font-family: var(--font-heading);">
              ${r.power_w} W <span style="font-size: 0.85rem; color: var(--text-muted); font-weight: normal;">/ ${r.threshold_w} W</span>
            </div>
          </div>
        </div>

        <!-- Reason for Alert -->
        <div style="background: rgba(15, 23, 42, 0.5); border-radius: 6px; padding: 0.65rem 0.85rem; margin-bottom: 0.75rem; font-size: 0.84rem; color: #f1f5f9; line-height: 1.4;">
          <strong style="color: var(--accent-amber);">Alert Reason:</strong> ${r.reason}
        </div>

        <!-- Recommended Action & Button -->
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem; border-top: 1px solid rgba(255, 255, 255, 0.06); padding-top: 0.75rem;">
          <div style="font-size: 0.82rem; color: #94a3b8;">
            <strong style="color: #fff;">Recommended Step:</strong> ${r.recommended_action}
          </div>
          <div style="display: flex; gap: 0.5rem;">
            <a href="/rooms/${r.room_id}" class="btn btn-secondary btn-sm" style="font-size: 0.78rem;">
              Open Room Control &rarr;
            </a>
          </div>
        </div>
      </div>
    `;
  });

  container.innerHTML = html;
}
