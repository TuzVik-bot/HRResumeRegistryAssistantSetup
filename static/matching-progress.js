(function () {
  const panel = document.querySelector("[data-matching-progress]");
  const form = document.querySelector("[data-matching-form]");
  if (!panel) return;

  const title = panel.querySelector("[data-matching-progress-title]");
  const message = panel.querySelector("[data-matching-progress-message]");

  function render(progress) {
    if (!progress || progress.state === "idle") {
      panel.hidden = true;
      return;
    }
    panel.hidden = false;
    title.textContent = progress.state === "failed"
      ? "Сопоставление завершилось с ошибкой"
      : progress.state === "completed"
        ? "Сопоставление завершено"
        : "Сопоставление выполняется";
    message.textContent = progress.message || "";
  }

  async function poll() {
    try {
      const response = await fetch("/matching-progress", { cache: "no-store" });
      if (!response.ok) return;
      const progress = await response.json();
      render(progress);
      if (progress.state === "running") {
        window.setTimeout(poll, 1500);
      }
    } catch (error) {
      panel.hidden = true;
    }
  }

  if (form) {
    form.addEventListener("submit", function () {
      render({ state: "running", message: "Запущено сопоставление. Дождитесь обновления страницы." });
    });
  }

  poll();
})();
