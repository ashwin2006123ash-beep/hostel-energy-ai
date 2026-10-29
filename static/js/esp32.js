/* ==========================================================================
   Hostel Energy AI - ESP32 Virtual Fan Controller Hub
   ========================================================================== */

document.addEventListener("DOMContentLoaded", function() {
  loadEsp32Devices();
  loadEsp32Logs();
});

async function loadEsp32Devices() {
  const container = document.getElementById("devices-container");
  if (!container) return;

  try {
    const res = await fetch("/api/esp32/devices");
    if (!res.ok) throw new Error("Failed to load virtual devices");
    const data = await res.json();
    const devices = data.devices;

    let html = "";
    devices.forEach(d => {
      const speed = d.fan_speed_percent;
      let statusBadge = `<span class="badge badge-low">ONLINE</span>`;
      if (d.status === "ECO_MODE") statusBadge = `<span class="badge badge-medium">ECO MODE</span>`;
      else if (d.status === "OFFLINE") statusBadge = `<span class="badge badge-critical">OFFLINE</span>`;
      else if (d.status === "MANUAL_OVERRIDE") statusBadge = `<span class="badge badge-high">MANUAL</span>`;

      // Speed spin animation duration (faster speed = lower duration)
      const animDuration = speed > 0 ? Math.max(0.2, (1.6 - (speed / 100.0) * 1.35)).toFixed(2) : 0;
      const spinStyle = speed > 0 ? `animation: spin ${animDuration}s infinite linear;` : `opacity: 0.4;`;

      html += `
        <div class="glass-panel" style="padding: 1.5rem; display: flex; flex-direction: column; justify-content: space-between;">
          <div>
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.75rem;">
              <div>
                <strong style="font-size: 1.05rem; color: #fff;">${d.device_id}</strong>
                <div style="font-size: 0.78rem; color: var(--text-secondary);">${d.block_id} • ${d.zone_name}</div>
              </div>
              ${statusBadge}
            </div>

            <!-- Virtual Animated Fan Visualizer -->
            <div style="background: rgba(0,0,0,0.3); border-radius: var(--radius-md); padding: 1.25rem; display: flex; align-items: center; justify-content: center; gap: 1.5rem; margin-bottom: 1.25rem;">
              <div style="font-size: 2.8rem; display: inline-block; ${spinStyle}">
                🌀
              </div>
              <div>
                <div style="font-family: var(--font-heading); font-size: 1.6rem; font-weight: 800; color: var(--accent-cyan); line-height: 1;">
                  ${speed}% <span style="font-size: 0.85rem; color: var(--text-secondary);">PWM</span>
                </div>
                <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.2rem;">
                  ${d.simulated_rpm} RPM • <strong style="color: #fff;">${d.simulated_watts} W</strong>
                </div>
              </div>
            </div>

            <!-- PWM Control Slider -->
            <div class="slider-container">
              <div class="slider-label-group">
                <span style="font-size: 0.82rem;">Virtual Duty Cycle</span>
                <span class="slider-val" id="val-${d.device_id}">${speed}%</span>
              </div>
              <input type="range" class="custom-range" min="0" max="100" value="${speed}"
                     onchange="sendSpeedCommand('${d.device_id}', this.value)"
                     oninput="document.getElementById('val-${d.device_id}').innerText = this.value + '%'">
            </div>
          </div>

          <!-- Quick Action Buttons -->
          <div style="display: flex; gap: 0.5rem; margin-top: 1rem; border-top: 1px solid var(--border-glass); padding-top: 1rem;">
            <button class="btn btn-secondary btn-sm" style="flex: 1;" onclick="sendModeCommand('${d.device_id}', 'ECO_MODE')">
              🌱 Eco (35%)
            </button>
            <button class="btn btn-secondary btn-sm" style="flex: 1;" onclick="sendModeCommand('${d.device_id}', 'ONLINE')">
              ⚡ Normal (60%)
            </button>
            <button class="btn btn-secondary btn-sm" onclick="sendSpeedCommand('${d.device_id}', 0)">
              🛑 Off
            </button>
          </div>
        </div>
      `;
    });

    container.innerHTML = html;

  } catch (e) {
    container.innerHTML = `<div style="grid-column: 1/-1; color: var(--accent-rose); text-align: center; padding: 2rem;">Error: ${e.message}</div>`;
  }
}

async function sendSpeedCommand(deviceId, speedVal) {
  try {
    const res = await fetch("/api/esp32/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        device_id: deviceId,
        command_type: "SET_SPEED",
        value: speedVal
      })
    });
    if (res.ok) {
      loadEsp32Devices();
      loadEsp32Logs();
    }
  } catch (e) {
    alert("Simulation error: " + e.message);
  }
}

async function sendModeCommand(deviceId, modeVal) {
  try {
    const res = await fetch("/api/esp32/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        device_id: deviceId,
        command_type: "SET_MODE",
        value: modeVal
      })
    });
    if (res.ok) {
      loadEsp32Devices();
      loadEsp32Logs();
    }
  } catch (e) {
    alert("Simulation error: " + e.message);
  }
}

async function loadEsp32Logs() {
  const tbody = document.getElementById("esp32-logs-body");
  if (!tbody) return;

  try {
    const res = await fetch("/api/esp32/logs");
    if (!res.ok) return;
    const data = await res.json();

    if (data.logs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No recent simulation events logged.</td></tr>`;
      return;
    }

    let html = "";
    data.logs.forEach(l => {
      html += `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-secondary);">${l.timestamp}</td>
          <td><strong>${l.device_id}</strong></td>
          <td style="font-family: var(--font-mono); font-size: 0.82rem; color: var(--accent-cyan);">${l.command}</td>
          <td><span style="font-size: 0.75rem; color: var(--text-secondary); background: rgba(255,255,255,0.05); padding: 0.2rem 0.5rem; border-radius: 4px;">${l.triggered_by}</span></td>
          <td style="font-size: 0.84rem; color: #e2e8f0;">${l.response}</td>
        </tr>
      `;
    });

    tbody.innerHTML = html;
  } catch (e) {
    console.error("Failed to load ESP32 logs", e);
  }
}
