let currentResults = [];

async function startScrape() {
  const query = document.getElementById("query").value.trim();
  const location = document.getElementById("location").value.trim();
  const maxResults = parseInt(document.getElementById("max-results").value);
  const fetchEmails = document.getElementById("fetch-emails").checked;

  if (!query || !location) {
    showError("Please enter both an industry/business type and a location.");
    return;
  }

  setLoading(true, fetchEmails);
  clearError();
  hideResults();

  try {
    const response = await fetch("/scrape", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, location, max_results: maxResults, fetch_emails: fetchEmails }),
    });

    const data = await response.json();

    if (!response.ok || data.error) {
      showError(data.error || "An unexpected error occurred.");
      return;
    }

    currentResults = data.results;
    renderResults(data.results, query, location);

  } catch (err) {
    showError("Network error: " + err.message);
  } finally {
    setLoading(false);
  }
}

function renderResults(results, query, location) {
  const section = document.getElementById("results-section");
  const body = document.getElementById("results-body");
  const countEl = document.getElementById("results-count");
  const queryEl = document.getElementById("results-query");
  const emptyState = document.getElementById("empty-state");
  const exportBtn = document.getElementById("export-btn");

  if (results.length === 0) {
    emptyState.classList.remove("hidden");
    exportBtn.disabled = true;
    return;
  }

  countEl.textContent = `${results.length} lead${results.length !== 1 ? "s" : ""} found`;
  queryEl.textContent = `"${query}" in ${location}`;

  // Stats
  const withEmail = results.filter(r => r.email && r.email !== "N/A").length;
  const withPhone = results.filter(r => r.phone && r.phone !== "N/A").length;
  const withWebsite = results.filter(r => r.website && r.website !== "N/A").length;
  const ratings = results
    .map(r => parseFloat(r.rating))
    .filter(n => !isNaN(n));
  const avgRating = ratings.length > 0
    ? (ratings.reduce((a, b) => a + b, 0) / ratings.length).toFixed(1)
    : "—";

  document.getElementById("stat-with-email").textContent = withEmail;
  document.getElementById("stat-with-phone").textContent = withPhone;
  document.getElementById("stat-with-website").textContent = withWebsite;
  document.getElementById("stat-avg-rating").textContent = avgRating !== "—" ? `★ ${avgRating}` : "—";

  // Rows
  body.innerHTML = "";
  results.forEach((r, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${i + 1}</td>
      <td>
        <div class="biz-name">${escHtml(r.business_name)}</div>
        ${r.maps_url && r.maps_url !== "N/A"
        ? `<a class="maps-link" href="${r.maps_url}" target="_blank" rel="noopener">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
              Maps
            </a>`
        : ""}
      </td>
      <td>${r.owner_name && r.owner_name !== "N/A" ? escHtml(r.owner_name) : '<span class="tag-na">—</span>'}</td>
      <td>${r.category && r.category !== "N/A" ? escHtml(r.category) : '<span class="tag-na">—</span>'}</td>
      <td>${r.phone && r.phone !== "N/A"
        ? `<span class="pill-phone">${escHtml(r.phone)}</span>`
        : '<span class="tag-na">—</span>'}</td>
      <td>${r.email && r.email !== "N/A"
        ? `<span class="pill-email">${escHtml(r.email)}</span>`
        : '<span class="tag-na">—</span>'}</td>
      <td>${r.website && r.website !== "N/A"
        ? `<a class="site-link" href="${r.website}" target="_blank" rel="noopener">${truncateUrl(r.website)}</a>`
        : '<span class="tag-na">—</span>'}</td>
      <td>${r.address && r.address !== "N/A" ? escHtml(r.address) : '<span class="tag-na">—</span>'}</td>
      <td>${r.rating && r.rating !== "N/A"
        ? `<span class="rating-badge">★ ${escHtml(r.rating)}</span>`
        : '<span class="tag-na">—</span>'}</td>
    `;
    body.appendChild(tr);
  });

  section.classList.remove("hidden");
  exportBtn.disabled = false;

  // Smooth scroll to results
  setTimeout(() => section.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
}

async function exportCSV() {
  if (!currentResults.length) return;

  try {
    const response = await fetch("/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ results: currentResults }),
    });

    if (!response.ok) {
      showError("Failed to export CSV.");
      return;
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "b2b_leads.csv";
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    showError("Export error: " + err.message);
  }
}

// ── Helpers ──

function setLoading(loading, fetchEmails = true) {
  const btn = document.getElementById("scrape-btn");
  const statusBar = document.getElementById("status-bar");
  const statusText = document.getElementById("status-text");
  btn.disabled = loading;
  if (loading) {
    btn.innerHTML = `<div class="spinner" style="border-top-color:white;border-color:rgba(255,255,255,0.3)"></div> Scraping...`;
    statusBar.classList.remove("hidden");
    const timeHint = fetchEmails ? "2–4 minutes" : "~1 minute";
    statusText.textContent = `Scraping Google Maps — please wait (${timeHint})…`;
  } else {
    statusBar.classList.add("hidden");
    btn.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg> Find Leads`;
  }
}

function showError(msg) {
  const box = document.getElementById("error-box");
  document.getElementById("error-text").textContent = msg;
  box.classList.remove("hidden");
}

function clearError() {
  document.getElementById("error-box").classList.add("hidden");
}

function hideResults() {
  document.getElementById("results-section").classList.add("hidden");
  document.getElementById("empty-state").classList.add("hidden");
  currentResults = [];
  document.getElementById("export-btn").disabled = true;
}

function escHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function truncateUrl(url) {
  try {
    const u = new URL(url);
    const host = u.hostname.replace(/^www\./, "");
    return host.length > 28 ? host.slice(0, 28) + "…" : host;
  } catch {
    return url.length > 30 ? url.slice(0, 30) + "…" : url;
  }
}

// Allow Enter key to trigger search
document.addEventListener("DOMContentLoaded", () => {
  ["query", "location"].forEach(id => {
    document.getElementById(id).addEventListener("keydown", e => {
      if (e.key === "Enter") startScrape();
    });
  });
});
