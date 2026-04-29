(() => {
  const forms = document.querySelectorAll("[data-upload-form]");

  forms.forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();

      const progress = form.querySelector("[data-upload-progress]");
      const bar = form.querySelector("[data-upload-bar]");
      const percent = form.querySelector("[data-upload-percent]");
      const status = form.querySelector("[data-upload-status]");
      const button = form.querySelector("button[type='submit']");
      const formData = new FormData(form);
      const request = new XMLHttpRequest();

      if (progress) progress.hidden = false;
      if (button) {
        button.dataset.originalText = button.textContent;
        button.disabled = true;
        button.textContent = "Загружаем...";
      }
      setProgress(0, "Подготовка загрузки");

      request.upload.addEventListener("progress", (uploadEvent) => {
        if (!uploadEvent.lengthComputable) {
          setProgress(12, "Загрузка файла");
          return;
        }
        const rawValue = Math.round((uploadEvent.loaded / uploadEvent.total) * 100);
        if (rawValue >= 100) {
          setProgress(100, "Файл передан. Обрабатываем данные...");
          return;
        }
        setProgress(rawValue, "Загрузка файла");
      });

      request.addEventListener("load", () => {
        if (request.status >= 200 && request.status < 400) {
          setProgress(100, "Загрузка завершена");
          window.location.href = request.responseURL || form.action;
          return;
        }
        setProgress(0, getErrorMessage(request) || "Ошибка загрузки");
        if (button) {
          button.disabled = false;
          button.textContent = button.dataset.originalText || "Повторить";
        }
      });

      request.addEventListener("error", () => {
        setProgress(0, "Сеть недоступна");
        if (button) button.disabled = false;
      });

      request.open(form.method || "POST", form.action);
      request.send(formData);

      function setProgress(value, text) {
        if (bar) bar.style.width = `${value}%`;
        if (percent) percent.textContent = `${value}%`;
        if (status) status.textContent = text;
      }

      function getErrorMessage(xhr) {
        try {
          const payload = JSON.parse(xhr.responseText || "{}");
          return payload.detail || "";
        } catch {
          return xhr.responseText || "";
        }
      }
    });
  });
})();
