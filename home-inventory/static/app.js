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

  // Day 4 state: which saved inventory is open, and whether it has unsaved edits.
  let currentId = null; // null = a new, unsaved inventory
  let dirty = false;
  let loadingRows = false; // true while rows are filled from a saved inventory
  const markDirty = () => {
    if (!loadingRows) {
      dirty = true;
      updateMode();
    }
  };

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
    const count = itemList.children.length;
    itemEmpty.hidden = count > 0;
    $("items-count").textContent = count ? "(" + count + ")" : "";
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
      scoreEl.textContent = { manual: "added", saved: "saved" }[source] || "";
    }

    input.addEventListener("input", () => {
      markDirty();
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
    if (!loadingRows) flash(row);
    updateEmpty();
    markDirty();
    return row;
  }

  function removeRow(row, moveFocus) {
    if (!row.isConnected) return;
    const next = row.nextElementSibling || row.previousElementSibling;
    row.remove();
    updateEmpty();
    markDirty();
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

  // ======================================================================
  // Day 4: save, reopen and search saved inventories
  // ======================================================================

  const readJson = (id, fallback) => {
    try {
      return JSON.parse($(id).textContent);
    } catch (_) {
      return fallback;
    }
  };
  const LIMITS = readJson("limits-data", { label: 200, item: 100, items: 200, query: 100, preview: 3 });
  let saved = readJson("saved-data", []); // [{id, label, item_count, preview}], newest first

  const locationInput = $("location");
  const locationPanel = $("location-panel");
  const modeChip = $("mode-chip");
  const modeText = $("mode-text");
  const modeDirty = $("mode-dirty");
  const newLocationBtn = $("new-location-btn");
  const saveBtn = $("save-btn");
  const saveBtnLabel = $("save-btn-label");
  const cardGrid = $("card-grid");
  const cardTemplate = $("card-template");
  const archiveEmpty = $("archive-empty");
  const savedView = $("saved-view");
  const searchForm = $("search-form");
  const searchInput = $("search-input");
  const searchClear = $("search-clear");
  const searchResults = $("search-results");
  const resultList = $("result-list");
  const resultTemplate = $("result-template");
  const resultsSummary = $("results-summary");
  const resultsEmpty = $("results-empty");
  const resultsEmptyText = $("results-empty-text");

  let saving = false;

  const padId = (id) => "#" + String(id).padStart(3, "0");
  const plural = (n, word, many) => n + " " + (n === 1 ? word : (many || word + "s"));

  // ---------- Mode: new inventory vs editing a saved one ----------

  function updateMode() {
    const editing = currentId !== null;
    modeChip.classList.toggle("is-editing", editing);
    locationPanel.classList.toggle("is-editing", editing);
    modeChip.classList.toggle("is-dirty", dirty);
    modeText.textContent = editing ? "Editing Inventory " + padId(currentId) : "New inventory";
    modeDirty.textContent = editing ? "· unsaved changes" : "· not saved yet";
    modeDirty.hidden = !dirty;
    newLocationBtn.hidden = !editing && !dirty;
    saveBtnLabel.textContent = saving ? "Saving…" : (editing ? "Save Changes" : "Save Items");
    saveBtn.disabled = saving;
    cardGrid.querySelectorAll(".folder-card").forEach((card) => {
      const current = editing && Number(card.dataset.id) === currentId;
      card.classList.toggle("is-current", current);
      if (current) card.setAttribute("aria-current", "true");
      else card.removeAttribute("aria-current");
    });
  }

  function confirmDiscard() {
    return !dirty || window.confirm("You have unsaved changes. Discard them?");
  }

  // Replace the editor's label and rows with a saved inventory (or clear them).
  function loadEditor(location) {
    loadingRows = true;
    itemList.replaceChildren();
    locationInput.value = location ? location.label : "";
    if (location) location.items.forEach((name) => addRow(name, null, "saved"));
    loadingRows = false;
    currentId = location ? location.id : null;
    dirty = false;
    updateEmpty();
    updateMode();
  }

  locationInput.addEventListener("input", markDirty);

  newLocationBtn.addEventListener("click", () => {
    if (!confirmDiscard()) return;
    loadEditor(null);
    resetPhoto();
    clearStatus();
    locationInput.focus();
  });

  window.addEventListener("beforeunload", (event) => {
    if (dirty) event.preventDefault(); // browser asks "Leave site?"
  });

  // ---------- Saving ----------

  function currentItems() {
    return rows().map((row) => row.querySelector(".item-name").value.trim()).filter(Boolean);
  }

  async function saveInventory() {
    if (saving) return;
    const label = locationInput.value.trim();
    const items = currentItems();

    if (!label) {
      showStatus("error", "Location Needed", "Give this inventory a location name before saving, e.g. Garage / Workbench / Top drawer.");
      locationInput.focus();
      return;
    }
    if (items.length > LIMITS.items) {
      showStatus("error", "Too Many Items",
        "A location can hold at most " + LIMITS.items + " items. This one has " + items.length + ".");
      return;
    }

    const wasNew = currentId === null;
    saving = true;
    updateMode();
    let response = null;
    let data = null;
    try {
      response = await fetch(wasNew ? "/locations" : "/locations/" + currentId, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label, items }),
      });
      data = await response.json().catch(() => null);
    } catch (_) {
      response = null;
    } finally {
      saving = false;
      updateMode();
    }

    if (response === null) {
      showStatus("error", "Can't Reach the App",
        "The save request didn't reach the server. Check that Flask is still running, then save again. Your list is still here.");
      return;
    }
    if (!response.ok || !data || typeof data.id !== "number") {
      if (response.status === 404 && !wasNew) {
        // The inventory was removed from the database; keep the user's list as a new one.
        removeCard(currentId);
        currentId = null;
        updateMode();
        showStatus("error", "Inventory Not Found",
          "That saved inventory no longer exists. Your list is still here; click Save Items to save it as a new inventory.");
        return;
      }
      showStatus("error", "Couldn't Save", (data && data.error) || "The server rejected the save. Please try again.");
      return;
    }

    loadEditor(data); // show exactly what was stored (duplicates merged, blanks dropped)
    upsertCard(data);
    showStatus("success", wasNew ? "Saved as Inventory " + padId(data.id) : "Inventory " + padId(data.id) + " Updated",
      plural(data.items.length, "item") + " saved under “" + data.label + "”. Find them anytime with the search below.");
    if (searchInput.value.trim()) runSearch(); // keep visible search results up to date
  }

  saveBtn.addEventListener("click", saveInventory);

  // ---------- Opening a saved inventory ----------

  async function openInventory(id) {
    if (id === currentId && !dirty) {
      locationPanel.scrollIntoView({ block: "start" });
      return;
    }
    if (!confirmDiscard()) return;
    let data = null;
    let status = 0;
    try {
      const response = await fetch("/locations/" + id);
      status = response.status;
      data = await response.json().catch(() => null);
    } catch (_) {
      status = 0;
    }
    if (status === 404) {
      removeCard(id);
      showStatus("error", "Inventory Not Found", "Inventory " + padId(id) + " no longer exists.");
      return;
    }
    if (!data || typeof data.id !== "number") {
      showStatus("error", "Can't Open Inventory", "Couldn't load inventory " + padId(id) + ". Check that Flask is running and try again.");
      return;
    }

    loadEditor(data);
    resetPhoto(); // photos are never stored, so a reopened inventory starts without one
    showStatus("notice", "Editing Inventory " + padId(data.id),
      "Rename, remove or add items, then click Save Changes. To add suggestions, choose a new photo and scan it.");
    locationPanel.scrollIntoView({ block: "start" });
    locationInput.focus({ preventScroll: true });
  }

  // ---------- Saved location cards ----------

  function cardFromLocation(location) {
    return {
      id: location.id,
      label: location.label,
      item_count: location.items.length,
      preview: location.items.slice(0, LIMITS.preview),
    };
  }

  function upsertCard(location) {
    saved = saved.filter((card) => card.id !== location.id);
    saved.unshift(cardFromLocation(location)); // most recently updated first, like the server
    renderCards(location.id);
  }

  function removeCard(id) {
    saved = saved.filter((card) => card.id !== id);
    renderCards();
  }

  function renderCards(highlightId) {
    cardGrid.replaceChildren();
    saved.forEach((card) => {
      const li = cardTemplate.content.firstElementChild.cloneNode(true);
      const button = li.querySelector(".folder-card");
      button.dataset.id = card.id;
      li.querySelector(".card-label").textContent = card.label;
      li.querySelector(".card-meta").textContent = "Inventory " + padId(card.id) + " · " + plural(card.item_count, "item");
      const more = card.item_count - card.preview.length;
      li.querySelector(".card-preview").textContent = card.preview.length
        ? card.preview.join(", ") + (more > 0 ? " +" + more + " more" : "")
        : "No items yet";
      button.setAttribute("aria-label",
        "Open Inventory " + padId(card.id) + ", " + card.label + ", " + plural(card.item_count, "item"));
      button.title = card.label;
      button.addEventListener("click", () => openInventory(card.id));
      if (card.id === highlightId) button.classList.add("is-new");
      cardGrid.appendChild(li);
    });

    const count = saved.length;
    archiveEmpty.hidden = count > 0;
    $("archive-count").textContent = count ? plural(count, "location") : "";
    $("nav-count").textContent = count;
    $("db-count").textContent = "DB: " + plural(count, "saved location");
    updateMode();
  }

  // ---------- Search ----------

  let searchTimer = null;
  let searchToken = 0;

  // Write `text` into `el`, wrapping the first case-insensitive match of `query` in <mark>.
  function highlight(el, text, query) {
    el.replaceChildren();
    const at = text.toLocaleLowerCase().indexOf(query.toLocaleLowerCase());
    if (!query || at < 0) {
      el.textContent = text;
      return;
    }
    const mark = document.createElement("mark");
    mark.textContent = text.slice(at, at + query.length);
    el.append(document.createTextNode(text.slice(0, at)), mark, document.createTextNode(text.slice(at + query.length)));
  }

  function showAllLocations() {
    searchInput.value = "";
    searchToken += 1; // ignore any search still in flight
    searchClear.hidden = true;
    searchResults.hidden = true;
    savedView.hidden = false;
    searchInput.focus();
  }

  async function runSearch() {
    const query = searchInput.value.trim();
    searchClear.hidden = !searchInput.value;
    if (!query) {
      searchResults.hidden = true;
      savedView.hidden = false;
      return;
    }

    const token = ++searchToken;
    let data = null;
    try {
      const response = await fetch("/search?q=" + encodeURIComponent(query));
      data = await response.json().catch(() => null);
      if (!response.ok) data = { error: (data && data.error) || "Search failed." };
    } catch (_) {
      data = { error: "Couldn't reach the app. Check that Flask is still running." };
    }
    if (token !== searchToken) return; // a newer search has started

    savedView.hidden = true;
    searchResults.hidden = false;
    resultList.replaceChildren();
    const results = (data && Array.isArray(data.results)) ? data.results : [];

    if (data && data.error) {
      resultsSummary.parentElement.hidden = true;
      resultsEmptyText.textContent = data.error;
      resultsEmpty.hidden = false;
      return;
    }
    resultsSummary.textContent = plural(results.length, "match", "matches") + " for “" + query + "”";
    resultsSummary.parentElement.hidden = results.length === 0; // the empty state says it instead
    resultsEmpty.hidden = results.length > 0;
    resultsEmptyText.textContent = "No saved items match “" + query + "”.";

    results.forEach((result) => {
      const li = resultTemplate.content.firstElementChild.cloneNode(true);
      highlight(li.querySelector(".result-item"), result.item, query);
      li.querySelector(".result-label").textContent = result.location_label;
      li.querySelector(".result-id").textContent = padId(result.location_id);
      const button = li.querySelector(".result-row");
      button.setAttribute("aria-label",
        result.item + " in " + result.location_label + ", Inventory " + padId(result.location_id) + ". Open.");
      button.addEventListener("click", () => openInventory(result.location_id));
      resultList.appendChild(li);
    });
  }

  searchInput.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(runSearch, 200);
  });
  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && searchInput.value) {
      event.preventDefault();
      showAllLocations();
    }
  });
  searchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    clearTimeout(searchTimer);
    runSearch();
  });
  searchClear.addEventListener("click", showAllLocations);
  $("show-all-btn").addEventListener("click", showAllLocations);
  $("results-show-all").addEventListener("click", showAllLocations);

  updateEmpty();
  updateScanButton();
  renderCards();
  updateMode();
})();
