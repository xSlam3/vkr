(() => {
  const modalRegistry = new Map();

  const openModal = (modal) => {
    if (!modal) return;
    modal.hidden = false;
    document.body.classList.add("modal-open");
    modal.dispatchEvent(new CustomEvent("modal:open"));
    const focusTarget = modal.querySelector("[data-modal-focus]") || modal.querySelector("[data-rich-editor]") || modal.querySelector("input, select, textarea, button");
    if (focusTarget) {
      window.setTimeout(() => focusTarget.focus(), 0);
    }
  };

  const closeModal = (modal) => {
    if (!modal) return;
    modal.hidden = true;
    if (![...document.querySelectorAll(".modal-shell")].some((node) => !node.hidden)) {
      document.body.classList.remove("modal-open");
    }
  };

  document.querySelectorAll(".modal-shell[id]").forEach((modal) => {
    modalRegistry.set(modal.id, modal);
    modal.querySelectorAll("[data-modal-close]").forEach((button) => {
      button.addEventListener("click", () => closeModal(modal));
    });
  });

  document.querySelectorAll("[data-modal-open]").forEach((button) => {
    const modalId = button.dataset.modalOpen;
    const modal = modalRegistry.get(modalId);
    if (!modal) return;
    button.addEventListener("click", () => openModal(modal));
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    [...modalRegistry.values()].forEach((modal) => {
      if (!modal.hidden) closeModal(modal);
    });
  });

  const initializeEditorModal = (modal) => {
    const form = modal.querySelector("[data-rich-editor-form]");
    const editor = modal.querySelector("[data-rich-editor]");
    const output = modal.querySelector("[data-editor-output]");
    const fileInput = modal.querySelector("[data-editor-file-input]");
    const statusNode = modal.querySelector("[data-editor-status]");
    const dropzone = modal.querySelector("[data-editor-dropzone]");
    const primaryMediaUrl = modal.querySelector("[data-primary-media-url]");
    const primaryMediaType = modal.querySelector("[data-primary-media-type]");
    const initialContentNode = modal.querySelector("[data-editor-initial-content]");
    if (!form || !editor || !output || !fileInput || !statusNode || !dropzone || !primaryMediaUrl || !primaryMediaType) {
      return;
    }

    let pendingInsertType = "image";
    let savedRange = null;

    const setStatus = (message, tone = "default") => {
      statusNode.textContent = message;
      statusNode.dataset.tone = tone;
    };

    const resetFormState = () => {
      form.reset();
      editor.innerHTML = initialContentNode?.value || "<p></p>";
      output.value = initialContentNode?.value || "";
      primaryMediaUrl.value = form.dataset.initialMediaUrl || "";
      primaryMediaType.value = form.dataset.initialMediaType || "";

      if (form.dataset.initialDayNumber) {
        const daySelect = form.querySelector("[name='day_number']");
        if (daySelect) daySelect.value = form.dataset.initialDayNumber;
      }

      if (form.dataset.initialTitle) {
        const titleInput = form.querySelector("[name='title']");
        if (titleInput) titleInput.value = form.dataset.initialTitle;
      }

      if (form.dataset.initialCategoryId) {
        const categorySelect = form.querySelector("[name='category_id']");
        if (categorySelect) categorySelect.value = form.dataset.initialCategoryId;
      }

      savedRange = null;
      setStatus("Редактор готов.");
    };

    modal.addEventListener("modal:open", resetFormState);

    const saveSelection = () => {
      const selection = window.getSelection();
      if (!selection || selection.rangeCount === 0) return;
      savedRange = selection.getRangeAt(0).cloneRange();
    };

    const restoreSelection = () => {
      if (!savedRange) return;
      const selection = window.getSelection();
      if (!selection) return;
      selection.removeAllRanges();
      selection.addRange(savedRange);
    };

    const ensureEditorHasContent = () => {
      if (!editor.innerHTML.trim()) editor.innerHTML = "<p></p>";
    };

    const syncOutput = () => {
      const html = editor.innerHTML.trim();
      output.value = html;
      return html;
    };

    const isEditorEmpty = () => {
      const html = syncOutput().replace(/<p><br><\/p>/g, "").replace(/&nbsp;/g, " ").trim();
      const plain = editor.textContent.replace(/\s+/g, " ").trim();
      const hasMedia = /<(img|video|iframe|figure|source)\b/i.test(html);
      return !plain && !hasMedia;
    };

    const setPrimaryMedia = (value, kind) => {
      if (!primaryMediaUrl.value) {
        primaryMediaUrl.value = value;
        primaryMediaType.value = kind === "video" ? "video" : "photo";
      }
    };

    const insertHtml = (html) => {
      editor.focus();
      restoreSelection();
      document.execCommand("insertHTML", false, html);
      ensureEditorHasContent();
      syncOutput();
      saveSelection();
    };

    const escapeHtml = (value) =>
      value.replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[char]));

    const insertMedia = (url, kind, altText = "") => {
      const safeUrl = escapeHtml(url);
      const safeAlt = escapeHtml(altText || "");
      if (kind === "video") {
        insertHtml(`<figure><video controls preload="metadata" src="${safeUrl}"></video></figure><p><br></p>`);
      } else {
        insertHtml(`<figure><img src="${safeUrl}" alt="${safeAlt}" /></figure><p><br></p>`);
      }
    };

    const uploadToStorage = async (file) => {
      const scope = form.dataset.uploadScope || "onboarding";
      const presignResponse = await fetch("/media/presign-upload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: file.name,
          content_type: file.type,
          scope,
        }),
      });

      if (!presignResponse.ok) {
        const payload = await presignResponse.json().catch(() => ({}));
        throw new Error(payload.detail || "Не удалось подготовить загрузку.");
      }

      const presign = await presignResponse.json();
      const uploadData = new FormData();
      Object.entries(presign.fields).forEach(([key, value]) => uploadData.append(key, value));
      uploadData.append("file", file);

      const uploadResponse = await fetch(presign.url, { method: "POST", body: uploadData });
      if (!uploadResponse.ok) throw new Error("Не удалось загрузить файл.");

      return {
        key: presign.key,
        url: `/media/file?key=${encodeURIComponent(presign.key)}`,
      };
    };

    const readAsDataUrl = (file) =>
      new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(new Error("Не удалось прочитать файл."));
        reader.readAsDataURL(file);
      });

    const processFile = async (file, sourceLabel = "файл") => {
      const kind = file.type.startsWith("video/") ? "video" : "image";
      setStatus(`Загружаю ${sourceLabel}...`);

      try {
        const uploaded = await uploadToStorage(file);
        insertMedia(uploaded.url, kind, file.name);
        setPrimaryMedia(uploaded.key, kind);
        setStatus("Вложение добавлено.", "success");
        return;
      } catch (error) {
        if (kind === "image") {
          try {
            const dataUrl = await readAsDataUrl(file);
            insertMedia(dataUrl, "image", file.name);
            setPrimaryMedia(dataUrl, "image");
            setStatus("Изображение добавлено локально.", "warning");
            return;
          } catch (readError) {
            setStatus(readError.message, "danger");
            return;
          }
        }
        setStatus(error.message || "Не удалось добавить вложение.", "danger");
      }
    };

    const processFiles = async (files, sourceLabel) => {
      const supported = Array.from(files).filter((file) => file.type.startsWith("image/") || file.type.startsWith("video/"));
      if (supported.length === 0) {
        setStatus("Поддерживаются только изображения и видео.", "danger");
        return;
      }
      for (const file of supported) await processFile(file, sourceLabel);
    };

    editor.addEventListener("mouseup", saveSelection);
    editor.addEventListener("keyup", () => {
      saveSelection();
      syncOutput();
    });
    editor.addEventListener("focus", () => {
      ensureEditorHasContent();
      saveSelection();
    });

    editor.addEventListener("paste", async (event) => {
      const files = Array.from(event.clipboardData?.files || []);
      if (files.length === 0) return;
      event.preventDefault();
      await processFiles(files, "вложение из буфера");
    });

    editor.addEventListener("dragover", (event) => {
      event.preventDefault();
      dropzone.classList.add("is-dragover");
    });

    editor.addEventListener("dragleave", () => {
      dropzone.classList.remove("is-dragover");
    });

    editor.addEventListener("drop", async (event) => {
      event.preventDefault();
      dropzone.classList.remove("is-dragover");
      await processFiles(event.dataTransfer?.files || [], "перетаскиваемый файл");
    });

    modal.querySelectorAll("[data-editor-command]").forEach((button) => {
      button.addEventListener("click", () => {
        const command = button.dataset.editorCommand;
        let value = button.dataset.editorValue || null;
        if (command === "formatBlock" && value) value = `<${value}>`;
        editor.focus();
        restoreSelection();
        document.execCommand(command, false, value);
        syncOutput();
        saveSelection();
      });
    });

    modal.querySelectorAll("[data-editor-action]").forEach((button) => {
      button.addEventListener("click", () => {
        const action = button.dataset.editorAction;
        editor.focus();
        restoreSelection();

        if (action === "link") {
          const url = window.prompt("Введите ссылку");
          if (url) {
            document.execCommand("createLink", false, url);
            syncOutput();
            saveSelection();
          }
          return;
        }

        if (action === "image" || action === "video") {
          pendingInsertType = action;
          fileInput.accept = action === "video" ? "video/*" : "image/*";
          fileInput.click();
          return;
        }

        if (action === "clear") {
          editor.innerHTML = "<p></p>";
          primaryMediaUrl.value = "";
          primaryMediaType.value = "";
          syncOutput();
          setStatus("Содержимое очищено.");
        }
      });
    });

    fileInput.addEventListener("change", async () => {
      const files = Array.from(fileInput.files || []);
      if (pendingInsertType === "image") {
        await processFiles(files, "выбранный файл");
      } else {
        await processFiles(files.filter((file) => file.type.startsWith("video/")), "выбранный файл");
      }
      fileInput.value = "";
    });

    form.addEventListener("submit", (event) => {
      syncOutput();
      if (isEditorEmpty()) {
        event.preventDefault();
        setStatus("Добавьте содержимое перед сохранением.", "danger");
        editor.focus();
        return;
      }
      setStatus("Сохраняю...");
    });

    ensureEditorHasContent();
    syncOutput();
  };

  document.querySelectorAll(".modal-shell").forEach(initializeEditorModal);
})();
