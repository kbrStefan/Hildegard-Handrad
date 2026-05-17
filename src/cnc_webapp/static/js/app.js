const statusOut = document.getElementById("statusOut");
const portInput = document.getElementById("portInput");
const baudrateInput = document.getElementById("baudrateInput");
const gcodeInput = document.getElementById("gcodeInput");
const jogDistanceInput = document.getElementById("jogDistanceInput");
const jogFeedrateInput = document.getElementById("jogFeedrateInput");

async function callApi(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });

  const data = await response.json();
  if (!response.ok || !data.ok) {
    throw new Error(data.error || `Request failed: ${response.status}`);
  }
  return data;
}

async function refreshStatus() {
  try {
    const data = await callApi("/api/status", { method: "GET", headers: {} });
    statusOut.textContent = JSON.stringify(data.status, null, 2);
  } catch (err) {
    statusOut.textContent = `Status unavailable: ${err.message}`;
  }
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
    const data = await response.json();
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

document.getElementById("homeAllBtn").addEventListener("click", async () => {
  try {
    await callApi("/api/home", { method: "POST", body: JSON.stringify({}) });
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
