const TOAST_DURATION_MS = 4000;
const TOAST_FADE_MS = 300;

export function showToast(message: string, variant: "error" | "info" = "error"): void {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  const colorClasses = variant === "error" ? "bg-red-600" : "bg-slate-800";
  toast.className = `max-w-sm rounded-lg px-4 py-3 text-sm font-medium text-white shadow-lg ${colorClasses}`;
  toast.textContent = message;
  container.appendChild(toast);

  window.setTimeout(() => {
    toast.classList.add("opacity-0", "transition-opacity", "duration-300");
    window.setTimeout(() => toast.remove(), TOAST_FADE_MS);
  }, TOAST_DURATION_MS);
}
