// Global state
let socket = null;
let isConnected = false;
let isScanning = false;
let scanResults = {};
let currentFilter = "all";

// DOM elements
const elements = {
  statusIndicator: document.getElementById("statusIndicator"),
  statusText: document.getElementById("statusText"),
  autoDetect: document.getElementById("autoDetect"),
  networkRangeGroup: document.getElementById("networkRangeGroup"),
  networkRange: document.getElementById("networkRange"),
  notes: document.getElementById("notes"),
  scanForm: document.getElementById("scanForm"),
  scanButton: document.getElementById("scanButton"),
  progressSection: document.getElementById("progressSection"),
  progressPhase: document.getElementById("progressPhase"),
  progressPercent: document.getElementById("progressPercent"),
  progressFill: document.getElementById("progressFill"),
  progressMessage: document.getElementById("progressMessage"),
  progressDetails: document.getElementById("progressDetails"),
  resultsSection: document.getElementById("resultsSection"),
  statsGrid: document.getElementById("statsGrid"),
  totalHosts: document.getElementById("totalHosts"),
  onlineHosts: document.getElementById("onlineHosts"),
  hostsWithPorts: document.getElementById("hostsWithPorts"),
  scanSummary: document.getElementById("scanSummary"),
  searchInput: document.getElementById("searchInput"),
  sortSelect: document.getElementById("sortSelect"),
  resultsBody: document.getElementById("resultsBody"),
  historyContainer: document.getElementById("historyContainer"),
  statisticsContainer: document.getElementById("statisticsContainer"),
  refreshHistoryBtn: document.getElementById("refreshHistoryBtn"),
  errorContainer: document.getElementById("errorContainer"),
  errorMessage: document.getElementById("errorMessage"),
  notificationContainer: document.getElementById("notificationContainer"),
  notificationMessage: document.getElementById("notificationMessage"),
};

// Initialize the application
function init() {
  setupEventListeners();
  initializeSocket();

  // Add debugging after a short delay to ensure DOM is ready
  setTimeout(() => {
    debugEventListeners();
  }, 1000);
}

// Event listeners
function setupEventListeners() {
  if (elements.autoDetect) {
    elements.autoDetect.addEventListener("change", toggleNetworkRangeInput);
  }

  if (elements.scanForm) {
    elements.scanForm.addEventListener("submit", handleScanSubmit);
  } else {
    console.error("Scan form not found for event listener");
  }

  if (elements.scanButton) {
    elements.scanButton.addEventListener("click", (e) => {
      if (e.target.type !== "submit") {
        handleScanSubmit(e);
      }
    });
  }

  if (elements.searchInput) {
    elements.searchInput.addEventListener("input", filterResults);
  }
  if (elements.sortSelect) {
    elements.sortSelect.addEventListener("change", filterResults);
  }
  if (elements.refreshHistoryBtn) {
    elements.refreshHistoryBtn.addEventListener("click", requestScanHistory);
  }

  document.querySelectorAll(".filter-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      document
        .querySelectorAll(".filter-btn")
        .forEach((b) => b.classList.remove("active"));
      e.target.classList.add("active");
      currentFilter = e.target.dataset.filter;
      filterResults();
    });
  });
}

// Simplified Socket.IO initialization
function initializeSocket() {
  try {
    // Simple detection logic
    const hostname = window.location.hostname;
    const port = window.location.port;

    let serverUrl;
    if (port === "3030") {
      // Direct frontend access - connect to backend directly
      serverUrl = `http://${hostname}:5050`;
    } else {
      // Via nginx proxy
      serverUrl = `http://${hostname}:80`;
    }

    console.log(`Attempting to connect to: ${serverUrl}`);

    socket = io(serverUrl, {
      transports: ["websocket", "polling"],
      timeout: 20000,
      reconnection: true,
      reconnectionAttempts: 5,
      reconnectionDelay: 1000,
      forceNew: true,
    });

    // Connection events
    socket.on("connect", () => {
      console.log(`Connected successfully to ${serverUrl}`);
      updateConnectionStatus(true);
      clearError();
    });

    socket.on("disconnect", (reason) => {
      console.log(`Disconnected: ${reason}`);
      updateConnectionStatus(false);
      isScanning = false;
      updateScanButton();
    });

    socket.on("connect_error", (err) => {
      console.error("Connection error:", {
        message: err.message,
        description: err.description,
        type: err.type,
      });
      updateConnectionStatus(false);
      showError(`Connection failed: ${err.message || "Unknown error"}`);
    });

    // Scan events
    socket.on("connected", (data) => {
      showNotification(data.status);
    });

    socket.on("scan_started", (data) => {
      isScanning = true;
      scanResults = {};
      updateScanButton();
      showProgressSection();
      hideResultsSection();
      updateProgress(0, "initializing", data.status);
    });

    socket.on("scan_progress", (data) => {
      updateProgress(data.progress, data.phase, data.message, data);
    });

    socket.on("scan_complete", (data) => {
      isScanning = false;
      scanResults = data.results || {};
      updateScanButton();
      hideProgressSection();
      showResultsSection(data);
      showNotification(
        `Scan completed! Found ${data.summary?.online_hosts || 0} online hosts.`
      );
      requestScanHistory();
      requestStatistics();
    });

    socket.on("scan_error", (data) => {
      console.error("Scan error:", data);
      isScanning = false;
      updateScanButton();
      hideProgressSection();
      showError(data.error || "An error occurred during scanning");
    });

    socket.on("scan_history", (data) => {
      displayScanHistory(data || []);
    });

    socket.on("statistics", (data) => {
      displayStatistics(data || {});
    });

    // Auto scan events
    socket.on("auto_scan_status", (data) => {
      updateAutoScanStatus(data);
    });

    socket.on("auto_scan_scheduled", (data) => {
      showNotification(
        `Automatic scan scheduled for ${new Date(
          data.next_scan_time
        ).toLocaleTimeString()}`
      );
      updateAutoScanStatus({
        enabled: true,
        running: true,
        next_scan_time: data.next_scan_time,
        interval_minutes: data.interval_minutes,
      });
    });

    socket.on("auto_scan_toggled", (data) => {
      if (data.success) {
        showNotification(
          `Automatic scanning ${data.running ? "started" : "stopped"}`
        );
      }
    });

    // Request initial data
    setTimeout(() => {
      if (isConnected) {
        requestScanHistory();
        requestStatistics();
      }
    }, 1000);
  } catch (err) {
    console.error("Socket initialization error:", err);
    showError("Failed to initialize connection to scan server");
  }
}

// Detect the best connection method based on environment
function detectConnectionEnvironment() {
  const hostname = window.location.hostname;
  const port = window.location.port;
  const protocol = window.location.protocol;

  let serverUrl;
  let connectionType;
  if (port === "3030") {
    // Direct frontend access - connect directly to backend
    serverUrl = `${protocol}//${hostname}:5050`;
    connectionType = "direct-backend";
  }
  // Check if localhost/127.0.0.1 access
  else if (hostname === "localhost" || hostname === "127.0.0.1") {
    serverUrl = `${protocol}//${hostname}:80`;
    connectionType = "local-nginx";
  }
  // Remote access
  else {
    serverUrl = `${protocol}//${hostname}${
      port && port !== "80" ? ":" + port : ""
    }`;
    connectionType = "remote-nginx";
  }

  return {
    serverUrl,
    connectionType,
    hostname,
    port,
    isFallback: false,
  };
}

// Fallback connection attempts
function tryFallbackConnection() {
  const hostname = window.location.hostname;
  const protocol = window.location.protocol;

  // Try different connection URLs as fallbacks
  const fallbackUrls = [
    `${protocol}//${hostname}:5050`,
    `${protocol}//${hostname}:80`,
    `${protocol}//localhost:80`,
    `${protocol}//127.0.0.1:80`,
  ];

  let currentFallback = 0;

  function attemptFallback() {
    if (currentFallback >= fallbackUrls.length) {
      showError("All connection attempts failed. Please check server status.");
      return;
    }

    const fallbackUrl = fallbackUrls[currentFallback];
    console.log(
      `🔄 Attempting fallback connection ${currentFallback + 1}: ${fallbackUrl}`
    );

    if (socket) {
      socket.disconnect();
    }

    socket = io(fallbackUrl, {
      transports: ["websocket", "polling"],
      timeout: 10000,
      reconnection: false, // Disable auto-reconnection for fallback attempts
      forceNew: true,
      path: "/socket.io/",
    });

    socket.on("connect", () => {
      console.log(`✅ Fallback connection successful: ${fallbackUrl}`);
      updateConnectionStatus(true);
      clearError();
      setupSocketEventHandlers(); // Re-setup event handlers
    });

    socket.on("connect_error", () => {
      currentFallback++;
      setTimeout(attemptFallback, 2000);
    });
  }

  attemptFallback();
}

// Setup all socket event handlers
function setupSocketEventHandlers() {
  // Scan events
  socket.on("connected", (data) => {
    showNotification(data.status);
  });

  socket.on("scan_started", (data) => {
    isScanning = true;
    scanResults = {};
    updateScanButton();
    showProgressSection();
    hideResultsSection();
    updateProgress(0, "initializing", data.status);
  });

  socket.on("scan_progress", (data) => {
    updateProgress(data.progress, data.phase, data.message, data);
  });

  socket.on("scan_complete", (data) => {
    isScanning = false;
    scanResults = data.results || {};
    updateScanButton();
    hideProgressSection();
    showResultsSection(data);
    showNotification(
      `Scan completed! Found ${data.summary?.online_hosts || 0} online hosts.`
    );
    requestScanHistory();
    requestStatistics();
  });

  socket.on("scan_error", (data) => {
    console.error("Scan error:", data);
    isScanning = false;
    updateScanButton();
    hideProgressSection();
    showError(data.error || "An error occurred during scanning");
  });

  socket.on("scan_history", (data) => {
    displayScanHistory(data || []);
  });

  socket.on("statistics", (data) => {
    displayStatistics(data || {});
  });

  // Auto scan events
  socket.on("auto_scan_status", (data) => {
    updateAutoScanStatus(data);
  });

  socket.on("auto_scan_scheduled", (data) => {
    showNotification(
      `Automatic scan scheduled for ${new Date(
        data.next_scan_time
      ).toLocaleTimeString()}`
    );
    updateAutoScanStatus({
      enabled: true,
      running: true,
      next_scan_time: data.next_scan_time,
      interval_minutes: data.interval_minutes,
    });
  });

  socket.on("auto_scan_toggled", (data) => {
    if (data.success) {
      showNotification(
        `Automatic scanning ${data.running ? "started" : "stopped"}`
      );
    }
  });

  // Request initial data
  setTimeout(() => {
    if (isConnected) {
      requestScanHistory();
      requestStatistics();
    }
  }, 1000);
}

// UI Update Functions
function updateConnectionStatus(connected) {
  isConnected = connected;
  elements.statusIndicator.classList.toggle("connected", connected);
  elements.statusText.textContent = connected ? "Connected" : "Disconnected";
  elements.scanButton.disabled = !connected || isScanning;

  const connectionInfo = document.getElementById("connectionInfo");
  if (connectionInfo && connected && socket) {
    const hostname = window.location.hostname;
    connectionInfo.textContent = `(${hostname})`;
  }
}

function updateScanButton() {
  const button = elements.scanButton;
  const btnText = button.querySelector(".btn-text");
  const btnIcon = button.querySelector(".btn-icon");

  if (isScanning) {
    button.classList.add("loading");
    button.disabled = true;
    btnText.textContent = "Scanning...";
    btnIcon.textContent = "⏳";
  } else {
    button.classList.remove("loading");
    button.disabled = !isConnected;
    btnText.textContent = "Start Scan";
    btnIcon.textContent = "🔍";
  }
}

function toggleNetworkRangeInput() {
  const isChecked = elements.autoDetect.checked;
  elements.networkRangeGroup.style.display = isChecked ? "none" : "block";
}

function showProgressSection() {
  elements.progressSection.classList.remove("hidden");
}

function hideProgressSection() {
  elements.progressSection.classList.add("hidden");
}

function updateProgress(progress, phase, message, details = {}) {
  elements.progressPercent.textContent = `${Math.round(progress)}%`;
  elements.progressFill.style.width = `${progress}%`;
  elements.progressPhase.textContent = getPhaseLabel(phase);
  elements.progressMessage.textContent = message;

  let detailsHTML = "";
  if (details.current_ip) {
    detailsHTML += `<div>Scanning: ${details.current_ip}`;
    if (details.status) {
      const statusClass =
        details.status === "online" ? "status-online" : "status-offline";
      detailsHTML += ` <span class="status-badge ${statusClass}">${details.status}</span>`;
    }
    if (details.hostname && details.hostname !== "Unknown") {
      detailsHTML += ` <span style="color: #22c55e;">| ${details.hostname}</span>`;
    }
    detailsHTML += `</div>`;
  }
  if (details.open_ports && details.open_ports.length > 0) {
    detailsHTML += `<div>Open ports: ${details.open_ports.join(", ")}</div>`;
  }
  if (details.total > 0) {
    detailsHTML += `<div>Progress: ${progress.toFixed(1)}% of ${
      details.total
    } hosts</div>`;
  }
  if (details.online_hosts !== undefined) {
    detailsHTML += `<div style="color: #22c55e;">✓ ${details.online_hosts} hosts found online</div>`;
  }

  elements.progressDetails.innerHTML = detailsHTML;
}

function getPhaseLabel(phase) {
  switch (phase) {
    case "ping_sweep":
      return "📡 Ping Sweep";
    case "port_scan":
      return "🔍 Port Scanning";
    case "complete":
      return "✅ Complete";
    case "error":
      return "❌ Error";
    default:
      return "⏳ Initializing";
  }
}

function showResultsSection(data) {
  elements.resultsSection.classList.remove("hidden");

  // Update summary stats
  if (data.summary) {
    elements.statsGrid.classList.remove("hidden");
    elements.totalHosts.textContent = data.summary.total_hosts || 0;
    elements.onlineHosts.textContent = data.summary.online_hosts || 0;
    elements.hostsWithPorts.textContent = data.summary.hosts_with_ports || 0;
  }

  if (data.duration) {
    elements.scanSummary.textContent = `Completed in ${data.duration.toFixed(
      2
    )}s`;
  }

  filterResults();
}

function hideResultsSection() {
  elements.resultsSection.classList.add("hidden");
}

// Update the progress details to show hostname resolution
function updateProgress(progress, phase, message, details = {}) {
  elements.progressPercent.textContent = `${Math.round(progress)}%`;
  elements.progressFill.style.width = `${progress}%`;
  elements.progressPhase.textContent = getPhaseLabel(phase);
  elements.progressMessage.textContent = message;

  let detailsHTML = "";
  if (details.current_ip) {
    detailsHTML += `<div>Scanning: ${details.current_ip}`;
    if (details.status) {
      const statusClass =
        details.status === "online" ? "status-online" : "status-offline";
      detailsHTML += ` <span class="status-badge ${statusClass}">${details.status}</span>`;
    }
    if (details.hostname && details.hostname !== "Unknown") {
      detailsHTML += ` <span style="color: #22c55e;">| ${details.hostname}</span>`;
    }
    detailsHTML += `</div>`;
  }
  if (details.open_ports && details.open_ports.length > 0) {
    detailsHTML += `<div>Open ports: ${details.open_ports.join(", ")}</div>`;
  }
  if (details.total > 0) {
    detailsHTML += `<div>Progress: ${progress.toFixed(1)}% of ${
      details.total
    } hosts</div>`;
  }
  if (details.online_hosts !== undefined) {
    detailsHTML += `<div style="color: #22c55e;">✓ ${details.online_hosts} hosts found online</div>`;
  }

  elements.progressDetails.innerHTML = detailsHTML;
}

// Update the search functionality to include hostname searching
function filterResults() {
  const searchTerm = elements.searchInput.value.toLowerCase();
  const sortBy = elements.sortSelect.value;

  // Filter results
  let filteredResults = Object.entries(scanResults).filter(([ip, data]) => {
    // Filter by view mode
    if (currentFilter === "online" && data.status !== "online") return false;
    if (currentFilter === "offline" && data.status !== "offline") return false;

    // Filter by search term (search in both IP and hostname)
    if (searchTerm) {
      const ipMatch = ip.toLowerCase().includes(searchTerm);
      const hostnameMatch =
        data.hostname && data.hostname.toLowerCase().includes(searchTerm);
      if (!ipMatch && !hostnameMatch) return false;
    }

    return true;
  });

  // Sort results
  filteredResults.sort(([ipA, dataA], [ipB, dataB]) => {
    if (sortBy === "ports") {
      return (dataB.ports?.length || 0) - (dataA.ports?.length || 0);
    } else if (sortBy === "hostname") {
      const hostnameA = dataA.hostname || "Unknown";
      const hostnameB = dataB.hostname || "Unknown";
      return hostnameA.localeCompare(hostnameB);
    }
    // Sort by IP
    return ipA.localeCompare(ipB, undefined, { numeric: true });
  });

  // Update filter button counts
  updateFilterButtonCounts();

  // Render table
  renderResultsTable(filteredResults);
}

function updateFilterButtonCounts() {
  const total = Object.keys(scanResults).length;
  const online = Object.values(scanResults).filter(
    (host) => host.status === "online"
  ).length;
  const offline = total - online;

  document.querySelector('[data-filter="all"]').textContent = `All (${total})`;
  document.querySelector(
    '[data-filter="online"]'
  ).textContent = `Online (${online})`;
  document.querySelector(
    '[data-filter="offline"]'
  ).textContent = `Offline (${offline})`;
}

function renderResultsTable(results) {
  const tbody = elements.resultsBody;
  tbody.innerHTML = "";

  if (results.length === 0) {
    tbody.innerHTML = `
           <tr>
               <td colspan="4" style="text-align: center; padding: 40px; color: #6b7280;">
                   No results found matching your criteria
               </td>
           </tr>
       `;
    return;
  }

  results.forEach(([ip, data]) => {
    const row = document.createElement("tr");

    const statusClass =
      data.status === "online" ? "status-online" : "status-offline";
    const portsDisplay =
      data.ports && data.ports.length > 0
        ? data.ports
            .map((port) => `<span class="port-tag">${port}</span>`)
            .join("")
        : '<span style="color: #6b7280; font-style: italic;">No open ports</span>';

    const hostname =
      data.hostname && data.hostname !== "Unknown"
        ? `<span class="hostname">${data.hostname}</span>`
        : '<span style="color: #6b7280; font-style: italic;">Unknown</span>';

    row.innerHTML = `
           <td><span class="ip-address">${ip}</span></td>
           <td>${hostname}</td>
           <td><span class="status-badge ${statusClass}">${data.status}</span></td>
           <td><div class="port-list">${portsDisplay}</div></td>
       `;

    tbody.appendChild(row);
  });
}

function displayScanHistory(history) {
  const container = elements.historyContainer;

  if (history.length === 0) {
    container.innerHTML =
      '<p class="loading-text">No scan history available</p>';
    return;
  }

  container.innerHTML = history
    .map(
      (scan) => `
       <div class="history-item">
           <div class="history-header">
               <span class="history-id">Scan #${scan.scan_id}</span>
               <span class="history-date">${formatTimestamp(
                 scan.scan_date
               )}</span>
           </div>
           <div class="history-details">
               <div><strong>Network:</strong> ${
                 scan.network_range || "Auto-detected"
               }</div>
               <div><strong>Results:</strong> ${scan.online_hosts}/${
        scan.total_hosts
      } hosts online</div>
               <div><strong>Duration:</strong> ${scan.scan_duration?.toFixed(
                 2
               )}s</div>
               ${
                 scan.notes
                   ? `<div><strong>Notes:</strong> ${scan.notes}</div>`
                   : ""
               }
           </div>
       </div>
   `
    )
    .join("");
}

function displayStatistics(stats) {
  const container = elements.statisticsContainer;

  const statsItems = [
    { label: "Total Scans", value: stats.total_scans || 0 },
    { label: "Unique IPs Scanned", value: stats.unique_ips_scanned || 0 },
    {
      label: "Last Scan",
      value: stats.last_scan_date
        ? formatTimestamp(stats.last_scan_date)
        : "Never",
    },
    { label: "Avg Online Hosts", value: stats.average_online_hosts || 0 },
  ];

  container.innerHTML = statsItems
    .map(
      (item) => `
       <div class="stat-item">
           <span class="stat-label">${item.label}</span>
           <span class="stat-value">${item.value}</span>
       </div>
   `
    )
    .join("");
}

// Event Handlers
function handleScanSubmit(e) {
  e.preventDefault();

  if (!isConnected) {
    console.error("Not connected to server");
    showError("Not connected to server");
    return;
  }

  if (isScanning) {
    console.error("Already scanning");
    showError("Scan already in progress");
    return;
  }

  const networkRange = elements.autoDetect.checked
    ? null
    : elements.networkRange.value.trim() || null;
  const notes = elements.notes.value.trim() || null;

  startScan(networkRange, notes);
}

// Socket Communication
function startScan(networkRange, notes) {
  if (socket && socket.connected) {
    socket.emit("start_scan", {
      network_range: networkRange,
      notes: notes || "Web UI Scan",
    });
  } else {
    console.error("Socket not connected:", {
      socket,
      connected: socket?.connected,
    });
    showError("Not connected to server");
  }
}

function requestScanHistory() {
  if (socket && socket.connected) {
    socket.emit("get_scan_history");
  }
}

function requestStatistics() {
  if (socket && socket.connected) {
    socket.emit("get_statistics");
  }
}

// Notification Functions
function showError(message) {
  elements.errorMessage.textContent = message;
  elements.errorContainer.classList.remove("hidden");

  // Auto-hide after 10 seconds
  setTimeout(() => {
    clearError();
  }, 10000);
}

function clearError() {
  elements.errorContainer.classList.add("hidden");
}

function showNotification(message) {
  elements.notificationMessage.textContent = message;
  elements.notificationContainer.classList.remove("hidden");

  // Auto-hide after 5 seconds
  setTimeout(() => {
    clearNotification();
  }, 5000);
}

function clearNotification() {
  elements.notificationContainer.classList.add("hidden");
}

// Utility Functions
function formatTimestamp(timestamp) {
  if (!timestamp) return "Unknown";
  return new Date(timestamp).toLocaleString();
}

function formatDuration(seconds) {
  if (!seconds) return "0s";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}m ${remainingSeconds.toFixed(0)}s`;
}

function updateAutoScanStatus(data) {
  // You can add a UI element to show this information
  // For example, add a status indicator in your header
  const autoScanStatus = document.getElementById("autoScanStatus");
  if (autoScanStatus && data.enabled && data.running) {
    const nextScan = new Date(data.next_scan_time);
    autoScanStatus.textContent = `Next auto-scan: ${nextScan.toLocaleTimeString()}`;
    autoScanStatus.style.display = "block";
  }
}

// Initialize when DOM is loaded
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

// Global functions for HTML onclick handlers
window.clearError = clearError;
window.clearNotification = clearNotification;
