// Confirm dialogs, a "working" banner, copy and print buttons. Every page works without this file.
document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;
  const question = form.dataset.confirm;
  if (question && !window.confirm(question)) {
    event.preventDefault();
    return;
  }
  const banner = document.getElementById("working");
  if (banner) banner.hidden = false;
  window.setTimeout(() => {
    document.querySelectorAll("button").forEach((button) => {
      button.disabled = true;
    });
  }, 0);
});

window.addEventListener("pageshow", (event) => {
  if (!event.persisted) return;
  document.querySelectorAll("button").forEach((button) => {
    button.disabled = false;
  });
  const banner = document.getElementById("working");
  if (banner) banner.hidden = true;
});

// Copy and print buttons are hidden in the markup and shown only when the browser can do it.
if (navigator.clipboard && window.isSecureContext) {
  document.querySelectorAll("[data-copy]").forEach((button) => {
    const label = button.textContent;
    let timer = 0;
    const flash = (text) => {
      window.clearTimeout(timer);
      button.textContent = text;
      timer = window.setTimeout(() => {
        button.textContent = label;
      }, 1500);
    };
    button.hidden = false;
    button.addEventListener("click", () => {
      navigator.clipboard
        .writeText(button.dataset.copy || "")
        .then(() => flash("Copied!"))
        .catch(() => flash("Copy failed"));
    });
  });
}

document.querySelectorAll("[data-print]").forEach((button) => {
  button.hidden = false;
  button.addEventListener("click", () => window.print());
});
