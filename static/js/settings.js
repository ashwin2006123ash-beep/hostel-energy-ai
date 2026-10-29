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
  const pVal = document.getElementById("set-persistence").value.trim();
  const gVal = document.getElementById("set-geyser").value.trim();

  // 1. Client-Side Validation
  if (!highVal || isNaN(highVal) || Number(highVal) <= 0) {
    showSettingsFeedback("error", "Maximum Room Power Limit must be a positive number greater than 0 W.");
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
        `Operational policies synchronized! Maximum Room Power Limit is now set to <strong>${payload.high_power_threshold_w} W</strong> (Vacant standby: <strong>${payload.empty_room_threshold_w} W</strong>). Live Room cards and detection engines have been updated.`
      );
    } else {
      showSettingsFeedback("error", result.message || "Failed to update configuration.");
    }
  } catch (e) {
    console.error("Failed to update settings:", e);
    showSettingsFeedback("error", "Network error updating policy configuration.");
  }
}
