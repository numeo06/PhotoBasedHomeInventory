// Upload, preview, scan and editable item rows (owner: Person A).
//
// Security: user-typed and detector-provided names are only ever written with
// input.value, textContent or setAttribute, never innerHTML.
// Privacy: the photo preview is a local object URL; the photo itself is only
// sent to POST /scan, which keeps it in memory and never stores it.

(function () {
  "use strict";

  const body = document.body;
  const MAX_BYTES = Number(body.dataset.maxBytes);
  const MAX_DIMENSION = Number(body.dataset.maxDimension);
  const UPLOAD_FIELD = body.dataset.uploadField || "photo";
  const ALLOWED_TYPES = ["image/jpeg", "image/png"];

  const $ = (id) => document.getElementById(id);
  const photoInput = $("photo-input");
  const dropzone = $("dropzone");
  const preview = $("preview");
  const previewEmpty = $("preview-empty");
  const previewImg = $("preview-img");
  const previewName = $("preview-name");
  const clearPhotoBtn = $("clear-photo");
  const scanBtn = $("scan-btn");
  const scanBtnLabel = $("scan-btn-label");
  const statusCard = $("status");
  const statusIconUse = $("status-icon-use");
  const statusTitle = $("status-title");
  const statusText = $("status-text");
  const statusRetry = $("status-retry");
  const statusChoose = $("status-choose");
  const statusClose = $("status-close");
  const itemList = $("item-list");
  const itemEmpty = $("item-empty");
  const rowTemplate = $("item-row-template");
  const addForm = $("add-item-form");
  const addInput = $("add-item-input");

  let currentFile = null;
  let previewUrl = null;
  let scanning = false;

  // ---------- Status card ----------

  const STATUS_ICONS = {
    scanning: "#i-spark",
    success: "#i-check",
    notice: "#i-info",
    error: "#i-alert",
  };

  function showStatus(kind, title, text, options = {}) {
    statusCard.className = "status-card is-" + kind;
    statusIconUse.setAttribute("href", STATUS_ICONS[kind]);
    statusTitle.textContent = title;
    statusText.textContent = text;
    statusRetry.hidden = !options.retry;
    statusChoose.hidden = !options.choose;
    statusClose.hidden = kind === "scanning";
    statusCard.hidden = false;
  }

  function clearStatus() {
    statusCard.hidden = true;
  }

  function showInvalid(title, text) {
    showStatus("error", title, text, { choose: true });
  }

  // ---------- Photo selection and preview ----------

  function formatMB(bytes) {
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  function resetPhoto() {
    currentFile = null;
    photoInput.value = "";
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      previewUrl = null;
    }
    previewImg.removeAttribute("src");
    preview.hidden = true;
    previewEmpty.hidden = false;
    updateScanButton();
  }

  // Quick checks in the browser for fast feedback. The server repeats every
  // check (and actually decodes the image), so these are only a convenience.
  function clientSideProblem(file) {
    if (!ALLOWED_TYPES.includes(file.type)) {
      return ["Invalid File Type", "Please upload a JPEG or PNG image."];
    }
    if (file.size > MAX_BYTES) {
      return ["File Too Large",
        "Your file is " + formatMB(file.size) + ". The limit is " + formatMB(MAX_BYTES) + ". Please choose a smaller image."];
    }
    return null;
  }

  function selectFile(file) {
    if (!file) return;
    clearStatus();
    const problem = clientSideProblem(file);
    if (problem) {
      resetPhoto();
      showInvalid(problem[0], problem[1]);
      return;
    }

    resetPhoto();
    currentFile = file;
    previewUrl = URL.createObjectURL(file);
    previewImg.src = previewUrl;
    previewName.textContent = "Photo ready! " + file.name;
    preview.hidden = false;
    previewEmpty.hidden = true;
    updateScanButton();
  }

  previewImg.addEventListener("load", () => {
    const { naturalWidth: w, naturalHeight: h } = previewImg;
    if (w > MAX_DIMENSION || h > MAX_DIMENSION) {
      resetPhoto();
      showInvalid("Image Too Large",
        "The image is " + w + " × " + h + " pixels. The maximum is " + MAX_DIMENSION + " × " + MAX_DIMENSION + ".");
    }
  });

  previewImg.addEventListener("error", () => {
    if (!currentFile) return;
    resetPhoto();
    showInvalid("Invalid File Type", "This file could not be read as an image. Please choose a JPEG or PNG photo.");
  });

  photoInput.addEventListener("change", () => selectFile(photoInput.files[0]));

  clearPhotoBtn.addEventListener("click", () => {
    resetPhoto();
    clearStatus();
    photoInput.focus();
  });

  // Drag and drop onto the dropzone.
  ["dragenter", "dragover"].forEach((type) =>
    dropzone.addEventListener(type, (event) => {
      event.preventDefault();
      dropzone.classList.add("is-dragover");
    })
  );
  ["dragleave", "drop"].forEach((type) =>
    dropzone.addEventListener(type, () => dropzone.classList.remove("is-dragover"))
  );
  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    const files = event.dataTransfer && event.dataTransfer.files;
    if (files && files.length) selectFile(files[0]);
  });
  // Stop the browser from opening a photo dropped anywhere else on the page.
  window.addEventListener("dragover", (event) => event.preventDefault());
  window.addEventListener("drop", (event) => event.preventDefault());

  // ---------- Scanning ----------

  function updateScanButton() {
    scanBtn.disabled = scanning || !currentFile;
    scanBtnLabel.textContent = scanning ? "Scanning…" : "Scan Items";
  }

  function handleScanResult(data) {
    const status = data && data.status;
    const items = (data && Array.isArray(data.items)) ? data.items : [];

    if (status === "ok") {
      const added = mergeSuggestions(items);
      showStatus("success", "Scan Complete!",
        "Found " + items.length + " suggestion" + (items.length === 1 ? "" : "s") +
        (added < items.length ? " (" + (items.length - added) + " already in your list)" : "") +
        ". These are suggestions: rename, remove or add items below.");
    } else if (status === "no_detections") {
      mergeSuggestions([]);
      showStatus("notice", "Nothing Recognised",
        "The detector didn't find any of its known items in this photo. Add items by hand below, or try another photo.",
        { retry: true, choose: true });
    } else if (status === "model_unavailable") {
      showStatus("error", "Model Unavailable",
        "The local model files are missing. Run scripts/setup_model.py, then try again. You can still add items by hand.",
        { retry: true });
    } else if (status === "invalid_file") {
      const titles = {
        missing_file: "No File Selected",
        file_too_large: "File Too Large",
        dimensions_too_large: "Image Too Large",
      };
      showInvalid(titles[data.reason] || "Invalid File Type",
        data.message || "Please upload a JPEG or PNG image.");
    } else {
      showStatus("error", "Scan Failed",
        "Something went wrong while scanning. Retry, or enter items manually below.",
        { retry: true });
    }
  }

  async function scanPhoto() {
    if (scanning) return;
    if (!currentFile) {
      showInvalid("No File Selected", "Please choose a photo to continue.");
      return;
    }

    scanning = true;
    updateScanButton();
    showStatus("scanning", "Scanning…",
      "Looking for items in your photo. The first scan loads the model and takes longer.");

    const form = new FormData();
    form.append(UPLOAD_FIELD, currentFile, currentFile.name);

    let data = null;
    try {
      const response = await fetch("/scan", { method: "POST", body: form });
      try {
        data = await response.json();
      } catch (_) {
        data = { status: "scan_error", items: [] };
      }
    } catch (_) {
      data = null; // network failure: server stopped or unreachable
    } finally {
      scanning = false;
      updateScanButton();
    }

    if (data === null) {
      showStatus("error", "Can't Reach the App",
        "The scan request didn't reach the server. Check that Flask is still running, then retry. You can still add items by hand.",
        { retry: true });
      return;
    }
    handleScanResult(data);
  }

  scanBtn.addEventListener("click", scanPhoto);
  statusRetry.addEventListener("click", scanPhoto);
  statusChoose.addEventListener("click", () => photoInput.click());
  statusClose.addEventListener("click", clearStatus);

  // ---------- Editable item rows ----------

  const normalize = (text) => text.trim().toLocaleLowerCase();

  function rows() {
    return Array.from(itemList.querySelectorAll(".item-row"));
  }

  function findRow(name) {
    const target = normalize(name);
    return rows().find((row) => normalize(row.querySelector(".item-name").value) === target);
  }

  function updateEmpty() {
    itemEmpty.hidden = itemList.children.length > 0;
  }

  function flash(row) {
    row.classList.remove("is-new");
    void row.offsetWidth; // restart the animation
    row.classList.add("is-new");
  }

  function addRow(name, score, source) {
    const row = rowTemplate.content.firstElementChild.cloneNode(true);
    const input = row.querySelector(".item-name");
    const scoreEl = row.querySelector(".item-score");
    const removeBtn = row.querySelector(".item-remove");

    row.dataset.source = source; // "detector" until the user edits it, then "manual"
    input.value = name;
    removeBtn.setAttribute("aria-label", "Remove " + name);
    if (typeof score === "number") {
      scoreEl.textContent = "score " + score;
      scoreEl.title = "Detector score (not a probability)";
    } else {
      scoreEl.textContent = source === "manual" ? "added" : "";
    }

    input.addEventListener("input", () => {
      row.dataset.source = "manual"; // an edited suggestion is now the user's item
      if (typeof score === "number") {
        // The detector's score belonged to the original label, not the new name.
        scoreEl.textContent = "edited";
        scoreEl.title = "Renamed from the suggestion “" + name + "” (score " + score + ")";
      }
      removeBtn.setAttribute("aria-label", "Remove " + (input.value.trim() || "item"));
    });
    input.addEventListener("blur", () => {
      input.value = input.value.trim();
      if (!input.value) removeRow(row, false); // an emptied row is a removed row
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        input.blur();
      }
    });
    removeBtn.addEventListener("click", () => removeRow(row, true));

    itemList.appendChild(row);
    flash(row);
    updateEmpty();
    return row;
  }

  function removeRow(row, moveFocus) {
    const next = row.nextElementSibling || row.previousElementSibling;
    row.remove();
    updateEmpty();
    if (moveFocus) {
      (next ? next.querySelector(".item-remove") : addInput).focus();
    }
  }

  // A new scan replaces earlier untouched suggestions but keeps anything the
  // user typed or edited. Returns how many new rows were added.
  function mergeSuggestions(items) {
    rows().filter((row) => row.dataset.source === "detector").forEach((row) => row.remove());
    let added = 0;
    items.forEach((item) => {
      if (!item || typeof item.name !== "string" || !item.name.trim()) return;
      if (findRow(item.name)) return;
      addRow(item.name.trim(), item.score, "detector");
      added += 1;
    });
    updateEmpty();
    return added;
  }

  addForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const name = addInput.value.trim();
    if (!name) {
      addInput.focus();
      return;
    }
    const existing = findRow(name);
    if (existing) {
      flash(existing);
      existing.querySelector(".item-name").focus();
    } else {
      addRow(name, null, "manual");
    }
    addInput.value = "";
    addInput.focus();
  });

  updateEmpty();
  updateScanButton();
})();
