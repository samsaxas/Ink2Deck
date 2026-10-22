(function () {
  "use strict";

  var MAX_BYTES = 10 * 1024 * 1024;
  var ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];
  var ALLOWED_EXT = /\.(jpe?g|png|webp)$/i;

  var $ = function (id) {
    return document.getElementById(id);
  };

  var el = {
    whoami: $("whoami"),
    logout: $("logout-btn"),
    pageError: $("page-error"),
    dropzone: $("dropzone"),
    chooseBtn: $("choose-btn"),
    fileInput: $("file-input"),
    editor: $("editor"),
    preview: $("preview"),
    fileMeta: $("file-meta"),
    extractBtn: $("extract-btn"),
    changeBtn: $("change-btn"),
    badge: $("engine-badge"),
    empty: $("empty-text"),
    skeleton: $("skeleton"),
    text: $("text-area"),
    count: $("count"),
    warnings: $("warnings"),
    pptxBtn: $("pptx-btn"),
    pdfBtn: $("pdf-btn"),
    copyBtn: $("copy-btn"),
  };

  var state = { file: null, previewUrl: null, extracting: false, exporting: false };

  /* ----------------------------------------------------------- helpers */

  function showPageError(message) {
    el.pageError.textContent = message;
    el.pageError.hidden = false;
  }

  function clearPageError() {
    el.pageError.hidden = true;
    el.pageError.textContent = "";
  }

  function formatSize(bytes) {
    if (bytes >= 1024 * 1024) {
      return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    }
    return Math.max(1, Math.round(bytes / 1024)) + " KB";
  }

  function handleAuthError(error) {
    if (error && error.status === 401) {
      window.location.href = "/login";
      return true;
    }
    return false;
  }

  function hasText() {
    return el.text.value.trim().length > 0;
  }

  function refreshButtons() {
    var ready = hasText() && !state.extracting && !state.exporting;
    el.pptxBtn.disabled = !ready;
    el.pdfBtn.disabled = !ready;
    el.copyBtn.disabled = !hasText();
    el.extractBtn.disabled = !state.file || state.extracting || state.exporting;
    el.changeBtn.disabled = state.extracting || state.exporting;
  }

  function resetResult() {
    el.text.value = "";
    el.text.hidden = true;
    el.count.hidden = true;
    el.badge.hidden = true;
    el.skeleton.hidden = true;
    el.empty.hidden = false;
    el.warnings.hidden = true;
    el.warnings.replaceChildren();
    refreshButtons();
  }

  function downloadBlob(blob, filename) {
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 2000);
  }

  /* ------------------------------------------------------ choose a file */

  function looksLikeAllowedImage(file) {
    return ALLOWED_TYPES.indexOf(file.type) !== -1 || (!file.type && ALLOWED_EXT.test(file.name));
  }

  function setFile(file) {
    clearPageError();

    if (!looksLikeAllowedImage(file)) {
      showPageError("That file is not a JPG, PNG or WebP image.");
      return;
    }
    if (file.size > MAX_BYTES) {
      showPageError("That image is " + formatSize(file.size) + ". The limit is 10 MB.");
      return;
    }
    if (file.size === 0) {
      showPageError("That file is empty.");
      return;
    }

    if (state.previewUrl) {
      URL.revokeObjectURL(state.previewUrl);
    }
    state.file = file;
    state.previewUrl = URL.createObjectURL(file);

    el.preview.src = state.previewUrl;
    el.fileMeta.textContent = (file.name || "Pasted image") + " \u00b7 " + formatSize(file.size);

    resetResult();
    el.dropzone.hidden = true;
    el.editor.hidden = false;
    refreshButtons();
    el.extractBtn.focus();
  }

  function chooseDifferent() {
    state.file = null;
    if (state.previewUrl) {
      URL.revokeObjectURL(state.previewUrl);
      state.previewUrl = null;
    }
    el.preview.removeAttribute("src");
    el.fileInput.value = "";
    resetResult();
    clearPageError();
    el.editor.hidden = true;
    el.dropzone.hidden = false;
    el.chooseBtn.focus();
  }

  el.chooseBtn.addEventListener("click", function () {
    el.fileInput.click();
  });

  el.fileInput.addEventListener("change", function () {
    if (el.fileInput.files && el.fileInput.files[0]) {
      setFile(el.fileInput.files[0]);
    }
  });

  el.changeBtn.addEventListener("click", chooseDifferent);

  /* Drag and drop. Stop the browser from opening a dropped file by accident. */
  window.addEventListener("dragover", function (event) {
    event.preventDefault();
  });
  window.addEventListener("drop", function (event) {
    event.preventDefault();
  });

  el.dropzone.addEventListener("dragenter", function () {
    el.dropzone.classList.add("is-over");
  });
  el.dropzone.addEventListener("dragover", function () {
    el.dropzone.classList.add("is-over");
  });
  el.dropzone.addEventListener("dragleave", function (event) {
    if (!el.dropzone.contains(event.relatedTarget)) {
      el.dropzone.classList.remove("is-over");
    }
  });
  el.dropzone.addEventListener("drop", function (event) {
    el.dropzone.classList.remove("is-over");
    var files = event.dataTransfer && event.dataTransfer.files;
    if (files && files[0]) {
      setFile(files[0]);
    }
  });

  /* Paste an image from the clipboard. */
  document.addEventListener("paste", function (event) {
    var items = (event.clipboardData && event.clipboardData.items) || [];
    for (var i = 0; i < items.length; i++) {
      if (items[i].kind === "file" && items[i].type.indexOf("image/") === 0) {
        var file = items[i].getAsFile();
        if (file && !state.extracting && !state.exporting) {
          setFile(file);
        }
        return;
      }
    }
  });

  /* -------------------------------------------------------- extract text */

  function showWarnings(list) {
    el.warnings.replaceChildren();
    if (!list || !list.length) {
      el.warnings.hidden = true;
      return;
    }
    list.forEach(function (message) {
      var box = document.createElement("div");
      box.className = "alert alert-warn";
      box.textContent = message;
      el.warnings.appendChild(box);
    });
    el.warnings.hidden = false;
  }

  function updateCount() {
    var words = el.text.value.trim() ? el.text.value.trim().split(/\s+/).length : 0;
    el.count.textContent = words + (words === 1 ? " word" : " words") + " \u00b7 " + el.text.value.length + " characters";
  }

  async function extract() {
    if (!state.file || state.extracting) {
      return;
    }
    clearPageError();
    state.extracting = true;
    Ink.setBusy(el.extractBtn, true);
    el.extractBtn.querySelector(".label").textContent = "Reading\u2026";
    el.empty.hidden = true;
    el.text.hidden = true;
    el.count.hidden = true;
    el.badge.hidden = true;
    el.skeleton.hidden = false;
    refreshButtons();

    try {
      var form = new FormData();
      form.append("file", state.file, state.file.name || "image.png");
      var response = await Ink.request("/api/extract", { method: "POST", body: form });
      var data = await response.json();

      el.text.value = data.text;
      el.text.hidden = false;
      el.count.hidden = false;
      updateCount();
      el.badge.textContent = "Read with Gemini";
      el.badge.hidden = false;
      showWarnings(data.warnings);
      el.extractBtn.querySelector(".label").textContent = "Extract again";
      Ink.toast("Text extracted. Check it, then download.");
    } catch (error) {
      if (handleAuthError(error)) {
        return;
      }
      el.empty.hidden = false;
      showPageError(error.message);
      el.extractBtn.querySelector(".label").textContent = "Extract text";
    } finally {
      state.extracting = false;
      Ink.setBusy(el.extractBtn, false);
      el.skeleton.hidden = true;
      refreshButtons();
    }
  }

  el.extractBtn.addEventListener("click", extract);

  el.text.addEventListener("input", function () {
    updateCount();
    refreshButtons();
  });

  /* -------------------------------------------------------------- export */

  async function runExport(button, work) {
    if (state.exporting || !hasText()) {
      return;
    }
    clearPageError();
    state.exporting = true;
    Ink.setBusy(button, true);
    refreshButtons();
    try {
      await work();
    } catch (error) {
      if (!handleAuthError(error)) {
        showPageError(error.message);
        Ink.toast(error.message, true);
      }
    } finally {
      state.exporting = false;
      Ink.setBusy(button, false);
      refreshButtons();
    }
  }

  el.pdfBtn.addEventListener("click", function () {
    runExport(el.pdfBtn, async function () {
      var response = await Ink.request("/api/export/pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: el.text.value }),
      });
      downloadBlob(await response.blob(), "extracted_content.pdf");
      Ink.toast("PDF downloaded.");
    });
  });

  el.pptxBtn.addEventListener("click", function () {
    runExport(el.pptxBtn, async function () {
      var form = new FormData();
      form.append("file", state.file, state.file.name || "image.png");
      form.append("text", el.text.value);
      var response = await Ink.request("/api/export/pptx", { method: "POST", body: form });
      downloadBlob(await response.blob(), "whiteboard_presentation.pptx");
      Ink.toast("PowerPoint downloaded.");
    });
  });

  el.copyBtn.addEventListener("click", async function () {
    try {
      await navigator.clipboard.writeText(el.text.value);
    } catch (ignore) {
      el.text.select();
      document.execCommand("copy");
    }
    Ink.toast("Text copied.");
  });

  /* ------------------------------------------------------------- session */

  el.logout.addEventListener("click", function () {
    Ink.logout();
  });

  (async function init() {
    var user = await Ink.currentUser();
    if (!user) {
      window.location.href = "/login";
      return;
    }
    el.whoami.textContent = user.name || user.username;
  })();
})();
