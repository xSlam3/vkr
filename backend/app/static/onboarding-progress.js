(() => {
  const stateNode = document.querySelector("[data-auto-complete-state]");
  const sentinel = document.querySelector("[data-read-sentinel]");
  if (!stateNode || !sentinel) {
    return;
  }

  if (stateNode.dataset.dayCompleted === "true") {
    return;
  }

  const completeUrl = stateNode.dataset.completeUrl;
  if (!completeUrl) {
    return;
  }

  const dayStatusBadge = document.querySelector("[data-day-status-badge]");
  const completedAtLabel = document.querySelector("[data-completed-at-label]");
  const progressBar = document.querySelector("[data-progress-bar]");
  const progressPercentLabel = document.querySelector("[data-progress-percent-label]");
  const progressSummary = document.querySelector("[data-progress-summary]");
  const dayCard = document.querySelector("[data-progress-total]");

  let isSubmitting = false;
  let isDone = false;

  const updateProgress = (completedAt) => {
    if (dayStatusBadge) {
      dayStatusBadge.textContent = "Завершено";
      dayStatusBadge.classList.add("done");
    }

    stateNode.dataset.dayCompleted = "true";
    stateNode.textContent = "День отмечен как завершенный.";

    if (completedAtLabel) {
      completedAtLabel.textContent = `Завершено: ${completedAt}`;
    } else if (stateNode.parentElement && completedAt) {
      const label = document.createElement("p");
      label.className = "helper";
      label.setAttribute("data-completed-at-label", "");
      label.textContent = `Завершено: ${completedAt}`;
      stateNode.insertAdjacentElement("afterend", label);
    }

    if (!dayCard || !progressBar || !progressPercentLabel || !progressSummary) {
      return;
    }

    const total = Number(dayCard.dataset.progressTotal || "0");
    const currentCompleted = Number(dayCard.dataset.progressCompleted || "0");
    const nextCompleted = Math.min(currentCompleted + 1, total);
    const percent = total > 0 ? Math.round((nextCompleted / total) * 100) : 0;

    dayCard.dataset.progressCompleted = String(nextCompleted);
    progressBar.style.width = `${percent}%`;
    progressPercentLabel.textContent = `${percent}%`;
    progressSummary.textContent = `Пройдено ${nextCompleted} из ${total} дней.`;

    if (nextCompleted === total && total > 0) {
      progressPercentLabel.classList.add("done");
    }
  };

  const completeDay = async () => {
    if (isSubmitting || isDone) {
      return;
    }

    isSubmitting = true;
    stateNode.textContent = "Отмечаем день как завершенный...";

    try {
      const response = await fetch(completeUrl, {
        method: "POST",
        headers: {
          "X-Requested-With": "fetch",
        },
        credentials: "same-origin",
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "Не удалось сохранить прогресс.");
      }

      isDone = true;
      updateProgress(payload.completed_at || "");
      observer.disconnect();
    } catch (error) {
      stateNode.textContent = error instanceof Error ? error.message : "Не удалось сохранить прогресс.";
      isSubmitting = false;
    }
  };

  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries.some((entry) => entry.isIntersecting);
      if (visible) {
        completeDay();
      }
    },
    {
      threshold: 1,
    },
  );

  observer.observe(sentinel);
})();
