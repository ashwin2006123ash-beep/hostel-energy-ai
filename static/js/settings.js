/* ==========================================================================
   Hostel Energy AI - Settings Controller
   ========================================================================== */

function showSettingsFeedback(type, message) {
  const container = document.getElementById("settings-alert-container");
  if (!container) return;

  container.style.display = "block";
  if (type === "success") {
    container.style.background = "rgba(16, 185, 129, 0.15)";
    container.style.border = "1px solid rgba(16, 185, 129, 0.4)";
    container.style.color = "#34d399";
    container.innerHTML = `✓ ${message}`;
  } else {
    container.style.background = "rgba(239, 68, 68, 0.15)";
    container.style.border = "1px solid rgba(239, 68, 68, 0.4)";
    container.style.color = "#f87171";
    container.innerHTML = `⚠️ ${message}`;
  }
  container.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function saveSettings(event) {
  event.preventDefault();

  const emptyVal = document.getElementById("set-empty-threshold").value.trim();
  const highVal = document.getElementById("set-high-power-threshold").value.trim();
  const targetVal = document.getElementById("set-optimization-target") ? document.getElementById("set-optimization-target").value.trim() : "800.0";
  const tolVal = document.getElementById("set-optimization-tolerance") ? document.getElementById("set-optimization-tolerance").value.trim() : "50.0";
  const critVal = document.getElementById("set-critical-safety-threshold") ? document.getElementById("set-critical-safety-threshold").value.trim() : "2400.0";
  const stabVal = document.getElementById("set-stability-check-seconds") ? document.getElementById("set-stability-check-seconds").value.trim() : "60";
  const pVal = document.getElementById("set-persistence").value.trim();
  const gVal = document.getElementById("set-geyser").value.trim();

  // 1. Client-Side Validation
  if (!highVal || isNaN(highVal) || Number(highVal) <= 0) {
    showSettingsFeedback("error", "Maximum Room Power Limit must be a positive number greater than 0 W.");
    return;
  }
  if (!targetVal || isNaN(targetVal) || Number(targetVal) <= 0) {
    showSettingsFeedback("error", "Default Optimization Target must be a positive number greater than 0 W.");
    return;
  }
  if (Number(targetVal) >= Number(highVal)) {
    showSettingsFeedback("error", `Preferred Optimization Target (${targetVal} W) must be strictly lower than Maximum Power Limit (${highVal} W).`);
    return;
  }
  if (!emptyVal || isNaN(emptyVal) || Number(emptyVal) < 0) {
    showSettingsFeedback("error", "Vacant Room Wattage Threshold must be a non-negative number (≥ 0 W).");
    return;
  }
  if (!pVal || isNaN(pVal) || Number(pVal) <= 0) {
    showSettingsFeedback("error", "Vacant Auto-Trip Persistence Window must be a positive number of minutes.");
    return;
  }
  if (!gVal || isNaN(gVal) || Number(gVal) <= 0) {
    showSettingsFeedback("error", "Continuous Geyser Run Limit must be a positive number of minutes.");
    return;
  }

  const payload = {
    daytime_start: document.getElementById("set-daytime-start").value.trim(),
    daytime_end: document.getElementById("set-daytime-end").value.trim(),
    empty_room_threshold_w: emptyVal,
    high_power_threshold_w: highVal,
    default_optimization_target_w: targetVal,
    optimization_tolerance_w: tolVal,
    critical_safety_threshold_w: critVal,
    stability_check_seconds: stabVal,
    persistence_window_min: pVal,
    geyser_persistence_min: gVal,
    real_hardware_relay_enabled: "0" // Safety lock permanently kept at 0
  };

  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const result = await res.json();
    if (res.ok && result.status === "success") {
      showSettingsFeedback(
        "success",
        `Operational policies synchronized! Maximum Limit: <strong>${payload.high_power_threshold_w} W</strong>, Optimization Target: <strong>${payload.default_optimization_target_w} W</strong> (Tolerance: ±${payload.optimization_tolerance_w} W, Critical Trip: ${payload.critical_safety_threshold_w} W). Live Room cards and optimization engines have been updated.`
      );
    } else {
      showSettingsFeedback("error", result.message || "Failed to update configuration.");
    }
  } catch (e) {
    console.error("Failed to update settings:", e);
    showSettingsFeedback("error", "Network error updating policy configuration.");
  }
}
