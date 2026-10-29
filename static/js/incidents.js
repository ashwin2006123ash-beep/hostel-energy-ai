/* ==========================================================================
   Hostel Energy AI - Incident Memory Controller ("Learn Once, Act Smart")
   ========================================================================== */

let allIncidents = [];

document.addEventListener("DOMContentLoaded", function() {
  // Pre-fill form from URL params if present
  const params = new URLSearchParams(window.location.search);
  const roomParam = params.get("room");
  const blockParam = params.get("block");
  if (roomParam) document.getElementById("form-room").value = roomParam;
  if (blockParam) document.getElementById("form-block").value = blockParam;

  loadIncidents();
});

async function loadIncidents() {
  const container = document.getElementById("incidents-list");
  if (!container) return;

  try {
    const res = await fetch("/api/incidents");
    if (!res.ok) {
      container.innerHTML = `<div class="glass-panel" style="padding: 2rem; text-align: center; color: var(--text-muted);">No recorded incidents.</div>`;
      return;
    }
    const data = await res.json();
    allIncidents = data.incidents || [];

    const countEl = document.getElementById("incidents-count");
    if (countEl) countEl.innerText = allIncidents.length;

    renderIncidents(allIncidents);
  } catch (e) {
    console.error("Failed to load incidents:", e);
    container.innerHTML = `<div class="glass-panel" style="padding: 2rem; text-align: center; color: var(--text-muted);">Error loading incident memory.</div>`;
  }
}

function renderIncidents(incidents) {
  const container = document.getElementById("incidents-list");
  if (!container) return;

  if (incidents.length === 0) {
    container.innerHTML = `
      <div class="glass-panel" style="padding: 2.5rem; text-align: center; color: var(--text-muted);">
        No matching verified incidents found.
      </div>
    `;
    return;
  }

  let html = "";
  incidents.forEach(inc => {
    html += `
      <div class="glass-panel" style="padding: 1.25rem 1.5rem; border-left: 4px solid var(--accent-emerald);">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.75rem;">
          <div>
            <div style="display: flex; align-items: center; gap: 0.5rem;">
              <h4 style="font-size: 1.05rem; font-weight: 700; color: #fff;">${inc.room_number} • ${inc.block_id}</h4>
              <span class="badge badge-normal" style="background: rgba(16, 185, 129, 0.15); color: #34d399;">Verified Resolution</span>
            </div>
            <div style="font-size: 0.75rem; color: var(--text-muted); font-family: var(--font-mono); margin-top: 0.2rem;">
              Logged: ${inc.incident_date} • Verified by: ${inc.verified_by || 'Hostel Warden'}
            </div>
          </div>
          <div style="text-align: right;">
            <div style="font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase;">Measured Savings</div>
            <div style="font-size: 1.15rem; font-weight: 800; color: var(--accent-emerald);">
              ₹${(inc.savings_inr_post || 0).toFixed(0)} <span style="font-size: 0.75rem; font-weight: normal; color: var(--text-secondary);">(${inc.savings_kwh_post || 0} kWh)</span>
            </div>
          </div>
        </div>

        <div style="margin-bottom: 0.6rem; font-size: 0.84rem; line-height: 1.4;">
          <strong style="color: var(--accent-amber);">Observed Symptom:</strong> 
          <span style="color: #cbd5e1;">${inc.anomaly_symptom}</span>
        </div>

        <div style="margin-bottom: 0.6rem; font-size: 0.84rem; line-height: 1.4;">
          <strong style="color: var(--accent-rose);">Confirmed Cause:</strong> 
          <span style="color: #fff; font-weight: 500;">${inc.confirmed_cause}</span>
        </div>

        <div style="margin-bottom: 0.6rem; font-size: 0.84rem; line-height: 1.4;">
          <strong style="color: var(--accent-cyan);">Action Taken:</strong> 
          <span style="color: #cbd5e1;">${inc.action_taken}</span>
        </div>

        <div style="background: rgba(15, 23, 42, 0.4); padding: 0.5rem 0.75rem; border-radius: 6px; font-size: 0.8rem; color: var(--text-secondary); display: flex; align-items: center; gap: 0.4rem;">
          <span style="color: var(--accent-emerald); font-weight: bold;">✓ Result:</span> ${inc.measured_result}
        </div>
      </div>
    `;
  });

  container.innerHTML = html;
}

// Symptom matcher input listener
let matchTimeout = null;
function onMatchInput() {
  clearTimeout(matchTimeout);
  matchTimeout = setTimeout(async () => {
    const symptom = (document.getElementById("matcher-input").value || "").trim();
    const resultsContainer = document.getElementById("matcher-results");
    if (!symptom) {
      resultsContainer.style.display = "none";
      renderIncidents(allIncidents);
      return;
    }

    try {
      const res = await fetch(`/api/incidents/match?symptom=${encodeURIComponent(symptom)}`);
      if (!res.ok) return;
      const data = await res.json();
      const matches = data.matches || [];

      if (matches.length > 0) {
        resultsContainer.style.display = "block";
        resultsContainer.innerHTML = `
          <div style="background: rgba(6, 182, 212, 0.08); border: 1px solid rgba(6, 182, 212, 0.25); border-radius: 8px; padding: 0.75rem; font-size: 0.8rem;">
            <div style="color: var(--accent-cyan); font-weight: 700; margin-bottom: 0.35rem;">
              🧠 Found ${matches.length} Past Matching Case(s) (Warden Approval Required)
            </div>
            ${matches.map(m => `
              <div style="margin-top: 0.4rem; padding-top: 0.4rem; border-top: 1px solid rgba(255, 255, 255, 0.06);">
                <strong>${m.incident.room_number}:</strong> ${m.incident.confirmed_cause} &rarr; <em>${m.recommended_action}</em> (Saved ₹${m.historical_savings_inr})
              </div>
            `).join("")}
          </div>
        `;
      } else {
        resultsContainer.style.display = "none";
      }
    } catch (e) {
      console.error("Match search failed:", e);
    }
  }, 250);
}

// Form Submission
async function submitIncidentForm(event) {
  event.preventDefault();

  const payload = {
    block_id: document.getElementById("form-block").value,
    room_number: document.getElementById("form-room").value,
    anomaly_symptom: document.getElementById("form-symptom").value,
    confirmed_cause: document.getElementById("form-cause").value,
    action_taken: document.getElementById("form-action").value,
    measured_result: document.getElementById("form-result").value,
    savings_kwh_post: parseFloat(document.getElementById("form-kwh").value) || 0.0,
    verified_by: document.getElementById("form-verified-by").value
  };

  try {
    const res = await fetch("/api/incidents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const result = await res.json();
    if (result.success) {
      alert("✓ Finding successfully verified and recorded into Incident Memory!");
      document.getElementById("incident-form").reset();
      loadIncidents();
    } else {
      alert("Error saving finding: " + (result.error || "Unknown error"));
    }
  } catch (e) {
    console.error("Failed to submit incident:", e);
    alert("Network error saving finding.");
  }
}

function scrollToRecordForm() {
  const form = document.getElementById("record-form-container");
  if (form) form.scrollIntoView({ behavior: "smooth" });
}
