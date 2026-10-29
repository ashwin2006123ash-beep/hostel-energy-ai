/* ==========================================================================
   Hostel Energy AI - NILM Simulator Controller
   ========================================================================== */

async function runSimulation(scenarioId, targetRoomId) {
  const consoleEl = document.getElementById("sim-console");
  const fastForward = document.getElementById("fast-forward-toggle").checked;

  if (consoleEl) {
    consoleEl.innerHTML = `<span style="color: var(--accent-amber);">Transmitting simulated telemetry to Room ${targetRoomId}...</span>`;
  }

  try {
    const res = await fetch("/api/nilm/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenario_id: scenarioId,
        target_room_id: targetRoomId === "ALL" ? null : targetRoomId,
        fast_forward: fastForward
      })
    });
    const result = await res.json();

    if (result.success) {
      if (consoleEl) {
        consoleEl.innerHTML = `
          <div>
            <span style="color: var(--accent-emerald); font-weight: 700;">[SUCCESS]</span>
            <span style="color: #fff;">${result.message}</span>
            <span style="color: var(--text-muted); font-size: 0.72rem; margin-left: 0.5rem;">(${result.event_type} logged to SQLite)</span>
          </div>
        `;
      }
    } else {
      if (consoleEl) {
        consoleEl.innerHTML = `<span style="color: var(--accent-rose);">[ERROR] ${result.error || 'Simulation trigger failed.'}</span>`;
      }
    }
  } catch (e) {
    console.error("Simulation request error:", e);
    if (consoleEl) {
      consoleEl.innerHTML = `<span style="color: var(--accent-rose);">Network error executing simulation.</span>`;
    }
  }
}
