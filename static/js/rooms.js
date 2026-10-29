/* ==========================================================================
   Hostel Energy AI - Room Investigation View Controller
   ========================================================================== */

let allFetchedRooms = [];

document.addEventListener("DOMContentLoaded", function() {
  loadRoomsList();
});

async function loadRoomsList() {
  const block = document.getElementById("rooms-filter-block").value;
  const occupancy = document.getElementById("rooms-filter-occupancy").value;
  const severity = document.getElementById("rooms-filter-severity").value;
  const status = document.getElementById("rooms-filter-status").value;
  const tbody = document.getElementById("rooms-tbody");
  if (!tbody) return;

  try {
    let url = `/api/rooms?limit=100`;
    if (block !== "all") url += `&block_id=${block}`;
    if (occupancy !== "all") url += `&occupancy=${occupancy}`;
    if (severity !== "all") url += `&severity=${severity}`;
    if (status !== "all") url += `&status=${status}`;

    const res = await fetch(url);
    if (!res.ok) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 2rem;">No data available.</td></tr>`;
      return;
    }
    const data = await res.json();
    allFetchedRooms = data.rooms || [];

    updateMetricPills(allFetchedRooms);
    renderRoomsTable(allFetchedRooms);
  } catch (e) {
    console.error("Failed to load rooms list:", e);
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 2rem;">Error loading room telemetry.</td></tr>`;
  }
}

function updateMetricPills(rooms) {
  const total = rooms.length;
  const critical = rooms.filter(r => r.severity === "CRITICAL").length;
  const vacant = rooms.filter(r => (r.occupancy_status || "").toLowerCase().includes("vacant")).length;
  const resolved = rooms.filter(r => r.status === "resolved").length;

  const totalEl = document.getElementById("rooms-total-count");
  if (totalEl) totalEl.innerText = total;
  const critEl = document.getElementById("rooms-critical-count");
  if (critEl) critEl.innerText = critical;
  const vacEl = document.getElementById("rooms-vacant-count");
  if (vacEl) vacEl.innerText = vacant;
  const resEl = document.getElementById("rooms-resolved-count");
  if (resEl) resEl.innerText = resolved;
}

function filterRoomsList() {
  const searchVal = (document.getElementById("rooms-search").value || "").trim().toLowerCase();
  if (!searchVal) {
    renderRoomsTable(allFetchedRooms);
    return;
  }
  const filtered = allFetchedRooms.filter(r => {
    const rm = (r.room_number || "").toLowerCase();
    const blk = (r.block_id || "").toLowerCase();
    const cause = (r.primary_cause || "").toLowerCase();
    return rm.includes(searchVal) || blk.includes(searchVal) || cause.includes(searchVal);
  });
  renderRoomsTable(filtered);
}

function renderRoomsTable(rooms) {
  const tbody = document.getElementById("rooms-tbody");
  if (!tbody) return;

  if (rooms.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" style="text-align: center; color: var(--text-secondary); padding: 2.5rem;">
          <div style="font-size: 1.15rem; color: var(--accent-emerald); margin-bottom: 0.4rem;">✓ No Flagged Rooms Found</div>
          <div style="font-size: 0.85rem; color: var(--text-muted);">Adjust your search or filter parameters to view other rooms.</div>
        </td>
      </tr>
    `;
    return;
  }

  let html = "";
  rooms.forEach(r => {
    // Severity
    let sevBadge = `<span class="badge badge-normal">${r.severity}</span>`;
    if (r.severity === "CRITICAL") {
      sevBadge = `<span class="badge badge-critical">CRITICAL</span>`;
    } else if (r.severity === "HIGH" || r.severity === "WARNING") {
      sevBadge = `<span class="badge badge-warning">WARNING</span>`;
    }

    // Occupancy
    let occBadge = `<span class="badge badge-normal" style="background: rgba(148, 163, 184, 0.15); color: #cbd5e1;">Unknown</span>`;
    const occLower = (r.occupancy_status || "").toLowerCase();
    if (occLower.includes("vacant")) {
      occBadge = `<span class="badge badge-warning" style="background: rgba(245, 158, 11, 0.15); color: #fbbf24;">Likely Vacant</span>`;
    } else if (occLower.includes("occupied")) {
      occBadge = `<span class="badge badge-normal" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8;">Occupied</span>`;
    }

    // Investigation status select
    const statusSelect = `
      <select class="select-custom status-pill-select" onchange="updateRoomStatus(${r.id}, this.value)" style="font-size: 0.8rem; padding: 0.3rem 0.6rem;">
        <option value="pending" ${r.status === 'pending' ? 'selected' : ''}>Pending</option>
        <option value="investigating" ${r.status === 'investigating' ? 'selected' : ''}>Investigating</option>
        <option value="resolved" ${r.status === 'resolved' ? 'selected' : ''}>Resolved</option>
      </select>
    `;

    html += `
      <tr id="room-row-${r.id}">
        <td>
          <div style="font-weight: 700; color: #fff; font-size: 1rem;">${r.room_number || 'Room 101'}</div>
          <div style="font-size: 0.78rem; color: var(--text-muted);">${r.block_id} • Floor ${r.room_number ? r.room_number.replace(/\D/g, '')[0] || '1' : '1'}</div>
        </td>
        <td>
          <div>
            <span style="font-weight: 700; color: #f43f5e; font-size: 0.95rem;">${r.actual_kw.toFixed(1)} kW</span>
            <span style="color: var(--text-muted); font-size: 0.8rem;"> vs ${r.expected_kw.toFixed(1)} kW</span>
          </div>
          <div style="font-size: 0.78rem; color: var(--accent-amber); font-weight: 600;">
            +${r.residual_kw.toFixed(1)} kW residual
          </div>
        </td>
        <td>${occBadge}</td>
        <td>
          <div style="margin-bottom: 0.3rem;">${sevBadge}</div>
          <div style="font-size: 0.82rem; color: var(--text-secondary); max-width: 260px; line-height: 1.35;">
            ${r.primary_cause}
          </div>
        </td>
        <td>
          <div style="font-size: 0.82rem; color: #e2e8f0; max-width: 280px; line-height: 1.4;">
            ${r.recommended_action || 'Inspect room for unattended appliances'}
          </div>
        </td>
        <td>${statusSelect}</td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="openDiagnosticModal(${r.id})" style="font-size: 0.8rem;">
            Inspect & Evidence
          </button>
        </td>
      </tr>
    `;
  });

  tbody.innerHTML = html;
}

async function updateRoomStatus(anomalyId, newStatus) {
  try {
    const res = await fetch(`/api/anomalies/${anomalyId}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus, notes: `Status updated to ${newStatus}` })
    });
    if (res.ok) {
      const idx = allFetchedRooms.findIndex(r => r.id === anomalyId);
      if (idx !== -1) {
        allFetchedRooms[idx].status = newStatus;
        updateMetricPills(allFetchedRooms);
      }
    }
  } catch (e) {
    console.error("Failed to update status:", e);
  }
}
