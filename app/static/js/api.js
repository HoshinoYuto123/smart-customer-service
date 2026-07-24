const JSON_HEADERS = { "Content-Type": "application/json" };

export function newId(prefix = "id") {
  if (globalThis.crypto?.randomUUID) return `${prefix}-${crypto.randomUUID()}`;
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers: { ...JSON_HEADERS, ...(options.headers || {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.success === false) {
    const message = payload.error?.message || payload.detail || `请求失败（${response.status}）`;
    const error = new Error(message);
    error.code = payload.error?.code || `HTTP_${response.status}`;
    error.traceId = payload.trace_id || response.headers.get("x-trace-id") || "";
    throw error;
  }
  return payload.data === undefined ? payload : payload.data;
}

export async function ensureAnonymous() {
  return api("/api/v1/auth/anonymous", { method: "POST", body: "{}" });
}

export function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function statusLabel(status = "") {
  const labels = {
    succeeded: "已完成", failed: "失败", unknown: "待确认", ineligible: "需人工核验",
    pending: "待处理", submitted: "已提交", processing: "处理中", waiting_user: "待用户补充",
    waiting_external: "待外部结果", resolved_pending: "待用户确认", closed: "已关闭", reopened: "已重开", cancelled: "已取消",
    async_ticket: "异步工单承接", queued: "排队中", connected: "已接入",
  };
  return labels[status] || status || "待确认";
}

export function statusClass(status = "") {
  if (["succeeded", "resolved_pending", "closed", "connected"].includes(status)) return "good";
  if (["failed", "cancelled"].includes(status)) return "bad";
  return "";
}
