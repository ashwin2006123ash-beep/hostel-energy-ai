/* ==========================================================================
   Hostel Energy AI - Recommendations View Controller
   ========================================================================== */

let recData = {
  immediate: [],
  operational: [],
  routine: []
};
let currentTab = "immediate";

document.addEventListener("DOMContentLoaded", function() {
  loadRecommendations();
});

async function loadRecommendations() {
  const container = document.getElementById("recommendations-container");
  if (!container) return;

  try {
    const res = await fetch("/api/recommendations");
    if (!res.ok) {
      container.innerHTML = `<div class="glass-panel" style="padding: 2rem; text-align: center; color: var(--text-muted);">No recommendations currently available.</div>`;
      return;
    }

    const data = await res.json();
    recData.immediate = data.immediate || [];
    recData.operational = data.operational || [];
    recData.routine = data.routine || [];

    document.getElementById("count-immediate").innerText = recData.immediate.length;
    document.getElementById("count-operational").innerText = recData.operational.length;
    document.getElementById("count-routine").innerText = recData.routine.length;

    renderTabContent(currentTab);
  } catch (e) {
    console.error("Failed to load recommendations:", e);
    container.innerHTML = `<div class="glass-panel" style="padding: 2rem; text-align: center; color: var(--text-muted);">Error loading recommendations.</div>`;
  }
}

function switchRecTab(tabName, btnElement) {
  currentTab = tabName;
  document.querySelectorAll(".btn-toggle").forEach(b => b.classList.remove("active"));
  if (btnElement) btnElement.classList.add("active");
  renderTabContent(tabName);
}

function renderTabContent(tabName) {
  const container = document.getElementById("recommendations-container");
  if (!container) return;

  const items = recData[tabName] || [];
  if (items.length === 0) {
    container.innerHTML = `
      <div class="glass-panel" style="padding: 3rem; text-align: center;">
        <div style="font-size: 1.3rem; color: var(--accent-emerald); margin-bottom: 0.5rem;">✓ No Active Flags in this Category</div>
        <p style="font-size: 0.88rem; color: var(--text-muted);">
          All monitored rooms and equipment in this tier are operating within normal baseline envelope.
        </p>
      </div>
    `;
    return;
  }

  let html = "";
  items.forEach(item => {
    // Severity and status badges
    let sevBadge = `<span class="badge badge-normal">${item.severity}</span>`;
    if (item.severity === "CRITICAL") sevBadge = `<span class="badge badge-critical">CRITICAL</span>`;
    else if (item.severity === "HIGH") sevBadge = `<span class="badge badge-warning">WARNING</span>`;

    const typeBadge = `<span class="badge badge-normal" style="background: rgba(148, 163, 184, 0.12); color: #cbd5e1; border: 1px solid rgba(255, 255, 255, 0.1);">${item.issue_type}</span>`;
    
    // Checklist items
    const checklistHtml = (item.checklist || []).map((step, idx) => `
      <li style="display: flex; gap: 0.6rem; align-items: flex-start; margin-bottom: 0.45rem; font-size: 0.84rem; color: #cbd5e1;">
        <span style="background: rgba(255, 255, 255, 0.08); color: var(--accent-cyan); width: 20px; height: 20px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; flex-shrink: 0; font-weight: 700;">${idx + 1}</span>
        <span>${step}</span>
      </li>
    `).join("");

    html += `
      <div class="glass-panel" style="padding: 1.5rem; border-left: 4px solid ${item.severity === 'CRITICAL' ? 'var(--accent-rose)' : 'var(--accent-amber)'};">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 1rem;">
          <div>
            <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.25rem;">
              <h3 style="font-size: 1.2rem; font-weight: 700; color: #fff;">${item.room_number} • ${item.block_id}</h3>
              ${sevBadge}
              ${typeBadge}
            </div>
            <div style="font-size: 0.8rem; color: var(--text-secondary);">
              Occupancy: <strong>${item.occupancy_status}</strong> • Status: <strong>${item.status}</strong>
            </div>
          </div>
          <div style="text-align: right;">
            <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">Avoidable Waste</div>
            <div style="font-size: 1.25rem; font-weight: 800; color: var(--accent-emerald);">~₹${item.potential_savings_inr}/day</div>
          </div>
        </div>

        <!-- Why Flagged Section -->
        <div style="background: rgba(15, 23, 42, 0.5); border-radius: var(--radius-sm); padding: 0.85rem 1rem; margin-bottom: 1rem;">
          <div style="font-size: 0.78rem; text-transform: uppercase; color: var(--accent-cyan); font-weight: 700; margin-bottom: 0.25rem;">
            🔍 Why This Room Was Flagged
          </div>
          <div style="font-size: 0.88rem; color: #f1f5f9; line-height: 1.45;">
            ${item.symptom}
          </div>
        </div>

        <!-- What Staff Should Check Section -->
        <div style="margin-bottom: 1rem;">
          <div style="font-size: 0.78rem; text-transform: uppercase; color: var(--text-secondary); font-weight: 700; margin-bottom: 0.5rem;">
            📋 Physical Inspection Checklist for Staff
          </div>
          <ul style="list-style: none; padding-left: 0;">
            ${checklistHtml}
          </ul>
        </div>

        <!-- Recommended Action & Controls -->
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; padding-top: 0.85rem; border-top: 1px solid var(--border-glass);">
          <div style="font-size: 0.85rem; color: #94a3b8; display: flex; align-items: center; gap: 0.4rem;">
            <strong style="color: #fff;">Recommended Action:</strong> ${item.action}
          </div>
          <div style="display: flex; gap: 0.5rem; align-items: center;">
            <button class="btn btn-secondary btn-sm" onclick="openDiagnosticModal(${item.id})">
              Detective Evidence
            </button>
            <a href="/incidents?room=${encodeURIComponent(item.room_number)}&block=${encodeURIComponent(item.block_id)}" class="btn btn-emerald btn-sm">
              Record Resolution
            </a>
          </div>
        </div>
      </div>
    `;
  });

  container.innerHTML = html;
}
