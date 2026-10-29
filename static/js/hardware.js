/* ==========================================================================
   Hostel Energy AI - Hardware & Sensors View Controller (Simulation Mode)
   ========================================================================== */

document.addEventListener("DOMContentLoaded", function() {
  loadHardwareDevices();
  loadHardwareLogs();
});

async function loadHardwareDevices() {
  const container = document.getElementById("device-cards-grid");
  if (!container) return;

  try {
    const res = await fetch("/api/esp32/devices");
    if (!res.ok) {
      container.innerHTML = `<div class="glass-panel" style="padding: 2rem; text-align: center; color: var(--text-muted); grid-column: 1 / -1;">No sensor nodes registered.</div>`;
      return;
    }
    const data = await res.json();
    const devices = data.devices || [];

    if (devices.length === 0) {
      container.innerHTML = `<div class="glass-panel" style="padding: 2rem; text-align: center; color: var(--text-muted); grid-column: 1 / -1;">No active hardware devices found.</div>`;
      return;
    }

    let html = "";
    devices.forEach(d => {
      // Connectivity badge
      let connBadge = `<span class="badge badge-normal" style="background: rgba(16, 185, 129, 0.15); color: #34d399;">● ONLINE</span>`;
      let staleNotice = "";
      if (d.status === "STALE" || (d.last_heartbeat && d.last_heartbeat.includes("11:45"))) {
        connBadge = `<span class="badge badge-warning">⚠️ STALE SENSOR</span>`;
        staleNotice = `
          <div style="background: rgba(245, 158, 11, 0.1); border-radius: 6px; padding: 0.4rem 0.6rem; font-size: 0.74rem; color: #fbbf24; margin-top: 0.6rem;">
            Telemetry timeout: Heartbeat delayed > 30 minutes. Data may be stale.
          </div>
        `;
      } else if (d.status === "OFFLINE") {
        connBadge = `<span class="badge badge-critical">● OFFLINE</span>`;
      }

      // Motion status badge
      let motionBadge = `<span class="badge badge-normal" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8;">🏃 Motion Detected</span>`;
      if ((d.motion_status || "").toLowerCase().includes("vacant") || (d.motion_status || "").toLowerCase().includes("no motion")) {
        motionBadge = `<span class="badge badge-warning" style="background: rgba(245, 158, 11, 0.15); color: #fbbf24;">⏸️ No Motion (Vacant)</span>`;
      } else if ((d.motion_status || "").toLowerCase().includes("unknown") || (d.motion_status || "").toLowerCase().includes("timeout")) {
        motionBadge = `<span class="badge badge-normal" style="background: rgba(148, 163, 184, 0.15); color: #cbd5e1;">❓ Unknown</span>`;
      }

      html += `
        <div class="glass-panel" style="padding: 1.5rem; display: flex; flex-direction: column; justify-content: space-between;">
          <div>
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.75rem;">
              <div>
                <span class="badge badge-normal" style="font-size: 0.68rem; margin-bottom: 0.35rem; display: inline-block;">SIMULATION NODE</span>
                <h3 style="font-size: 1.15rem; font-weight: 700; color: #fff;">${d.room_number || 'Room 101'}</h3>
                <div style="font-size: 0.78rem; color: var(--text-muted);">${d.block_id} • ${d.zone_name}</div>
              </div>
              <div style="text-align: right;">
                ${connBadge}
                <div style="font-size: 0.68rem; color: var(--text-muted); font-family: var(--font-mono); margin-top: 0.35rem;">
                  ID: ${d.device_id}
                </div>
              </div>
            </div>

            <!-- Motion & Connectivity Details -->
            <div style="display: flex; gap: 0.5rem; align-items: center; margin-bottom: 1rem; flex-wrap: wrap;">
              ${motionBadge}
              <span style="font-size: 0.75rem; color: var(--text-muted); font-family: var(--font-mono);">
                Heartbeat: ${d.last_heartbeat ? d.last_heartbeat.split(" ")[1] : '--'}
              </span>
            </div>

            <!-- Electrical Telemetry Measurements -->
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.5rem; background: rgba(15, 23, 42, 0.5); padding: 0.75rem; border-radius: 8px; margin-bottom: 1rem; text-align: center;">
              <div>
                <div style="font-size: 0.68rem; color: var(--text-muted); text-transform: uppercase;">Voltage</div>
                <div style="font-size: 0.95rem; font-weight: 700; color: #fff;">${d.voltage_v || 230.0} V</div>
              </div>
              <div>
                <div style="font-size: 0.68rem; color: var(--text-muted); text-transform: uppercase;">Current</div>
                <div style="font-size: 0.95rem; font-weight: 700; color: var(--accent-cyan);">${d.current_a || 0.35} A</div>
              </div>
              <div>
                <div style="font-size: 0.68rem; color: var(--text-muted); text-transform: uppercase;">Power</div>
                <div style="font-size: 0.95rem; font-weight: 700; color: var(--accent-amber);">${d.simulated_watts || d.current_draw_w || 75.0} W</div>
              </div>
            </div>

            ${staleNotice}
          </div>

          <!-- Safe Testbench Controls -->
          <div style="border-top: 1px solid var(--border-glass); padding-top: 1rem; margin-top: 0.75rem;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; font-size: 0.78rem;">
              <span style="color: var(--text-secondary);">Simulated Fan Speed:</span>
              <strong id="speed-label-${d.device_id}" style="color: #fff;">${d.fan_speed_percent}% (${d.simulated_rpm || 210} RPM)</strong>
            </div>

            <input type="range" min="0" max="100" value="${d.fan_speed_percent}"
                   oninput="onFanSpeedChange('${d.device_id}', this.value)"
                   class="slider-custom" style="width: 100%; margin-bottom: 0.75rem;">

            <div style="display: flex; gap: 0.5rem; justify-content: space-between;">
              <button class="btn btn-secondary btn-sm" onclick="sendDeviceCommand('${d.device_id}', 'SET_MODE', 'ECO_MODE')" style="flex: 1; font-size: 0.75rem; padding: 0.35rem 0.5rem;">
                Eco Mode
              </button>
              <button class="btn btn-secondary btn-sm" onclick="sendDeviceCommand('${d.device_id}', 'AUTO_TOGGLE', ${d.auto_mode ? 0 : 1})" style="flex: 1; font-size: 0.75rem; padding: 0.35rem 0.5rem;">
                ${d.auto_mode ? 'Auto: ON' : 'Auto: OFF'}
              </button>
            </div>
          </div>
        </div>
      `;
    });

    container.innerHTML = html;
  } catch (e) {
    console.error("Failed to load hardware devices:", e);
    container.innerHTML = `<div class="glass-panel" style="padding: 2rem; text-align: center; color: var(--text-muted); grid-column: 1 / -1;">Error loading sensor nodes.</div>`;
  }
}

async function onFanSpeedChange(deviceId, speed) {
  const label = document.getElementById(`speed-label-${deviceId}`);
  if (label) {
    label.innerText = `${speed}% (${Math.round(350 * speed / 100)} RPM)`;
  }
  // Debounced command send
  clearTimeout(window[`speedTimer_${deviceId}`]);
  window[`speedTimer_${deviceId}`] = setTimeout(() => {
    sendDeviceCommand(deviceId, "SET_SPEED", parseInt(speed));
  }, 350);
}

async function sendDeviceCommand(deviceId, commandType, value) {
  try {
    const res = await fetch("/api/esp32/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        device_id: deviceId,
        command_type: commandType,
        value: value
      })
    });
    if (res.ok) {
      loadHardwareLogs();
    }
  } catch (e) {
    console.error("Failed to send device command:", e);
  }
}

async function loadHardwareLogs() {
  const tbody = document.getElementById("hardware-logs-body");
  if (!tbody) return;

  try {
    const res = await fetch("/api/esp32/logs");
    if (!res.ok) return;
    const data = await res.json();
    const logs = data.logs || [];

    if (logs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No simulation logs recorded yet.</td></tr>`;
      return;
    }

    let rowsHtml = "";
    logs.slice(0, 8).forEach(l => {
      rowsHtml += `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 0.78rem; color: var(--text-secondary);">${l.timestamp}</td>
          <td><strong>${l.device_id}</strong></td>
          <td><span class="badge badge-normal">${l.command}</span></td>
          <td style="font-size: 0.8rem; color: var(--text-muted);">${l.triggered_by}</td>
          <td style="font-size: 0.82rem; color: #cbd5e1;">${l.response}</td>
        </tr>
      `;
    });
    tbody.innerHTML = rowsHtml;
  } catch (e) {
    console.error("Failed to load logs:", e);
  }
}
