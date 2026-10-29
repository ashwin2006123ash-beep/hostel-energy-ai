/* ==========================================================================
   Hostel Energy AI - Trip Event History Controller
   ========================================================================== */

let allTripEvents = [];

document.addEventListener("DOMContentLoaded", function() {
  loadTripEvents();
});

async function loadTripEvents() {
  const roomFilter = document.getElementById("events-filter-room").value;
  const tbody = document.getElementById("trip-events-body");
  if (!tbody) return;

  try {
    let url = `/api/events/trips?limit=60`;
    if (roomFilter !== "all") url += `&room_id=${roomFilter}`;

    const res = await fetch(url);
    if (!res.ok) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 2rem;">No trip events recorded.</td></tr>`;
      return;
    }
    const data = await res.json();
    allTripEvents = data.events || [];
    renderTripEventsTable(allTripEvents);
  } catch (e) {
    console.error("Failed to load events:", e);
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 2rem;">Error fetching events history.</td></tr>`;
  }
}

function onEventsSearch() {
  const query = (document.getElementById("events-search").value || "").trim().toLowerCase();
  if (!query) {
    renderTripEventsTable(allTripEvents);
    return;
  }
  const filtered = allTripEvents.filter(e => {
    return (e.event_id || "").toLowerCase().includes(query) ||
           (e.room_id || "").toLowerCase().includes(query) ||
           (e.event_type || "").toLowerCase().includes(query) ||
           (e.explanation || "").toLowerCase().includes(query);
  });
  renderTripEventsTable(filtered);
}

function renderTripEventsTable(events) {
  const tbody = document.getElementById("trip-events-body");
  if (!tbody) return;

  if (events.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 2.5rem;">
          No trip or anomaly events found matching criteria.
        </td>
      </tr>
    `;
    return;
  }

  let html = "";
  events.forEach(ev => {
    let typeBadge = `<span class="badge badge-normal">${ev.event_type}</span>`;
    if (ev.event_type === "TRIP_SIMULATED") {
      typeBadge = `<span class="safety-badge" style="font-size: 0.68rem; padding: 0.15rem 0.5rem;">🛑 TRIP SIMULATED</span>`;
    } else if (ev.event_type === "RESET") {
      typeBadge = `<span class="badge badge-normal" style="background: rgba(16, 185, 129, 0.15); color: #34d399;">✓ RESET</span>`;
    } else if (ev.event_type === "HIGH_USAGE") {
      typeBadge = `<span class="badge badge-warning">⚡ HIGH USAGE</span>`;
    } else if (ev.event_type === "ANOMALY_DETECTED") {
      typeBadge = `<span class="badge badge-warning">🔍 ANOMALY</span>`;
    }

    html += `
      <tr>
        <td>
          <div style="font-family: var(--font-mono); font-weight: 700; color: #fff; font-size: 0.8rem;">
            ${ev.event_id}
          </div>
          <div style="font-size: 0.72rem; color: var(--text-muted); font-family: var(--font-mono);">
            ${ev.timestamp}
          </div>
        </td>
        <td>
          <a href="/rooms/${ev.room_id}" style="font-weight: 700; color: var(--accent-cyan);">
            ${ev.room_id} (${ev.room_number})
          </a>
          <div style="font-size: 0.72rem; color: var(--text-muted);">${ev.block_id}</div>
        </td>
        <td>${typeBadge}</td>
        <td>
          <div style="font-weight: 700; color: ${ev.observed_power_w > ev.threshold_w ? '#f87171' : 'var(--accent-cyan)'};">
            ${ev.observed_power_w} W
          </div>
          <div style="font-size: 0.72rem; color: var(--text-muted);">
            Threshold: ${ev.threshold_w} W
          </div>
        </td>
        <td>
          <span class="badge badge-normal" style="font-size: 0.7rem;">${ev.occupancy_state || 'Unknown'}</span>
        </td>
        <td style="max-width: 280px; font-size: 0.8rem; color: #cbd5e1; line-height: 1.35;">
          ${ev.explanation}
        </td>
        <td style="max-width: 220px; font-size: 0.8rem; color: var(--text-secondary); line-height: 1.35;">
          ${ev.action_taken}
        </td>
      </tr>
    `;
  });

  tbody.innerHTML = html;
}
