/* ==========================================================================
   Hostel Energy AI - Room Detail Controller
   ========================================================================== */

let roomChartInstance = null;

document.addEventListener("DOMContentLoaded", function() {
  initRoomChart();
});

function initRoomChart() {
  const canvas = document.getElementById("roomPowerChart");
  if (!canvas || typeof currentRoomData === "undefined") return;
  const ctx = canvas.getContext("2d");

  // Generate a realistic 15-point historical telemetry series leading to current power
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
      // Step variation
      const noise = (Math.sin(i) * 20);
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
        legend: {
          labels: { color: "#94a3b8", font: { size: 11 } }
        },
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
          ticks: {
            color: "#64748b",
            callback: v => `${v} W`
          }
        }
      }
    }
  });
}

// Reset isolated room simulation
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
      alert("✓ Simulated power cutoff reset successfully! The room relay is now restored to CLOSED.");
      window.location.reload();
    } else {
      alert("Error resetting room: " + (result.error || "Unknown error"));
    }
  } catch (e) {
    console.error("Failed to reset room trip:", e);
    alert("Network error resetting room cutoff.");
  }
}

// Trigger test simulated trip for this room
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
      alert(`✓ Simulated trip triggered on ${roomId} (SIMULATION ONLY). Other rooms remain unaffected.`);
      window.location.reload();
    }
  } catch (e) {
    console.error("Failed to trigger trip:", e);
  }
}
