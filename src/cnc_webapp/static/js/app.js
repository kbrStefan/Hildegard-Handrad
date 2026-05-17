const statusOut = document.getElementById("statusOut");
const portInput = document.getElementById("portInput");
const baudrateInput = document.getElementById("baudrateInput");
const gcodeInput = document.getElementById("gcodeInput");
const jogDistanceInput = document.getElementById("jogDistanceInput");
const jogFeedrateInput = document.getElementById("jogFeedrateInput");
const connDot = document.getElementById("connDot");
const connText = document.getElementById("connText");

async function callApi(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });

  const raw = await response.text();
  let data;
  try {
    data = raw ? JSON.parse(raw) : {};
  } catch {
    const preview = raw.slice(0, 160).replace(/\s+/g, " ").trim();
    throw new Error(`Server returned non-JSON response (${response.status}): ${preview || "empty body"}`);
  }

  if (!response.ok || !data.ok) {
    throw new Error(data.error || `Request failed: ${response.status}`);
  }
  return data;
}

async function refreshStatus() {
  try {
    const data = await callApi("/api/status", { method: "GET", headers: {} });
    statusOut.textContent = JSON.stringify(data.status, null, 2);
    renderConnection(data.status);
  } catch (err) {
    statusOut.textContent = `Status unavailable: ${err.message}`;
    renderConnection({ connected: false });
  }
}

function renderConnection(status) {
  const connected = Boolean(status.connected);
  connDot.classList.toggle("online", connected);
  connDot.classList.toggle("offline", !connected);
  connText.textContent = connected ? "Connected" : "Not connected";
}

document.getElementById("connectBtn").addEventListener("click", async () => {
  try {
    await callApi("/api/serial/connect", {
      method: "POST",
      body: JSON.stringify({
        port: portInput.value.trim(),
        baudrate: Number(baudrateInput.value),
      }),
    });
    await refreshStatus();
  } catch (err) {
    alert(err.message);
  }
});

document.getElementById("disconnectBtn").addEventListener("click", async () => {
  try {
    await callApi("/api/serial/disconnect", { method: "POST", body: JSON.stringify({}) });
    await refreshStatus();
  } catch (err) {
    alert(err.message);
  }
});

document.getElementById("uploadBtn").addEventListener("click", async () => {
  const file = gcodeInput.files[0];
  if (!file) {
    alert("Select a G-code file first");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch("/api/gcode/upload", { method: "POST", body: formData });
    const raw = await response.text();
    let data;
    try {
      data = raw ? JSON.parse(raw) : {};
    } catch {
      const preview = raw.slice(0, 160).replace(/\s+/g, " ").trim();
      throw new Error(`Upload returned non-JSON response (${response.status}): ${preview || "empty body"}`);
    }

    if (!response.ok || !data.ok) {
      throw new Error(data.error || `Upload failed: ${response.status}`);
    }
    await refreshStatus();
  } catch (err) {
    alert(err.message);
  }
});

document.getElementById("startBtn").addEventListener("click", async () => {
  try {
    await callApi("/api/job/start", { method: "POST", body: JSON.stringify({}) });
    await refreshStatus();
  } catch (err) {
    alert(err.message);
  }
});

document.getElementById("stopBtn").addEventListener("click", async () => {
  try {
    await callApi("/api/job/stop", { method: "POST", body: JSON.stringify({}) });
    await refreshStatus();
  } catch (err) {
    alert(err.message);
  }
});

document.getElementById("pauseBtn").addEventListener("click", async () => {
  try {
    await callApi("/api/job/pause", { method: "POST", body: JSON.stringify({}) });
    await refreshStatus();
  } catch (err) {
    alert(err.message);
  }
});

document.getElementById("resumeBtn").addEventListener("click", async () => {
  try {
    await callApi("/api/job/resume", { method: "POST", body: JSON.stringify({}) });
    await refreshStatus();
  } catch (err) {
    alert(err.message);
  }
});

document.getElementById("estopBtn").addEventListener("click", async () => {
  const confirmed = window.confirm("Send emergency stop (M112) now?");
  if (!confirmed) {
    return;
  }

  try {
    await callApi("/api/job/estop", { method: "POST", body: JSON.stringify({}) });
    await refreshStatus();
  } catch (err) {
    alert(err.message);
  }
});

document.getElementById("homeXBtn").addEventListener("click", async () => {
  try {
    await callApi("/api/home", { method: "POST", body: JSON.stringify({ axes: ["X"] }) });
    await refreshStatus();
  } catch (err) {
    alert(err.message);
  }
});

document.getElementById("homeYBtn").addEventListener("click", async () => {
  try {
    await callApi("/api/home", { method: "POST", body: JSON.stringify({ axes: ["Y"] }) });
    await refreshStatus();
  } catch (err) {
    alert(err.message);
  }
});

document.getElementById("homeZBtn").addEventListener("click", async () => {
  try {
    await callApi("/api/home", { method: "POST", body: JSON.stringify({ axes: ["Z"] }) });
    await refreshStatus();
  } catch (err) {
    alert(err.message);
  }
});

document.querySelectorAll(".jog-btn").forEach((button) => {
  button.addEventListener("click", async () => {
    const axis = button.dataset.axis;
    const direction = Number(button.dataset.dir || "1");
    const distance = Number(jogDistanceInput.value) * direction;
    const feedrate = Number(jogFeedrateInput.value);

    if (!Number.isFinite(distance) || distance === 0) {
      alert("Jog distance must be non-zero");
      return;
    }
    if (!Number.isFinite(feedrate) || feedrate <= 0) {
      alert("Feedrate must be positive");
      return;
    }

    try {
      await callApi("/api/jog", {
        method: "POST",
        body: JSON.stringify({ axis, distance, feedrate }),
      });
      await refreshStatus();
    } catch (err) {
      alert(err.message);
    }
  });
});

setInterval(refreshStatus, 1000);
refreshStatus();
