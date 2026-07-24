import { api, escapeHtml, statusClass, statusLabel } from "./api.js";

const state = { data: { tickets: [], queues: [] }, selected: null, filter: "all" };
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function notify(message, isError = false) {
  const el = $("#globalAlert"); el.textContent = message; el.classList.toggle("error", isError); el.hidden = false;
  clearTimeout(notify.timer); notify.timer = setTimeout(() => { el.hidden = true; }, 3500);
}

async function loadWorkspace() {
  try {
    await api("/api/v1/auth/demo-role", { method: "POST", body: JSON.stringify({ role: "agent" }) });
    state.data = await api("/api/v1/agent/workspace");
    renderStats(); renderCases();
    if (state.selected?.id) selectCase(state.selected.type, state.selected.id);
  } catch (error) { notify(`工作台加载失败：${error.message}`, true); }
}

function renderStats() {
  const openTickets = state.data.tickets.filter((item) => !["resolved", "closed", "cancelled"].includes(item.status)).length;
  const asyncQueues = state.data.queues.filter((item) => item.status === "async_ticket").length;
  $("#agentStats").innerHTML = [[openTickets, "待处理工单"], [asyncQueues, "异步人工请求"], [state.data.tickets.length, "全部记录"]].map(([value, label]) => `<div class="agent-stat"><b>${value}</b><small>${label}</small></div>`).join("");
}

function allCases() {
  const tickets = state.data.tickets.map((item) => ({ type: "ticket", ...item }));
  const queues = state.data.queues.map((item) => ({ type: "queue", ...item, title: "人工服务请求", description: item.summary }));
  return [...tickets, ...queues].filter((item) => state.filter === "all" || item.type === state.filter);
}

function renderCases() {
  const cases = allCases();
  $("#agentCases").innerHTML = cases.length ? cases.map((item) => `<button class="case-card ${state.selected?.id === item.id ? "active" : ""}" data-case-type="${item.type}" data-case-id="${escapeHtml(item.id)}">
    <span class="case-card-head"><b>${escapeHtml(item.title)}</b><span class="status-chip ${statusClass(item.status)}">${escapeHtml(statusLabel(item.status))}</span></span>
    <p>${escapeHtml(item.description || item.summary || "暂无摘要")}</p><small>${escapeHtml(item.id)} · ${escapeHtml(item.priority || "standard")}</small>
  </button>`).join("") : `<div class="empty-state"><b>当前没有服务记录</b><p>用户提交人工请求或工单后会显示在这里。</p></div>`;
  $("#agentCases").onclick = (event) => { const card = event.target.closest("[data-case-id]"); if (card) selectCase(card.dataset.caseType, card.dataset.caseId); };
}

function ticketDetail(ticket) {
  const transitions = {
    submitted: ["processing", "cancelled"],
    processing: ["waiting_user", "waiting_external", "resolved_pending"],
    waiting_user: ["processing", "cancelled"],
    waiting_external: ["processing", "resolved_pending"],
    resolved_pending: ["closed", "reopened"],
    closed: ["reopened"], reopened: ["processing"], cancelled: [],
  };
  const history = ticket.history || [];
  return `<div class="detail-header"><p class="eyebrow blue">TICKET · MOCK</p><h2>${escapeHtml(ticket.title)}</h2><div class="detail-meta"><span class="status-chip ${statusClass(ticket.status)}">${escapeHtml(statusLabel(ticket.status))}</span><span>${escapeHtml(ticket.id)}</span><span>${escapeHtml(ticket.category)}</span><span>优先级 ${escapeHtml(ticket.priority)}</span></div></div>
    <section class="detail-section"><h3>用户问题与交接摘要</h3><p>${escapeHtml(ticket.description)}</p></section>
    <section class="detail-section"><h3>状态时间线</h3><div class="timeline">${history.map((item) => `<div class="timeline-item"><div><b>${escapeHtml(statusLabel(item.to_status))}</b>${escapeHtml(item.reason || "系统记录")} · ${escapeHtml(new Date(item.created_at).toLocaleString("zh-CN"))}</div></div>`).join("") || "<p>暂无状态记录</p>"}</div></section>
    <section class="detail-section"><h3>回复与内部备注</h3><div class="timeline">${(ticket.comments || []).map((item) => `<div class="timeline-item"><div><b>${item.visibility === "internal" ? "内部备注" : "公开回复"}</b>${escapeHtml(item.content)}</div></div>`).join("") || "<p>暂无补充内容</p>"}</div></section>
    <section class="detail-section"><h3>处理操作</h3><form class="agent-form" id="agentCommentForm"><textarea id="agentComment" placeholder="输入公开回复或内部备注，不要记录密码、验证码等敏感信息"></textarea><div class="form-row"><select id="commentVisibility"><option value="public">公开回复</option><option value="internal">内部备注</option></select><button class="outline-btn" type="submit">添加记录</button><select id="targetStatus"><option value="">选择目标状态</option>${(transitions[ticket.status] || []).map((status) => `<option value="${status}">${statusLabel(status)}</option>`).join("")}</select><button class="primary-btn" type="button" id="transitionBtn">更新状态</button></div></form></section>`;
}

function queueDetail(queue) {
  return `<div class="detail-header"><p class="eyebrow blue">HUMAN REQUEST · MOCK</p><h2>人工服务请求</h2><div class="detail-meta"><span class="status-chip ${statusClass(queue.status)}">${escapeHtml(statusLabel(queue.status))}</span><span>${escapeHtml(queue.id)}</span><span>${escapeHtml(queue.reason)}</span></div></div>
  <section class="detail-section"><h3>交接摘要</h3><p>${escapeHtml(queue.summary || "用户未提供摘要")}</p></section>
  <section class="detail-section"><h3>承接方式</h3><p>${escapeHtml(queue.service_message)}\n关联工单：${escapeHtml(queue.ticket_id || "无")}</p></section>`;
}

async function selectCase(type, id) {
  const item = type === "ticket" ? state.data.tickets.find((entry) => entry.id === id) : state.data.queues.find((entry) => entry.id === id);
  if (!item) return;
  state.selected = { type, id };
  renderCases();
  const detail = $("#agentDetail");
  detail.innerHTML = type === "ticket" ? ticketDetail(item) : queueDetail(item);
  if (type !== "ticket") return;
  $("#agentCommentForm").addEventListener("submit", async (event) => {
    event.preventDefault(); const content = $("#agentComment").value.trim(); if (!content) return;
    try { await api(`/api/v1/support/tickets/${encodeURIComponent(id)}/comments`, { method: "POST", body: JSON.stringify({ content, visibility: $("#commentVisibility").value }) }); notify("记录已添加"); await loadWorkspace(); } catch (error) { notify(error.message, true); }
  });
  $("#transitionBtn").addEventListener("click", async () => {
    const target = $("#targetStatus").value; if (!target) return notify("请先选择目标状态", true);
    try { await api(`/api/v1/support/tickets/${encodeURIComponent(id)}/transitions`, { method: "POST", body: JSON.stringify({ target, reason: "客服工作台操作" }) }); notify("状态已更新"); await loadWorkspace(); } catch (error) { notify(error.message, true); }
  });
}

$$('[data-agent-filter]').forEach((button) => button.addEventListener("click", () => { state.filter = button.dataset.agentFilter; $$('[data-agent-filter]').forEach((item) => item.classList.toggle("active", item === button)); renderCases(); }));
$("#agentRefresh").addEventListener("click", loadWorkspace);
loadWorkspace();
