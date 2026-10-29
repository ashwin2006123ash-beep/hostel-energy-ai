/* ==========================================================================
   Hostel Energy AI - Main JavaScript & Global Utilities
   ========================================================================== */

// Open AI Diagnostic Report Modal
async function openDiagnosticModal(anomalyId) {
  const modal = document.getElementById("diagnostic-modal");
  const modalBody = document.getElementById("modal-body-content");
  const modalTitle = document.getElementById("modal-title");
  
  if (!modal || !modalBody) return;

  modalBody.innerHTML = `
    <div style="text-align: center; padding: 2rem; color: var(--text-secondary);">
      <div class="fan-spinner" style="font-size: 2rem; margin-bottom: 0.75rem;">⚡</div>
      <p>Analyzing telemetry contextual evidence with AI Energy Detective...</p>
    </div>
  `;
  modal.classList.add("active");

  try {
    const res = await fetch(`/api/anomalies/${anomalyId}/diagnostic`);
    if (!res.ok) throw new Error("Failed to load diagnostic details");
    const data = await res.json();

    modalTitle.innerText = `Diagnostic Case #${data.anomaly_id}: ${data.context_summary.block_id}`;
    
    // Build Ranked Causes HTML
    let causesHtml = "";
    if (data.ranked_causes && data.ranked_causes.length > 0) {
      data.ranked_causes.forEach((c, idx) => {
        const confPct = Math.round(c.confidence * 100);
        let barColor = "var(--accent-cyan)";
        if (confPct >= 75) barColor = "var(--accent-rose)";
        else if (confPct >= 50) barColor = "var(--accent-amber)";

        const evidenceItems = c.evidence.map(e => `<li>${e}</li>`).join("");

        causesHtml += `
          <div style="background: rgba(0,0,0,0.3); border: 1px solid var(--border-glass); border-radius: var(--radius-sm); padding: 1rem; margin-bottom: 0.85rem;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
              <span style="font-weight: 700; font-size: 0.95rem; color: #fff;">
                #${idx + 1} ${c.title}
              </span>
              <span style="font-family: var(--font-mono); font-weight: 700; color: ${barColor}; font-size: 0.88rem;">
                ${confPct}% Confidence
              </span>
            </div>
            
            <div style="height: 6px; background: rgba(255,255,255,0.08); border-radius: 3px; overflow: hidden; margin-bottom: 0.75rem;">
              <div style="height: 100%; width: ${confPct}%; background: ${barColor}; border-radius: 3px;"></div>
            </div>

            <div style="font-size: 0.82rem; color: var(--text-secondary); margin-bottom: 0.5rem;">
              <strong style="color: var(--text-primary);">Observed Evidence:</strong>
              <ul style="padding-left: 1.25rem; margin-top: 0.25rem; line-height: 1.5;">
                ${evidenceItems}
              </ul>
            </div>

            <div style="font-size: 0.82rem; background: rgba(6, 182, 212, 0.08); border-left: 3px solid var(--accent-cyan); padding: 0.5rem 0.75rem; border-radius: 4px; color: #bae6fd;">
              <strong>Actionable Protocol:</strong> ${c.action}
            </div>
          </div>
        `;
      });
    } else {
      causesHtml = `<p style="color: var(--text-muted);">No specific diagnostic hypothesis reached statistical confidence threshold.</p>`;
    }

    modalBody.innerHTML = `
      <!-- Context Parameter Bar -->
      <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; background: rgba(255,255,255,0.03); border: 1px solid var(--border-glass); border-radius: var(--radius-sm); padding: 0.85rem; margin-bottom: 1.25rem; text-align: center;">
        <div>
          <span style="display: block; font-size: 0.72rem; color: var(--text-secondary); text-transform: uppercase;">Actual Power</span>
          <strong style="font-size: 1.15rem; color: #fff;">${data.context_summary.actual_kw} kW</strong>
        </div>
        <div>
          <span style="display: block; font-size: 0.72rem; color: var(--text-secondary); text-transform: uppercase;">Expected Power</span>
          <strong style="font-size: 1.15rem; color: var(--accent-cyan);">${data.context_summary.expected_kw} kW</strong>
        </div>
        <div>
          <span style="display: block; font-size: 0.72rem; color: var(--text-secondary); text-transform: uppercase;">Residual Delta</span>
          <strong style="font-size: 1.15rem; color: var(--accent-rose);">+${data.context_summary.residual_kw} kW</strong>
        </div>
        <div>
          <span style="display: block; font-size: 0.72rem; color: var(--text-secondary); text-transform: uppercase;">Occupancy</span>
          <strong style="font-size: 1.15rem; color: #fff;">${data.context_summary.occupancy_rate_pct}%</strong>
        </div>
      </div>

      <div style="margin-bottom: 1rem;">
        <h4 style="font-size: 0.95rem; margin-bottom: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary);">
          Evidence-Ranked Diagnostic Hypotheses
        </h4>
        ${causesHtml}
      </div>

      <!-- Investigation Action Controls -->
      <div style="background: rgba(0,0,0,0.2); border-radius: var(--radius-sm); padding: 1rem; border: 1px solid var(--border-glass);">
        <h5 style="font-size: 0.85rem; margin-bottom: 0.5rem; color: var(--text-secondary);">Audit Workflow Status</h5>
        <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
          <button class="btn btn-secondary btn-sm" onclick="setAnomalyStatus(${anomalyId}, 'Investigating')">Mark Investigating</button>
          <button class="btn btn-emerald btn-sm" onclick="setAnomalyStatus(${anomalyId}, 'Resolved')">Mark Resolved</button>
          <button class="btn btn-secondary btn-sm" onclick="setAnomalyStatus(${anomalyId}, 'False_Positive')">Mark False Positive</button>
        </div>
      </div>

      <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 1rem; line-height: 1.4;">
        * Note: Cause ranking is a statistical heuristic. Physical on-site inspection is required for confirmation.
      </div>
    `;

  } catch (err) {
    modalBody.innerHTML = `<p style="color: var(--accent-rose); padding: 1.5rem;">Error loading report: ${err.message}</p>`;
  }
}

function closeDiagnosticModal() {
  const modal = document.getElementById("diagnostic-modal");
  if (modal) modal.classList.remove("active");
}

// Update Anomaly Status via API
async function setAnomalyStatus(anomalyId, newStatus) {
  try {
    const res = await fetch(`/api/anomalies/${anomalyId}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus, notes: `Status manually updated to ${newStatus}` })
    });
    if (res.ok) {
      alert(`Anomaly #${anomalyId} status updated to: ${newStatus}`);
      closeDiagnosticModal();
      if (typeof reloadAnomaliesList === "function") {
        reloadAnomaliesList();
      }
    }
  } catch (e) {
    alert("Failed to update status: " + e.message);
  }
}

// Close modal when clicking outside container
window.addEventListener("click", function(event) {
  const modal = document.getElementById("diagnostic-modal");
  if (event.target === modal) {
    closeDiagnosticModal();
  }
});
