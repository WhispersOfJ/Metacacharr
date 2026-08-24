/* Arm/confirm guard for real, one-shot side effects. */
import { svg } from "./core.js";

export function armButton(btn, idleLabel, armedLabel, onConfirm) {
  let armed = false;
  let disarmTimer = null;
  const disarm = () => { armed = false; btn.textContent = idleLabel; btn.classList.remove("armed"); };
  btn.textContent = idleLabel;
  btn.addEventListener("click", async () => {
    if (!armed) {
      armed = true;
      btn.textContent = armedLabel;
      btn.classList.add("armed");
      disarmTimer = setTimeout(disarm, 5000);
      return;
    }
    clearTimeout(disarmTimer);
    disarm();
    await onConfirm();
  });
}

export function armIconButton(btn, iconName, onConfirm, stopHandler) {
  let armed = false;
  let disarmTimer = null;
  btn.innerHTML = svg(iconName);
  const disarm = () => {
    armed = false;
    btn.classList.remove("armed");
    btn.title = btn.dataset.idleTitle || btn.title;
    btn.setAttribute("aria-label", btn.dataset.idleLabel || btn.getAttribute("aria-label"));
  };
  btn.dataset.idleTitle = btn.title;
  btn.dataset.idleLabel = btn.getAttribute("aria-label") || btn.title;
  btn.addEventListener("click", async (e) => {
    if (stopHandler) stopHandler(e);
    if (!armed) {
      armed = true;
      btn.classList.add("armed");
      btn.title = "Click again to confirm";
      btn.setAttribute("aria-label", "Click again to confirm");
      disarmTimer = setTimeout(disarm, 5000);
      return;
    }
    clearTimeout(disarmTimer);
    disarm();
    await onConfirm();
  });
}
