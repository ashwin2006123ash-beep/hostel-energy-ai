/* ==========================================================================
   Hostel Energy AI - Room Detail & Manual Switch Controller
   ========================================================================== */

let roomChartInstance = null;
let pendingActionType = null;
let currentActionRoomId = null;

document.addEventListener("DOMContentLoaded", function() {
  initRoomChart();
  // Poll switch state every 8 seconds to reflect real-time background trips or telemetry
  if (typeof currentRoomData !== "undefined" && currentRoomData.room_id) {
    setInterval(() => {
      refreshSwitchPanelData(currentRoomData.room_id, false);
    }, 8000);
  }
});

function initRoomChart() {
  const canvas = document.getElementById("roomPowerChart");
  if (!canvas || typeof currentRoomData === "undefined") return;
  const ctx = canvas.getContext("2d");

  const labels = [];
  const powerData = [];
  const thresholdData = [];
  const currentP = currentRoomData.power_w;
  const limitP = currentRoomData.threshold_w;

  for (let i = 14; i >= 0; i--) {
    labels.push(`-${i * 2}m`);
    thresholdData.push(limitP);
    if (i === 0) {
      powerData.push(currentP);
    } else {
      const noise = Math.sin(i) * 20;
      const val = Math.max(20, Math.round(currentP * (0.8 + 0.015 * (14 - i)) + noise));
      powerData.push(val);
    }
  }

  const gradient = ctx.createLinearGradient(0, 0, 0, 240);
  gradient.addColorStop(0, currentP > limitP ? "rgba(239, 68, 68, 0.3)" : "rgba(6, 182, 212, 0.3)");
  gradient.addColorStop(1, "rgba(0, 0, 0, 0)");

  roomChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Measured Power (W)",
          data: powerData,
          borderColor: currentP > limitP ? "#f87171" : "#06b6d4",
          backgroundColor: gradient,
          borderWidth: 2.5,
          tension: 0.3,
          fill: true,
          pointRadius: 3,
          pointBackgroundColor: currentP > limitP ? "#f87171" : "#06b6d4"
        },
        {
          label: "Threshold (W)",
          data: thresholdData,
          borderColor: "#f59e0b",
          borderWidth: 2,
          borderDash: [5, 5],
          pointRadius: 0,
          fill: false
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: "#94a3b8", font: { size: 11 } } },
        tooltip: {
          backgroundColor: "rgba(15, 23, 42, 0.95)",
          titleColor: "#fff",
          bodyColor: "#cbd5e1"
        }
      },
      scales: {
        x: {
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: { color: "#64748b" }
        },
        y: {
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: { color: "#64748b", callback: v => `${v} W` }
        }
      }
    }
  });
}

// ============================================================================
// Modal Management Helpers
// ============================================================================
function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.add("active");
  }
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.remove("active");
  }
}

// Close modal on escape key or clicking backdrop
document.addEventListener("keydown", function(e) {
  if (e.key === "Escape") {
    closeModal("modal-confirm-action");
    closeModal("modal-problem-resolved");
  }
});

// ============================================================================
// Confirmation Dialog Triggers
// ============================================================================
function confirmManualOff(roomId) {
  currentActionRoomId = roomId;
  pendingActionType = "switch-off";

  const iconEl = document.getElementById("modal-action-icon");
  const titleEl = document.getElementById("modal-action-title");
  const bodyEl = document.getElementById("modal-action-body");
  const btnEl = document.getElementById("modal-action-confirm-btn");

  iconEl.innerText = "🛑";
  titleEl.innerText = "Confirm Manual Switch OFF";
  bodyEl.innerHTML = `
    <p>Are you sure you want to manually switch <strong>OFF</strong> the simulated mains circuit for <strong>${roomId}</strong>?</p>
    <div style="margin-top: 0.65rem; color: #fecdd3; font-size: 0.82rem;">
      ⚠️ <strong>Safety Notice:</strong> This action engages the <strong>Manual OFF Lock</strong>. Power will be isolated immediately (0 W in simulation). Automatic restoration policies will be blocked until the lock is explicitly released.
    </div>
  `;

  btnEl.className = "btn btn-rose btn-sm";
  btnEl.innerText = "Confirm Manual OFF";
  btnEl.onclick = executePendingAction;

  openModal("modal-confirm-action");
}

function confirmManualOn(roomId) {
  currentActionRoomId = roomId;
  pendingActionType = "switch-on";

  const iconEl = document.getElementById("modal-action-icon");
  const titleEl = document.getElementById("modal-action-title");
  const bodyEl = document.getElementById("modal-action-body");
  const btnEl = document.getElementById("modal-action-confirm-btn");

  iconEl.innerText = "⚡";
  titleEl.innerText = "Confirm Manual Switch ON";
  bodyEl.innerHTML = `
    <p>Confirm restoration of simulated power for <strong>${roomId}</strong>.</p>
    <div style="margin-top: 0.65rem; color: #cbd5e1; font-size: 0.82rem;">
      Backend safety checks will verify that no active safety locks, unresolved critical faults, or sensor disconnections remain before energizing the circuit.
    </div>
  `;

  btnEl.className = "btn btn-emerald btn-sm";
  btnEl.innerText = "Confirm Manual ON";
  btnEl.onclick = executePendingAction;

  openModal("modal-confirm-action");
}

function confirmReleaseLock(roomId) {
  currentActionRoomId = roomId;
  pendingActionType = "release-lock";

  const iconEl = document.getElementById("modal-action-icon");
  const titleEl = document.getElementById("modal-action-title");
  const bodyEl = document.getElementById("modal-action-body");
  const btnEl = document.getElementById("modal-action-confirm-btn");

  iconEl.innerText = "🔓";
  titleEl.innerText = "Release Manual OFF Lock";
  bodyEl.innerHTML = `
    <p>Release the manual lock currently held on <strong>${roomId}</strong>?</p>
    <div style="margin-top: 0.65rem; color: #fde68a; font-size: 0.82rem;">
      If no active critical faults remain on the circuit, power will automatically restore to ON. If a critical fault or trip condition persists, power will remain safely held OFF.
    </div>
  `;

  btnEl.className = "btn btn-amber btn-sm";
  btnEl.innerText = "Release Lock & Restore";
  btnEl.onclick = executePendingAction;

  openModal("modal-confirm-action");
}

async function executePendingAction() {
  if (!currentActionRoomId || !pendingActionType) return;

  const operatorInput = document.getElementById("modal-operator-input");
  const operator = (operatorInput && operatorInput.value.trim()) || "Hostel Warden";
  const btnEl = document.getElementById("modal-action-confirm-btn");

  const originalText = btnEl.innerText;
  btnEl.disabled = true;
  btnEl.innerText = "Processing...";

  try {
    const res = await fetch(`/api/rooms/${currentActionRoomId}/${pendingActionType}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operator: operator })
    });
    const result = await res.json();

    closeModal("modal-confirm-action");

    if (result.success) {
      showFeedbackAlert(result.message || "Action executed successfully.", "success");
      await refreshSwitchPanelData(currentActionRoomId, true);
    } else {
      const errMsg = result.error || result.message || "Action could not be completed.";
      showFeedbackAlert(`⛔ ${errMsg}`, "error");
      await refreshSwitchPanelData(currentActionRoomId, false);
    }
  } catch (e) {
    console.error("Action execution failed:", e);
    closeModal("modal-confirm-action");
    showFeedbackAlert("Network or communication error executing action.", "error");
  } finally {
    btnEl.disabled = false;
    btnEl.innerText = originalText;
    pendingActionType = null;
    currentActionRoomId = null;
  }
}

// ============================================================================
// Problem Resolved / Acknowledge Fault Modal
// ============================================================================
function openProblemResolvedModal(roomId) {
  currentActionRoomId = roomId;
  openModal("modal-problem-resolved");
}

async function submitProblemResolved(roomId) {
  const operatorEl = document.getElementById("modal-resolve-operator");
  const notesEl = document.getElementById("modal-resolve-notes");
  const clearedEl = document.getElementById("modal-hazard-cleared");
  const submitBtn = document.getElementById("modal-resolve-submit-btn");

  const operator = (operatorEl && operatorEl.value.trim()) || "Hostel Warden";
  const notes = (notesEl && notesEl.value.trim()) || "Physically inspected room, confirmed hazard resolved.";
  const faultCleared = clearedEl ? clearedEl.checked : true;

  const originalText = submitBtn.innerText;
  submitBtn.disabled = true;
  submitBtn.innerText = "Verifying Restoration Safety...";

  try {
    const res = await fetch(`/api/rooms/${roomId}/problem-resolved`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        operator: operator,
        resolution_notes: notes,
        fault_cleared: faultCleared
      })
    });
    const result = await res.json();

    closeModal("modal-problem-resolved");

    if (result.success) {
      if (result.restored) {
        showFeedbackAlert(`✓ ${result.message}`, "success");
      } else if (result.manual_lock_held) {
        showFeedbackAlert(`ℹ️ ${result.message}`, "warning");
      } else {
        showFeedbackAlert(result.message || "Resolution recorded.", "success");
      }
      await refreshSwitchPanelData(roomId, true);
    } else {
      const errMsg = result.error || result.message || "Restoration check failed.";
      showFeedbackAlert(`⛔ ${errMsg}`, "error");
      await refreshSwitchPanelData(roomId, false);
    }
  } catch (e) {
    console.error("Failed to submit problem resolution:", e);
    closeModal("modal-problem-resolved");
    showFeedbackAlert("Communication error during fault resolution verification.", "error");
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerText = originalText;
  }
}

// ============================================================================
// Dynamic UI State Refresh
// ============================================================================
async function refreshSwitchPanelData(roomId, updateChart = false) {
  try {
    const res = await fetch(`/api/rooms/${roomId}/switch-state`);
    if (!res.ok) return;
    const data = await res.json();

    // 1. Switch Panel Border & Indicator Box
    const panelEl = document.getElementById("room-switch-panel");
    const indBox = document.getElementById("switch-indicator-box");
    const bulbEl = document.getElementById("switch-bulb-icon");
    const bulbSym = document.getElementById("bulb-symbol");
    const stateText = document.getElementById("switch-state-text");
    const subStatus = document.getElementById("switch-sub-status");
    const lockBadge = document.getElementById("switch-lock-badge");

    const isEffectiveOn = (data.effective_switch_state || "ON") === "ON";
    const isManualLocked = data.manual_off_lock === 1;

    if (panelEl) {
      panelEl.className = `switch-panel ${isEffectiveOn ? 'is-on' : 'is-off'}`;
    }

    if (indBox) {
      indBox.className = `switch-indicator-box ${isEffectiveOn ? 'on' : 'off'}`;
    }

    if (bulbEl) {
      bulbEl.className = `switch-bulb ${isEffectiveOn ? 'on' : 'off'}`;
    }

    if (bulbSym) {
      bulbSym.innerText = isEffectiveOn ? "⚡" : "🛑";
    }

    if (stateText) {
      stateText.innerText = `SIMULATED SWITCH ${data.effective_switch_state}`;
      stateText.style.color = isEffectiveOn ? "var(--accent-emerald)" : "#f87171";
    }

    if (lockBadge) {
      lockBadge.style.display = isManualLocked ? "inline-flex" : "none";
    }

    if (subStatus) {
      if (isEffectiveOn) {
        subStatus.innerText = `Circuit energized • Operating within safe operational limit (${data.power_w} W)`;
      } else if (isManualLocked) {
        subStatus.innerText = "Warden manually disconnected circuit. Automatic restoration blocked until lock is released.";
      } else {
        subStatus.innerText = `Simulated cutoff active: ${data.trip_reason || 'Safety trip condition active.'}`;
      }
    }

    // 2. Metadata Grid
    const pEl = document.getElementById("meta-power-w");
    if (pEl) pEl.innerText = data.power_w;

    const metricPower = document.getElementById("metric-power");
    if (metricPower) {
      metricPower.innerHTML = `${data.power_w} <span style="font-size: 0.9rem; color: var(--text-muted); font-weight: normal;">W</span>`;
      metricPower.style.color = data.power_w > 1200 ? "#f87171" : "var(--accent-cyan)";
    }

    const stateEl = document.getElementById("meta-room-state");
    if (stateEl) stateEl.innerText = data.room_state;

    const lastByEl = document.getElementById("meta-last-by");
    if (lastByEl) lastByEl.innerText = data.last_switch_by || "System Initializer";

    const lastAtEl = document.getElementById("meta-last-at");
    if (lastAtEl) lastAtEl.innerText = data.last_switch_at || "";

    const lockStatusEl = document.getElementById("meta-lock-status");
    if (lockStatusEl) {
      lockStatusEl.innerText = isManualLocked ? "🔒 LOCKED (Auto-Restore Disabled)" : "✓ UNLOCKED";
      lockStatusEl.style.color = isManualLocked ? "#f87171" : "var(--accent-emerald)";
    }

    const reasonEl = document.getElementById("meta-trip-reason");
    if (reasonEl) {
      reasonEl.innerText = data.trip_reason || "No active fault recorded. Room operating normally.";
    }

    // 3. Blocked Alert Banner
    const blockedAlert = document.getElementById("ctrl-blocked-alert");
    const blockedMsg = document.getElementById("ctrl-blocked-msg");
    if (blockedAlert && blockedMsg) {
      if (!data.can_switch_on && !isEffectiveOn) {
        blockedAlert.style.display = "flex";
        blockedMsg.innerText = data.switch_on_block_reason || "Safety policy prevents energizing.";
      } else {
        blockedAlert.style.display = "none";
      }
    }

    // 4. Action Buttons
    const btnOff = document.getElementById("btn-manual-off");
    const btnOn = document.getElementById("btn-manual-on");
    const btnRelease = document.getElementById("btn-release-lock");

    if (btnOff) {
      const disableOff = !isEffectiveOn && isManualLocked;
      btnOff.disabled = disableOff;
      btnOff.style.opacity = disableOff ? "0.5" : "1";
      btnOff.style.cursor = disableOff ? "not-allowed" : "pointer";
    }

    if (btnOn) {
      btnOn.disabled = isEffectiveOn;
      btnOn.style.opacity = isEffectiveOn ? "0.5" : "1";
      btnOn.style.cursor = isEffectiveOn ? "not-allowed" : "pointer";
    }

    if (btnRelease) {
      btnRelease.style.display = isManualLocked ? "inline-flex" : "none";
    }

    // 5. Optimization Console Metrics & State Sync
    const optBadge = document.getElementById("opt-state-badge");
    if (optBadge && data.optimization_state) {
      optBadge.innerText = data.optimization_state;
      let badgeClass = "normal";
      if (data.optimization_state === "OPTIMIZED") badgeClass = "optimized";
      else if (data.optimization_state === "OPTIMIZATION_PARTIAL") badgeClass = "partial";
      else if (data.optimization_state === "OPTIMIZATION_FAILED") badgeClass = "failed";
      else if (data.optimization_state === "TRIPPED_CRITICAL") badgeClass = "critical";
      else if (data.optimization_state === "HIGH_USAGE") badgeClass = "warning";
      optBadge.className = `badge badge-state-${badgeClass}`;
    }

    const dispMax = document.getElementById("disp-max-threshold");
    if (dispMax && data.threshold_w !== undefined) dispMax.innerText = data.threshold_w;

    const dispTarget = document.getElementById("disp-opt-target");
    if (dispTarget && data.optimization_target_w !== undefined) dispTarget.innerText = data.optimization_target_w;

    const dispExcess = document.getElementById("disp-excess-w");
    if (dispExcess && data.excess_power_w !== undefined) {
      dispExcess.innerText = data.excess_power_w;
      dispExcess.style.color = data.excess_power_w > 0 ? "#f87171" : "var(--text-muted)";
    }

    const dispReq = document.getElementById("disp-reduction-req");
    if (dispReq && data.reduction_required_w !== undefined) {
      dispReq.innerText = data.reduction_required_w;
      dispReq.style.color = data.reduction_required_w > 0 ? "var(--accent-amber)" : "var(--accent-emerald)";
    }

    // Savings impact figures
    const impactW = document.getElementById("opt-impact-w");
    if (impactW && data.savings_w !== undefined) impactW.innerText = `${data.savings_w} W`;

    const impactKwh = document.getElementById("opt-impact-kwh");
    if (impactKwh && data.savings_kwh !== undefined) impactKwh.innerText = `${data.savings_kwh} kWh`;

    const impactInr = document.getElementById("opt-impact-inr");
    if (impactInr && data.savings_inr !== undefined) impactInr.innerText = `₹${data.savings_inr}`;

    // Optimization button guard
    const btnOpt = document.getElementById("btn-run-optimization");
    if (btnOpt) {
      const disableOpt = !isEffectiveOn || isManualLocked || data.is_offline;
      btnOpt.disabled = disableOpt;
      btnOpt.style.opacity = disableOpt ? "0.5" : "1";
      btnOpt.style.cursor = disableOpt ? "not-allowed" : "pointer";
    }

    // Render loads if available
    if (data.controllable_loads && data.controllable_loads.length > 0) {
      renderControllableLoads(data.controllable_loads);
    }

    // 6. Timeline Updates
    renderEventsTimeline(data.events || []);

    // 7. Update chart if requested
    if (updateChart && roomChartInstance) {
      const len = roomChartInstance.data.datasets[0].data.length;
      if (len > 0) {
        roomChartInstance.data.datasets[0].data[len - 1] = data.power_w;
        roomChartInstance.update();
      }
    }
  } catch (e) {
    console.error("Failed to refresh switch state:", e);
  }
}

function renderEventsTimeline(events) {
  const container = document.getElementById("room-events-list");
  if (!container) return;

  if (events.length === 0) {
    container.innerHTML = `
      <div style="color: var(--text-muted); font-size: 0.8rem; text-align: center; padding: 1.5rem;">
        No logged switch or trip events for this room yet.
      </div>
    `;
    return;
  }

  let html = "";
  events.forEach(ev => {
    let bColor = "var(--accent-cyan)";
    if (ev.event_type.includes("OFF") || ev.event_type.includes("REJ") || ev.event_type.includes("TRIP")) {
      bColor = "#f87171";
    } else if (ev.event_type.includes("ON") || ev.event_type.includes("RESTORE") || ev.event_type.includes("RESET")) {
      bColor = "var(--accent-emerald)";
    } else if (ev.event_type.includes("RESOLVED")) {
      bColor = "var(--accent-cyan)";
    } else if (ev.event_type.includes("LOCK")) {
      bColor = "var(--accent-amber)";
    }

    html += `
      <div style="background: rgba(15, 23, 42, 0.55); padding: 0.75rem 0.9rem; border-radius: 6px; font-size: 0.8rem; border-left: 3px solid ${bColor};">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem;">
          <span class="badge" style="font-size: 0.68rem; padding: 0.15rem 0.5rem; background: rgba(255, 255, 255, 0.05); color: ${bColor}; border: 1px solid ${bColor};">
            ${ev.event_type}
          </span>
          <span style="color: var(--text-muted); font-family: var(--font-mono); font-size: 0.7rem;">
            ${ev.timestamp}
          </span>
        </div>
        <div style="color: #f1f5f9; line-height: 1.4; margin-top: 0.2rem;">
          ${ev.explanation}
        </div>
        ${ev.action_taken ? `
        <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 0.35rem; font-style: italic;">
          Action: ${ev.action_taken}
        </div>
        ` : ''}
      </div>
    `;
  });

  container.innerHTML = html;
}

function showFeedbackAlert(msg, type = "success") {
  const el = document.getElementById("ctrl-feedback-alert");
  if (!el) return;

  el.style.display = "block";
  if (type === "success") {
    el.style.background = "rgba(16, 185, 129, 0.15)";
    el.style.border = "1px solid rgba(16, 185, 129, 0.4)";
    el.style.color = "#a7f3d0";
  } else if (type === "warning") {
    el.style.background = "rgba(245, 158, 11, 0.15)";
    el.style.border = "1px solid rgba(245, 158, 11, 0.4)";
    el.style.color = "#fde68a";
  } else {
    el.style.background = "rgba(239, 68, 68, 0.15)";
    el.style.border = "1px solid rgba(239, 68, 68, 0.4)";
    el.style.color = "#fecdd3";
  }

  el.innerHTML = msg;

  // Auto-hide success after 7 seconds
  if (type === "success") {
    setTimeout(() => {
      if (el) el.style.display = "none";
    }, 7000);
  }
}

// Reset isolated room simulation (backward compatible)
async function resetThisRoom(roomId) {
  if (!confirm(`Are you sure you want to reset the simulated cutoff for ${roomId}? This will restore its relay state to NORMAL.`)) {
    return;
  }

  try {
    const res = await fetch(`/api/rooms/${roomId}/reset-trip`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operator: "Hostel Warden" })
    });
    const result = await res.json();
    if (result.success) {
      showFeedbackAlert("✓ Simulated power cutoff reset successfully! Room relay state restored to CLOSED.", "success");
      await refreshSwitchPanelData(roomId, true);
    } else {
      showFeedbackAlert("Error resetting room: " + (result.error || "Unknown error"), "error");
    }
  } catch (e) {
    console.error("Failed to reset room trip:", e);
    showFeedbackAlert("Network error resetting room cutoff.", "error");
  }
}

// Trigger test simulated trip for this room (backward compatible)
async function triggerTestTrip(roomId) {
  try {
    const res = await fetch("/api/nilm/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenario_id: 5,
        target_room_id: roomId,
        fast_forward: true
      })
    });
    const result = await res.json();
    if (result.success) {
      showFeedbackAlert(`✓ Simulated trip triggered on ${roomId} (SIMULATION ONLY). Other rooms remain unaffected.`, "warning");
      await refreshSwitchPanelData(roomId, true);
    }
  } catch (e) {
    console.error("Failed to trigger trip:", e);
  }
}

// ============================================================================
// Load-Level Power Optimization Console Handlers
// ============================================================================

function renderControllableLoads(loads) {
  const container = document.getElementById("controllable-loads-container");
  if (!container || !Array.isArray(loads)) return;

  let html = "";
  loads.forEach(load => {
    let stateColor = "var(--accent-emerald)";
    let stateBg = "rgba(16, 185, 129, 0.15)";
    if (load.state === "OFF") {
      stateColor = "#f87171";
      stateBg = "rgba(239, 68, 68, 0.15)";
    } else if (load.state === "THROTTLED") {
      stateColor = "var(--accent-amber)";
      stateBg = "rgba(245, 158, 11, 0.15)";
    }

    const isEssential = !!load.essential;

    html += `
      <div class="load-chip ${isEssential ? 'is-essential' : ''}" style="background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 0.85rem 1rem; display: flex; flex-direction: column; gap: 0.4rem;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <strong style="color: #fff; font-size: 0.86rem;">${load.name || load.id}</strong>
          <span class="badge" style="font-size: 0.65rem; background: ${stateBg}; color: ${stateColor}; border: 1px solid ${stateColor};">
            ${load.state}
          </span>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.78rem; color: var(--text-secondary);">
          <span>Rated: <strong>${load.rated_w} W</strong></span>
          <span>Current: <strong style="color: ${load.effective_w > 0 ? 'var(--accent-cyan)' : 'var(--text-muted)'};">${load.effective_w} W</strong></span>
        </div>
        <div style="font-size: 0.7rem; color: ${isEssential ? 'var(--accent-cyan)' : 'var(--text-muted)'}; margin-top: 0.1rem;">
          ${isEssential ? '🛡️ Protected (Never automatically disconnected)' : '⚡ Controllable (Eligible for optimization shedding)'}
        </div>
      </div>
    `;
  });

  container.innerHTML = html;
}

function showOptFeedback(msg, type = "success") {
  const el = document.getElementById("opt-feedback-alert");
  if (!el) return;

  el.style.display = "block";
  if (type === "success") {
    el.style.background = "rgba(16, 185, 129, 0.15)";
    el.style.border = "1px solid rgba(16, 185, 129, 0.4)";
    el.style.color = "#a7f3d0";
  } else if (type === "warning") {
    el.style.background = "rgba(245, 158, 11, 0.15)";
    el.style.border = "1px solid rgba(245, 158, 11, 0.4)";
    el.style.color = "#fde68a";
  } else {
    el.style.background = "rgba(239, 68, 68, 0.15)";
    el.style.border = "1px solid rgba(239, 68, 68, 0.4)";
    el.style.color = "#fecdd3";
  }

  el.innerHTML = msg;

  if (type === "success") {
    setTimeout(() => {
      if (el) el.style.display = "none";
    }, 8000);
  }
}

async function runRoomPowerOptimization(roomId) {
  const btn = document.getElementById("btn-run-optimization");
  const origText = btn ? btn.innerText : "";
  if (btn) {
    btn.disabled = true;
    btn.innerText = "Evaluating Controllable Loads...";
  }

  try {
    const res = await fetch(`/api/rooms/${roomId}/optimize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operator: "Hostel Warden" })
    });
    const result = await res.json();

    if (result.success) {
      const outcome = result.outcome || {};
      const status = outcome.status || "OPTIMIZED";
      let alertType = "success";
      let summaryText = "";

      if (status === "OPTIMIZED") {
        summaryText = `🌱 <strong>Optimization Target Reached!</strong> Shed ${outcome.power_reduction_w || 0} W (Resulting Power: ${outcome.resulting_power_w} W, Target: ${outcome.target_w} W). Estimated hourly savings: ₹${outcome.savings_inr} (${outcome.savings_kwh} kWh).`;
      } else if (status === "OPTIMIZATION_PARTIAL") {
        alertType = "warning";
        summaryText = `⚠️ <strong>Partial Optimization:</strong> Reduced ${outcome.power_reduction_w || 0} W to ${outcome.resulting_power_w} W, but could not safely reach the full ${outcome.target_w} W target without shedding essential lighting.`;
      } else if (status === "OPTIMIZATION_FAILED") {
        alertType = "error";
        summaryText = `❌ <strong>Optimization Failed:</strong> No eligible controllable loads could be shed safely to achieve the ${outcome.target_w} W target.`;
      } else {
        summaryText = result.message || "Optimization executed.";
      }

      showOptFeedback(summaryText, alertType);
      await refreshSwitchPanelData(roomId, true);
    } else {
      const errMsg = result.error || result.message || "Optimization could not be completed.";
      showOptFeedback(`⛔ ${errMsg}`, "error");
      await refreshSwitchPanelData(roomId, false);
    }
  } catch (e) {
    console.error("Optimization failed:", e);
    showOptFeedback("Network error executing power optimization.", "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerText = origText;
    }
  }
}

async function setQuickTarget(roomId, targetW) {
  try {
    const res = await fetch(`/api/rooms/${roomId}/target`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_w: targetW })
    });
    const result = await res.json();
    if (result.success) {
      showOptFeedback(`✓ Preferred Optimization Target updated to <strong>${targetW} W</strong>. Reduction required recalculated.`, "success");
      await refreshSwitchPanelData(roomId, false);
    } else {
      showOptFeedback(`⛔ ${result.error || 'Failed to update target'}`, "error");
    }
  } catch (e) {
    console.error("Failed to update target:", e);
    showOptFeedback("Error updating optimization target.", "error");
  }
}

function promptCustomTarget(roomId) {
  const currentTarget = document.getElementById("disp-opt-target") ? document.getElementById("disp-opt-target").innerText : "800";
  const input = prompt(`Enter new Preferred Optimization Target in Watts for ${roomId} (e.g. 700 to 1100 W):`, currentTarget);
  if (!input) return;

  const val = parseFloat(input.trim());
  if (isNaN(val) || val <= 0) {
    alert("Please enter a valid positive number for the optimization target.");
    return;
  }

  setQuickTarget(roomId, val);
}

