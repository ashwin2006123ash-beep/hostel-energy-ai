/* ==========================================================================
   Hostel Energy AI - Executive Reports View Controller
   ========================================================================== */

document.addEventListener("DOMContentLoaded", function() {
  loadReportSummary();
});

async function loadReportSummary() {
  const timeframe = document.getElementById("report-timeframe").value || "30d";
  const tbody = document.getElementById("report-blocks-body");
  if (!tbody) return;

  try {
    const res = await fetch(`/api/reports/summary?timeframe=${timeframe}`);
    if (!res.ok) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No report data available.</td></tr>`;
      return;
    }
    const data = await res.json();

    // Populate KPIs
    document.getElementById("rep-consumption").innerText = `${(data.total_consumption_kwh || 0).toLocaleString()} kWh`;
    document.getElementById("rep-cost").innerText = `₹${(data.estimated_bill_inr || 0).toLocaleString()}`;
    document.getElementById("rep-savings").innerText = `₹${(data.verified_savings_inr || 0).toLocaleString()}`;
    document.getElementById("rep-savings-kwh").innerText = `${(data.verified_savings_kwh || 0).toLocaleString()} kWh verified reduction`;
    document.getElementById("rep-flagged").innerText = `${data.flagged_rooms_count || 0} Rooms`;
    document.getElementById("rep-anomalies").innerText = `${data.total_anomalies || 0} total telemetry excursions`;

    // Populate Block Breakdown Table
    const blocks = data.blocks || [];
    if (blocks.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No block records found.</td></tr>`;
      return;
    }

    let rowsHtml = "";
    blocks.forEach(b => {
      const co2 = (b.consumption_kwh * 0.82).toFixed(1);
      rowsHtml += `
        <tr>
          <td>
            <strong style="color: #fff; font-size: 0.95rem;">${b.block_id}</strong>
          </td>
          <td style="font-weight: 600; color: var(--accent-cyan);">
            ${b.consumption_kwh.toLocaleString()} kWh
          </td>
          <td style="font-weight: 600;">
            ₹${b.estimated_bill_inr.toLocaleString()}
          </td>
          <td>
            ${b.avg_occupancy} students
          </td>
          <td>
            <span style="font-weight: 700; color: var(--accent-amber);">${b.per_student_kwh} kWh</span> / student
          </td>
          <td style="color: #94a3b8; font-size: 0.85rem;">
            ${co2} kg CO₂e
          </td>
        </tr>
      `;
    });

    tbody.innerHTML = rowsHtml;
  } catch (e) {
    console.error("Failed to load reports summary:", e);
    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">Error loading report summary.</td></tr>`;
  }
}
