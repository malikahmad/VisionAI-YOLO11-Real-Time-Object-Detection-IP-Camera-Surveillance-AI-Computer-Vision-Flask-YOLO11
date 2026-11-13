const videoInput = document.getElementById("videoInput");
const dropzone = document.getElementById("dropzone");
const selectedFile = document.getElementById("selectedFile");
const fileName = document.getElementById("fileName");
const fileSize = document.getElementById("fileSize");
const removeFile = document.getElementById("removeFile");
const startButton = document.getElementById("startButton");
const sourcePreview = document.getElementById("sourcePreview");
const previewEmpty = document.getElementById("previewEmpty");
const confidence = document.getElementById("confidence");
const confidenceValue = document.getElementById("confidenceValue");
const toast = document.getElementById("toast");

let currentFile = null;
let currentPreviewUrl = null;
let pollTimer = null;

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 3500);
}
function formatBytes(bytes) {
  return bytes >= 1024 * 1024 ? (bytes / (1024 * 1024)).toFixed(1) + " MB" : (bytes / 1024).toFixed(0) + " KB";
}
function setFile(file) {
  if (!file) return;
  const allowed = /\.(mp4|avi|mov|mkv|webm)$/i.test(file.name);
  if (!allowed) return showToast("Unsupported video format.");
  if (file.size > 700 * 1024 * 1024) return showToast("Maximum file size is 700 MB.");
  currentFile = file;
  fileName.textContent = file.name;
  fileSize.textContent = formatBytes(file.size);
  selectedFile.classList.remove("hidden");
  startButton.disabled = false;
  if (currentPreviewUrl) URL.revokeObjectURL(currentPreviewUrl);
  currentPreviewUrl = URL.createObjectURL(file);
  sourcePreview.src = currentPreviewUrl;
  sourcePreview.classList.remove("hidden");
  previewEmpty.classList.add("hidden");
  sourcePreview.onloadedmetadata = () => {
    const d = sourcePreview.duration;
    const mins = Math.floor(d / 60);
    const secs = Math.floor(d % 60);
    document.getElementById("videoMeta").textContent =
      `${sourcePreview.videoWidth}×${sourcePreview.videoHeight} · ${mins}:${String(secs).padStart(2,"0")}`;
  };
}
videoInput.addEventListener("change", e => setFile(e.target.files[0]));
["dragenter","dragover"].forEach(evt => dropzone.addEventListener(evt, e => {
  e.preventDefault(); dropzone.classList.add("dragover");
}));
["dragleave","drop"].forEach(evt => dropzone.addEventListener(evt, e => {
  e.preventDefault(); dropzone.classList.remove("dragover");
}));
dropzone.addEventListener("drop", e => setFile(e.dataTransfer.files[0]));
removeFile.addEventListener("click", () => {
  currentFile = null;
  videoInput.value = "";
  selectedFile.classList.add("hidden");
  startButton.disabled = true;
  sourcePreview.pause();
  sourcePreview.removeAttribute("src");
  sourcePreview.load();
  sourcePreview.classList.add("hidden");
  previewEmpty.classList.remove("hidden");
  document.getElementById("videoMeta").textContent = "No video selected";
});
confidence.addEventListener("input", () => confidenceValue.textContent = Number(confidence.value).toFixed(2));

function setStatus(status) {
  const badge = document.getElementById("statusBadge");
  badge.textContent = status.toUpperCase();
  badge.className = "status-badge " + status;
}
function renderJob(job) {
  document.getElementById("progressBar").style.width = `${job.progress || 0}%`;
  document.getElementById("progressPercent").textContent = `${job.progress || 0}%`;
  document.getElementById("progressMessage").textContent = job.message || "Working...";
  document.getElementById("frameProgress").textContent =
    `${(job.processed_frames || 0).toLocaleString()} / ${(job.total_frames || 0).toLocaleString()} frames`;
  document.getElementById("detectionCount").textContent = (job.total_detections || 0).toLocaleString();
  document.getElementById("framesCount").textContent = (job.processed_frames || 0).toLocaleString();
  if (job.device) document.getElementById("deviceLabel").textContent = `Device: ${job.device}`;
  setStatus(job.status === "loading" || job.status === "queued" ? "processing" : job.status);

  if (job.status === "completed") {
    clearInterval(pollTimer);
    document.getElementById("resultsEmpty").classList.add("hidden");
    document.getElementById("resultsContent").classList.remove("hidden");
    document.getElementById("videoDownload").href = job.video_url;
    document.getElementById("csvDownload").href = job.csv_url;
    const classList = document.getElementById("classList");
    classList.innerHTML = "";
    Object.entries(job.class_counts || {}).sort((a,b) => b[1]-a[1]).forEach(([name,count]) => {
      const chip = document.createElement("span");
      chip.className = "class-chip";
      chip.textContent = name + " ";
      const b = document.createElement("b");
      b.textContent = count.toLocaleString();
      chip.appendChild(b);
      classList.appendChild(chip);
    });
    startButton.disabled = !currentFile;
    startButton.innerHTML = '<i class="bi bi-arrow-repeat"></i> Run another video <i class="bi bi-arrow-right"></i>';
    showToast("Detection completed. Your results are ready.");
  } else if (job.status === "failed") {
    clearInterval(pollTimer);
    startButton.disabled = !currentFile;
    showToast("Detection failed: " + job.message);
  }
}
async function pollStatus(jobId) {
  try {
    const response = await fetch(`/api/status/${jobId}`);
    const job = await response.json();
    if (!response.ok) throw new Error(job.error || "Could not read job status.");
    renderJob(job);
  } catch (err) {
    clearInterval(pollTimer);
    showToast(err.message);
  }
}
startButton.addEventListener("click", async () => {
  if (!currentFile) return;
  if (pollTimer) clearInterval(pollTimer);
  const form = new FormData();
  form.append("video", currentFile);
  form.append("model", document.getElementById("model").value);
  form.append("confidence", confidence.value);
  form.append("image_size", document.getElementById("imageSize").value);
  form.append("tracking", document.getElementById("tracking").checked ? "true" : "false");

  startButton.disabled = true;
  startButton.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Uploading...';
  setStatus("processing");
  document.getElementById("progressBar").style.width = "0%";
  document.getElementById("progressPercent").textContent = "0%";
  document.getElementById("progressMessage").textContent = "Uploading video...";
  document.getElementById("resultsContent").classList.add("hidden");
  document.getElementById("resultsEmpty").classList.remove("hidden");

  try {
    const response = await fetch("/api/upload", { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Upload failed.");
    showToast("Video uploaded. YOLO11 processing has started.");
    startButton.innerHTML = '<i class="bi bi-hourglass-split"></i> Processing...';
    await pollStatus(data.job_id);
    pollTimer = setInterval(() => pollStatus(data.job_id), 1200);
  } catch (err) {
    startButton.disabled = !currentFile;
    startButton.innerHTML = '<i class="bi bi-stars"></i> Start detection <i class="bi bi-arrow-right"></i>';
    showToast(err.message);
  }
});


// Live IP camera controls (RTSP -> YOLO11 -> MJPEG browser preview).
const startCameraButton = document.getElementById("startCameraButton");
const stopCameraButton = document.getElementById("stopCameraButton");
const cameraFeed = document.getElementById("cameraFeed");
const cameraFeedEmpty = document.getElementById("cameraFeedEmpty");
let cameraPollTimer = null;

function renderCameraStatus(data) {
  document.getElementById("cameraState").textContent = (data.status || "stopped").toUpperCase();
  document.getElementById("cameraMessage").textContent = data.message || "";
  document.getElementById("cameraDetectionCount").textContent = (data.total_detections || 0).toLocaleString();
  const dot = document.getElementById("cameraStateDot");
  dot.classList.toggle("active", data.status === "running" || data.status === "reconnecting");
  const classes = document.getElementById("cameraClassList");
  classes.innerHTML = "";
  Object.entries(data.class_counts || {}).sort((a,b) => b[1]-a[1]).slice(0,12).forEach(([name,count]) => {
    const chip = document.createElement("span");
    chip.className = "class-chip";
    chip.textContent = `${name} ${count.toLocaleString()}`;
    classes.appendChild(chip);
  });
  const active = ["starting", "running", "reconnecting"].includes(data.status);
  startCameraButton.disabled = active;
  stopCameraButton.disabled = !active;
  if (data.status === "failed" || data.status === "stopped") {
    if (cameraPollTimer) clearInterval(cameraPollTimer);
    cameraPollTimer = null;
    cameraFeed.classList.add("hidden");
    cameraFeedEmpty.classList.remove("hidden");
  }
}

async function pollCameraStatus() {
  try {
    const response = await fetch("/api/camera/status", {cache: "no-store"});
    const data = await response.json();
    renderCameraStatus(data);
  } catch (error) {
    showToast("Could not read camera status: " + error.message);
  }
}

startCameraButton.addEventListener("click", async () => {
  const cameraUrl = document.getElementById("cameraUrl").value.trim();
  if (!cameraUrl) return showToast("Enter your camera RTSP URL first.");
  startCameraButton.disabled = true;
  startCameraButton.textContent = "Connecting...";
  try {
    const response = await fetch("/api/camera/start", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        camera_url: cameraUrl,
        model: document.getElementById("model").value,
        confidence: Number(confidence.value),
        image_size: Number(document.getElementById("imageSize").value),
        tracking: document.getElementById("tracking").checked
      })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not start camera.");
    cameraFeed.src = data.feed_url + "?t=" + Date.now();
    cameraFeed.classList.remove("hidden");
    cameraFeedEmpty.classList.add("hidden");
    if (cameraPollTimer) clearInterval(cameraPollTimer);
    await pollCameraStatus();
    cameraPollTimer = setInterval(pollCameraStatus, 1200);
    showToast("Camera stream started. Waiting for the first annotated frame.");
  } catch (error) {
    showToast(error.message);
    startCameraButton.disabled = false;
  } finally {
    startCameraButton.innerHTML = '<i class="bi bi-camera-video"></i> Start live detection';
  }
});

stopCameraButton.addEventListener("click", async () => {
  stopCameraButton.disabled = true;
  try {
    await fetch("/api/camera/stop", {method: "POST"});
    if (cameraPollTimer) clearInterval(cameraPollTimer);
    cameraPollTimer = null;
    cameraFeed.removeAttribute("src");
    cameraFeed.classList.add("hidden");
    cameraFeedEmpty.classList.remove("hidden");
    await pollCameraStatus();
    showToast("Camera stream stopped.");
  } catch (error) {
    showToast("Could not stop camera: " + error.message);
  }
});
