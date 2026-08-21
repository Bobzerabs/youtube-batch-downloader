const urlInput = document.querySelector("#urlInput");
const linkCount = document.querySelector("#linkCount");
const pasteButton = document.querySelector("#pasteButton");
const clearButton = document.querySelector("#clearButton");
const analyzeButton = document.querySelector("#analyzeButton");
const resultsSection = document.querySelector("#resultsSection");
const videoList = document.querySelector("#videoList");
const selectedCount = document.querySelector("#selectedCount");
const batchFormat = document.querySelector("#batchFormat");
const batchQuality = document.querySelector("#batchQuality");
const downloadButton = document.querySelector("#downloadButton");
const progressSection = document.querySelector("#progressSection");
const overallPercent = document.querySelector("#overallPercent");
const overallBar = document.querySelector("#overallBar");
const jobItems = document.querySelector("#jobItems");
const jobSummary = document.querySelector("#jobSummary");
const archiveBox = document.querySelector("#archiveBox");
const archiveLink = document.querySelector("#archiveLink");
const toast = document.querySelector("#toast");

let inspected = [];
let currentJobId = null;
let pollTimer = null;

function getLinks() {
  return [...new Set(
    urlInput.value
      .split(/\r?\n/)
      .map(v => v.trim())
      .filter(Boolean)
  )];
}

function updateLinkCount() {
  linkCount.textContent = getLinks().length;
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 2800);
}

function secondsToTime(total) {
  total = Number(total || 0);
  if (!total) return "Duração indisponível";
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = Math.floor(total % 60);
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
}

function bytesToSize(bytes) {
  if (!bytes) return "";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let value = Number(bytes);
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i++;
  }
  return `${value.toFixed(i > 1 ? 1 : 0)} ${units[i]}`;
}

function statusText(status) {
  return {
    queued: "Na fila",
    downloading: "Baixando",
    done: "Pronto",
    error: "Erro",
  }[status] || status;
}

function qualityOptions(video) {
  const base = [`<option value="best">Melhor disponível</option>`];
  const preferred = [...new Set(video.qualities || [])].sort((a, b) => b - a);
  for (const q of preferred) {
    base.push(`<option value="${q}">${q}p</option>`);
  }
  return base.join("");
}

function renderInspected() {
  videoList.innerHTML = "";
  const valid = inspected.filter(item => item.ok);

  inspected.forEach((item, index) => {
    const card = document.createElement("article");
    card.className = "video-card";

    if (!item.ok) {
      card.innerHTML = `
        <div class="thumb"></div>
        <div class="video-info">
          <h3>Não foi possível analisar este link</h3>
          <div class="video-meta"><span>${escapeHtml(item.error || "Erro desconhecido")}</span></div>
        </div>
        <button class="remove-item" data-remove="${index}" aria-label="Remover">×</button>
      `;
    } else {
      card.innerHTML = `
        <img class="thumb" src="${escapeAttr(item.thumbnail)}" alt="">
        <div class="video-info">
          <h3 title="${escapeAttr(item.title)}">${escapeHtml(item.title)}</h3>
          <div class="video-meta">
            <span>${escapeHtml(item.channel)}</span>
            <span>•</span>
            <span>${secondsToTime(item.duration)}</span>
            ${item.is_short ? `<span class="tag">SHORT</span>` : ""}
          </div>
        </div>
        <div class="item-controls">
          <select class="format-select" data-index="${index}">
            <option value="mp4">MP4 — Vídeo</option>
            <option value="mp3">MP3 — Áudio</option>
          </select>
          <select class="quality-select" data-index="${index}">
            ${qualityOptions(item)}
          </select>
          <select class="bitrate-select hidden" data-index="${index}">
            <option value="320">320 kbps</option>
            <option value="256">256 kbps</option>
            <option value="192">192 kbps</option>
            <option value="128">128 kbps</option>
          </select>
          <button class="remove-item" data-remove="${index}" aria-label="Remover">×</button>
        </div>
      `;
    }

    videoList.appendChild(card);
  });

  selectedCount.textContent = valid.length;
  downloadButton.disabled = valid.length === 0;

  document.querySelectorAll("[data-remove]").forEach(btn => {
    btn.addEventListener("click", () => {
      inspected.splice(Number(btn.dataset.remove), 1);
      renderInspected();
      if (!inspected.length) resultsSection.classList.add("hidden");
    });
  });

  document.querySelectorAll(".format-select").forEach(select => {
    select.addEventListener("change", () => toggleFormatControls(Number(select.dataset.index), select.value));
  });
}

function toggleFormatControls(index, value) {
  const quality = document.querySelector(`.quality-select[data-index="${index}"]`);
  const bitrate = document.querySelector(`.bitrate-select[data-index="${index}"]`);
  if (!quality || !bitrate) return;

  if (value === "mp3") {
    quality.classList.add("hidden");
    bitrate.classList.remove("hidden");
  } else {
    bitrate.classList.add("hidden");
    quality.classList.remove("hidden");
  }
}

async function analyze() {
  const urls = getLinks();
  if (!urls.length) {
    showToast("Cole pelo menos um link do YouTube.");
    return;
  }

  analyzeButton.disabled = true;
  analyzeButton.querySelector("span").textContent = "Analisando...";

  try {
    const response = await fetch("/api/inspect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ urls }),
    });

    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Falha ao analisar os links.");

    inspected = data.results || [];
    renderInspected();
    resultsSection.classList.remove("hidden");
    resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showToast(error.message || "Erro ao analisar.");
  } finally {
    analyzeButton.disabled = false;
    analyzeButton.querySelector("span").textContent = "Analisar vídeos";
  }
}

function collectDownloadItems() {
  const items = [];
  inspected.forEach((video, index) => {
    if (!video.ok) return;

    const format = document.querySelector(`.format-select[data-index="${index}"]`);
    const quality = document.querySelector(`.quality-select[data-index="${index}"]`);
    const bitrate = document.querySelector(`.bitrate-select[data-index="${index}"]`);

    if (!format) return;
    items.push({
      url: video.url,
      mode: format.value,
      quality: quality?.value || "best",
      audio_bitrate: bitrate?.value || "320",
    });
  });
  return items;
}

async function startDownload() {
  const items = collectDownloadItems();
  if (!items.length) {
    showToast("Nenhum vídeo válido para baixar.");
    return;
  }

  downloadButton.disabled = true;
  archiveBox.classList.add("hidden");

  try {
    const response = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items }),
    });

    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Não foi possível iniciar o lote.");

    currentJobId = data.job_id;
    progressSection.classList.remove("hidden");
    progressSection.scrollIntoView({ behavior: "smooth", block: "start" });
    beginPolling();
  } catch (error) {
    showToast(error.message || "Erro ao iniciar o download.");
    downloadButton.disabled = false;
  }
}

function renderJob(job) {
  const p = Math.max(0, Math.min(100, Number(job.progress || 0)));
  overallPercent.textContent = `${Math.round(p)}%`;
  overallBar.style.width = `${p}%`;

  const done = job.items.filter(i => i.status === "done").length;
  const errors = job.items.filter(i => i.status === "error").length;
  jobSummary.textContent = `${done} concluído(s) • ${errors} erro(s) • ${job.items.length} total`;

  jobItems.innerHTML = "";
  job.items.forEach((item, index) => {
    const original = inspected.filter(v => v.ok)[index];
    const title = original?.title || `Vídeo ${index + 1}`;
    const progress = Number(item.progress || 0);
    const sub = item.error
      ? item.error
      : item.status === "done"
      ? `${bytesToSize(item.size)} • ${item.mode.toUpperCase()}`
      : item.eta
      ? `Tempo restante aproximado: ${item.eta}s`
      : `${item.mode.toUpperCase()} • ${item.quality === "best" ? "melhor qualidade" : item.quality + "p"}`;

    const row = document.createElement("div");
    row.className = "job-item";
    row.innerHTML = `
      <div>
        <div class="job-item-title">${escapeHtml(title)}</div>
        <div class="job-item-sub">${escapeHtml(sub)}
          ${item.status === "done" ? `<a class="file-link" href="/api/job/${job.id}/file/${index}">baixar arquivo</a>` : ""}
        </div>
      </div>
      <div class="small-track"><span style="width:${Math.min(progress,100)}%"></span></div>
      <span class="status-pill ${item.status}">${statusText(item.status)}</span>
    `;
    jobItems.appendChild(row);
  });

  if (job.archive_ready) {
    archiveLink.href = `/api/job/${job.id}/archive`;
    archiveBox.classList.remove("hidden");
  }

  if (job.status === "done" || job.status === "error") {
    window.clearInterval(pollTimer);
    pollTimer = null;
    downloadButton.disabled = false;
    if (job.done_count > 0) showToast("Lote processado.");
  }
}

async function pollJob() {
  if (!currentJobId) return;
  try {
    const response = await fetch(`/api/job/${currentJobId}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Erro ao consultar o lote.");
    renderJob(data);
  } catch (error) {
    window.clearInterval(pollTimer);
    pollTimer = null;
    downloadButton.disabled = false;
    showToast(error.message || "Erro ao acompanhar o processamento.");
  }
}

function beginPolling() {
  window.clearInterval(pollTimer);
  pollJob();
  pollTimer = window.setInterval(pollJob, 1200);
}

function escapeHtml(value = "") {
  const el = document.createElement("div");
  el.textContent = String(value);
  return el.innerHTML;
}

function escapeAttr(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

urlInput.addEventListener("input", updateLinkCount);
analyzeButton.addEventListener("click", analyze);
downloadButton.addEventListener("click", startDownload);

pasteButton.addEventListener("click", async () => {
  try {
    const text = await navigator.clipboard.readText();
    if (!text) return;
    const existing = urlInput.value.trim();
    urlInput.value = existing ? `${existing}\n${text.trim()}` : text.trim();
    updateLinkCount();
  } catch {
    showToast("O navegador não permitiu acessar a área de transferência.");
  }
});

clearButton.addEventListener("click", () => {
  urlInput.value = "";
  inspected = [];
  updateLinkCount();
  resultsSection.classList.add("hidden");
  progressSection.classList.add("hidden");
});

batchFormat.addEventListener("change", () => {
  if (!batchFormat.value) return;
  document.querySelectorAll(".format-select").forEach(select => {
    select.value = batchFormat.value;
    toggleFormatControls(Number(select.dataset.index), select.value);
  });
});

batchQuality.addEventListener("change", () => {
  if (!batchQuality.value) return;
  document.querySelectorAll(".quality-select").forEach(select => {
    const hasOption = [...select.options].some(o => o.value === batchQuality.value);
    select.value = hasOption ? batchQuality.value : "best";
  });
});

updateLinkCount();
