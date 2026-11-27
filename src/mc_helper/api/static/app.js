// Confirm dialogs and a "working" banner. The page works without this file.
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
