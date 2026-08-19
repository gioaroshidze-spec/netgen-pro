const STORAGE_KEY = 'vnms_ui_errors';
const MAX_ENTRIES = 100;

function safePath(value) {
  try {
    return new URL(value, window.location.origin).pathname;
  } catch {
    return '/unavailable';
  }
}

export function recordDiagnostic(entry) {
  try {
    const existing = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    const safeEntry = {
      time: new Date().toISOString(),
      type: String(entry.type || 'frontend-error').slice(0, 80),
      error: String(entry.error || 'Frontend error').slice(0, 1000),
    };
    if (entry.stack) safeEntry.stack = String(entry.stack).slice(0, 8000);
    if (entry.method) safeEntry.method = String(entry.method).slice(0, 16);
    if (entry.path) safeEntry.path = safePath(entry.path);
    if (Number.isInteger(entry.status)) safeEntry.status = entry.status;
    existing.push(safeEntry);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(existing.slice(-MAX_ENTRIES)));
  } catch (error) {
    console.warn('Unable to store bounded VNMS browser diagnostics.', error);
  }
}

export function installGlobalDiagnostics() {
  window.addEventListener('error', (event) => {
    recordDiagnostic({
      type: 'window.error',
      error: event.message || 'Unhandled browser error',
      stack: event.error?.stack,
      path: event.filename,
    });
  });
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason;
    recordDiagnostic({
      type: 'unhandledrejection',
      error: reason instanceof Error ? reason.message : 'Unhandled promise rejection',
      stack: reason instanceof Error ? reason.stack : undefined,
    });
  });
}
