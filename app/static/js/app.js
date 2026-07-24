import { api, ensureAnonymous, escapeHtml, newId, statusClass, statusLabel } from "./api.js";

const state = {
  home: null,
  selectedObject: null,
  category: "",
  sessionId: localStorage.getItem("support_session_id") || newId("web"),
  sending: false,
};
localStorage.setItem("support_session_id", state.sessionId);

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const dialog = $("#detailDialog");
const dialogContent = $("#dialogContent");
const pageTitles = { home: "服务首页", chat: "智能客服", progress: "服务进度" };
const objectGlyph = { order: "单", course: "课", account: "安" };

function notify(message, isError = false) {
  const el = $("#globalAlert");
  el.textContent = message;
  el.classList.toggle("error", isError);
  el.hidden = false;
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => { el.hidden = true; }, 3600);
}

function setRouteStep(step) {
  $$('[data-route-step]').forEach((el) => {
    const current = Number(el.dataset.routeStep);
    el.classList.toggle("active", current === step);
    el.classList.toggle("done", current < step);
  });
}

function switchView(view) {
  $$('[data-view-panel]').forEach((panel) => panel.classList.toggle("active", panel.dataset.viewPanel === view));
  $$('[data-view]').forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  $("#pageTitle").textContent = pageTitles[view] || "服务中心";
  setRouteStep(view === "home" ? 1 : view === "chat" ? 2 : 4);
  history.replaceState(null, "", `#${view}`);
  if (view === "progress") loadProgress();
  if (view === "chat") setTimeout(() => $("#chatInput").focus(), 60);
}

function renderObjects() {
  const list = $("#objectList");
  const objects = state.home?.context?.objects || [];
  list.innerHTML = objects.map((item) => `
    <button class="object-card ${state.selectedObject?.id === item.id ? "active" : ""}" data-object-id="${escapeHtml(item.id)}">
      <span class="object-icon">${objectGlyph[item.type] || "服"}</span>
      <span><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.status)}</small></span>
      <span class="object-check">✓</span>
    </button>`).join("");
  list.onclick = (event) => {
    const button = event.target.closest("[data-object-id]");
    if (!button) return;
    state.selectedObject = objects.find((item) => item.id === button.dataset.objectId);
    renderObjects();
    renderCapabilities();
    $("#contextHint").textContent = `${state.selectedObject.title} · ${state.selectedObject.subtitle}`;
  };
}

function renderCapabilities() {
  const capabilities = state.home?.capabilities || [];
  const selected = state.selectedObject;
  const relevant = capabilities.filter((item) => !item.object_types.length || selected && item.object_types.includes(selected.type));
  $("#capabilityList").innerHTML = relevant.slice(0, 8).map((item, index) => `
    <button class="capability-card" data-capability="${escapeHtml(item.id)}">
      <span class="capability-index"><span>${String(index + 1).padStart(2, "0")}</span><b>↗</b></span>
      <strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.description)}</small>
    </button>`).join("");
  $("#capabilityList").onclick = (event) => {
    const button = event.target.closest("[data-capability]");
    if (!button) return;
    const capability = capabilities.find((item) => item.id === button.dataset.capability);
    runCapability(capability);
  };
}

function renderCategories() {
  const categories = state.home?.categories || [];
  $("#categoryList").innerHTML = `<button class="${state.category ? "" : "active"}" data-category="">全部</button>` + categories.map((item) => `
    <button class="${state.category === item.id ? "active" : ""}" data-category="${escapeHtml(item.id)}">${escapeHtml(item.name)}</button>`).join("");
  $("#categoryList").onclick = (event) => {
    const button = event.target.closest("[data-category]");
    if (!button) return;
    state.category = button.dataset.category;
    renderCategories();
    searchFaq();
  };
}

function renderFaqs(items) {
  const list = $("#faqList");
  if (!items.length) {
    list.innerHTML = `<div class="empty-state"><b>没有找到直接答案</b><p>换个关键词，或进入智能客服继续描述问题。</p><button class="text-btn" data-go-chat>咨询智能客服 →</button></div>`;
    return;
  }
  list.innerHTML = items.slice(0, 8).map((item) => `
    <button class="faq-row" data-faq-id="${escapeHtml(item.id)}"><span>${escapeHtml(item.question)}</span><small>查看 →</small></button>`).join("");
  list.onclick = (event) => {
    const row = event.target.closest("[data-faq-id]");
    if (row) openFaq(row.dataset.faqId);
  };
}

async function searchFaq() {
  const query = $("#faqQuery").value.trim();
  try {
    const items = await api(`/api/v1/support/faqs?q=${encodeURIComponent(query)}&category=${encodeURIComponent(state.category)}`);
    renderFaqs(items);
  } catch (error) { notify(`${error.message}${error.traceId ? ` · ${error.traceId}` : ""}`, true); }
}

async function openFaq(id) {
  try {
    const item = await api(`/api/v1/support/faqs/${encodeURIComponent(id)}`);
    dialogContent.innerHTML = `<article class="dialog-body">
      <p class="eyebrow blue">FAQ · ${escapeHtml(item.category_id)}</p>
      <h2>${escapeHtml(item.question)}</h2>
      <div class="answer">${escapeHtml(item.answer)}</div>
      <div class="dialog-result"><strong>适用范围</strong><small>${escapeHtml(item.scope)}</small></div>
      <div class="dialog-actions"><button class="primary-btn" data-faq-resolved="true">已解决</button><button class="outline-btn" data-faq-resolved="false">未解决，继续咨询</button></div>
    </article>`;
    dialogContent.onclick = async (event) => {
      const button = event.target.closest("[data-faq-resolved]");
      if (!button) return;
      const resolved = button.dataset.faqResolved === "true";
      await api(`/api/v1/support/faqs/${encodeURIComponent(id)}/feedback`, { method: "POST", body: JSON.stringify({ resolved, session_id: state.sessionId }) });
      dialog.close();
      if (resolved) notify("已记录：这个答案解决了问题");
      else { appendMessage("assistant", `关于“${item.question}”仍未解决，请补充具体情况，我会继续协助。`); switchView("chat"); }
    };
    dialog.showModal();
  } catch (error) { notify(error.message, true); }
}

async function runCapability(capability) {
  if (!capability) return;
  const selected = state.selectedObject;
  if (capability.requires_confirmation && !confirm(`确认执行“${capability.title}”？当前为演示环境，不会修改真实业务数据。`)) return;
  setRouteStep(2);
  try {
    const task = await api("/api/v1/support/self-service", {
      method: "POST",
      headers: { "Idempotency-Key": newId("self") },
      body: JSON.stringify({ capability: capability.id, object_type: selected?.type || "", object_id: selected?.id || "", input: {} }),
    });
    const result = task.result || {};
    dialogContent.innerHTML = `<article class="dialog-body">
      <p class="eyebrow blue">SELF SERVICE · MOCK</p><h2>${escapeHtml(capability.title)}</h2>
      <div class="dialog-result"><strong>${escapeHtml(result.headline || statusLabel(task.status))}</strong><small>${escapeHtml(result.disclaimer || "这是演示结果，不代表真实业务操作成功。")}</small></div>
      <p class="answer">${escapeHtml(result.next_action || task.error_code || "处理记录已生成，可在服务进度中查看。")}</p>
      <div class="dialog-actions"><button class="primary-btn" data-dialog-progress>查看服务进度</button><button class="outline-btn" data-dialog-human>仍未解决，转人工</button></div>
    </article>`;
    dialogContent.onclick = (event) => {
      if (event.target.closest("[data-dialog-progress]")) { dialog.close(); switchView("progress"); }
      if (event.target.closest("[data-dialog-human]")) { dialog.close(); requestHuman(`${capability.title}自助处理后仍未解决`); }
    };
    dialog.showModal();
  } catch (error) { notify(`${error.message}${error.traceId ? ` · ${error.traceId}` : ""}`, true); }
}

function appendMessage(role, text, meta = "") {
  const messages = $("#messages");
  const article = document.createElement("article");
  article.className = `message ${role}`;
  article.innerHTML = `<div class="message-mark">${role === "user" ? "我" : "AI"}</div><div class="bubble"><p>${escapeHtml(text)}</p>${meta ? `<small>${escapeHtml(meta)}</small>` : ""}</div>`;
  messages.append(article);
  messages.scrollTop = messages.scrollHeight;
  return article;
}

async function sendChat(message) {
  const content = message.trim();
  if (!content || state.sending) return;
  appendMessage("user", content);
  $("#chatInput").value = "";
  const loading = appendMessage("assistant", "正在分析");
  loading.classList.add("loading");
  state.sending = true;
  $(".send-btn").disabled = true;
  try {
    const payload = await api("/api/v1/chat", { method: "POST", body: JSON.stringify({ session_id: state.sessionId, message: content, context: { channel: "web", object: state.selectedObject || {} } }) });
    loading.remove();
    appendMessage("assistant", payload.response.text, payload.response.metadata?.data_mode === "mock" ? "演示结果 · MOCK" : "");
    if (payload.response.action === "transfer_human") { setRouteStep(3); notify("人工请求已由异步工单承接"); }
    const replies = payload.response.quick_replies || [];
    if (replies.length) $("#quickReplies").innerHTML = replies.map((item) => `<button data-message="${escapeHtml(item.value)}">${escapeHtml(item.label)}</button>`).join("");
  } catch (error) {
    loading.remove();
    appendMessage("assistant", `暂时无法完成本次处理。${error.traceId ? `追踪编号：${error.traceId}` : "请稍后重试。"}`);
  } finally { state.sending = false; $(".send-btn").disabled = false; }
}

async function requestHuman(summary = "用户从服务台明确请求人工客服") {
  try {
    const entry = await api("/api/v1/support/queue", {
      method: "POST", headers: { "Idempotency-Key": newId("human") },
      body: JSON.stringify({ session_id: state.sessionId, reason: "explicit_request", summary }),
    });
    setRouteStep(3);
    notify(entry.service_message || "人工请求已提交");
    switchView("progress");
  } catch (error) { notify(`${error.message}${error.traceId ? ` · ${error.traceId}` : ""}`, true); }
}

function recordMarkup(type, item) {
  const isTicket = type === "ticket";
  const title = isTicket ? item.title : type === "task" ? item.capability : "人工服务请求";
  const sub = isTicket ? `${item.id} · ${item.category}` : `${item.id} · ${item.data_mode === "mock" ? "Mock 演示" : item.data_mode || ""}`;
  return `<article class="record" ${isTicket ? `data-ticket-id="${escapeHtml(item.id)}"` : ""}>
    <span class="record-icon">${isTicket ? "工" : type === "task" ? "自" : "人"}</span>
    <div><strong>${escapeHtml(title)}</strong><small>${escapeHtml(sub)}</small></div>
    <span class="status-chip ${statusClass(item.status)}">${escapeHtml(statusLabel(item.status))}</span>
  </article>`;
}

async function loadProgress() {
  const list = $("#recordList");
  list.innerHTML = `<div class="empty-state"><p>正在读取服务记录…</p></div>`;
  try {
    const data = await api("/api/v1/support/progress");
    const counts = [data.tasks.length, data.queues.length, data.tickets.length, data.notifications.length];
    const labels = ["自助任务", "人工请求", "服务工单", "站内通知"];
    $("#progressSummary").innerHTML = counts.map((count, index) => `<div class="summary-card"><b>${count}</b><span>${labels[index]}</span></div>`).join("");
    const records = [...data.tickets.map((item) => ["ticket", item]), ...data.tasks.map((item) => ["task", item]), ...data.queues.map((item) => ["queue", item])];
    list.innerHTML = records.length ? records.map(([type, item]) => recordMarkup(type, item)).join("") : `<div class="empty-state"><b>暂无服务记录</b><p>执行自助服务或提交人工请求后，会在这里形成完整记录。</p></div>`;
    list.onclick = (event) => {
      const row = event.target.closest("[data-ticket-id]");
      if (row) openTicket(row.dataset.ticketId);
    };
  } catch (error) { list.innerHTML = `<div class="empty-state"><b>进度加载失败</b><p>${escapeHtml(error.message)}</p></div>`; }
}

async function openTicket(id) {
  try {
    const ticket = await api(`/api/v1/support/tickets/${encodeURIComponent(id)}`);
    const canRate = ["resolved_pending", "closed"].includes(ticket.status);
    dialogContent.innerHTML = `<article class="dialog-body"><p class="eyebrow blue">TICKET · ${escapeHtml(ticket.id)}</p><h2>${escapeHtml(ticket.title)}</h2>
      <span class="status-chip ${statusClass(ticket.status)}">${escapeHtml(statusLabel(ticket.status))}</span>
      <p class="answer">${escapeHtml(ticket.description)}</p>
      <div class="dialog-result"><strong>处理记录</strong><small>${ticket.history.map((item) => `${escapeHtml(statusLabel(item.to_status))} · ${escapeHtml(item.created_at)}`).join("<br>")}</small></div>
      ${canRate ? `<div><strong>这次服务解决了吗？</strong><div class="rating-row">${[1,2,3,4,5].map((score) => `<button data-rating="${score}">${score}</button>`).join("")}</div></div>` : `<p class="muted">工单解决后可在此确认结果并评价。</p>`}
    </article>`;
    dialogContent.onclick = async (event) => {
      const rating = event.target.closest("[data-rating]");
      if (!rating) return;
      await api("/api/v1/support/ratings", { method: "POST", body: JSON.stringify({ service_type: "ticket", service_id: ticket.id, resolved: true, score: Number(rating.dataset.rating), reason: "" }) });
      dialog.close(); notify("感谢评价，服务闭环已完成"); setRouteStep(4);
    };
    dialog.showModal();
  } catch (error) { notify(error.message, true); }
}

async function init() {
  try {
    const identity = await ensureAnonymous();
    const previousUserId = localStorage.getItem("support_user_id");
    if (previousUserId && previousUserId !== identity.user_id) {
      state.sessionId = newId("web");
      localStorage.setItem("support_session_id", state.sessionId);
    }
    localStorage.setItem("support_user_id", identity.user_id);
    state.home = await api("/api/v1/support/home");
    state.selectedObject = state.home.context.objects.find((item) => item.id === state.home.context.selected_object_id) || state.home.context.objects[0];
    renderObjects(); renderCapabilities(); renderCategories(); renderFaqs(state.home.featured_faqs || []);
    $("#contextHint").textContent = `${state.selectedObject.title} · ${state.home.disclaimer}`;
    await api("/api/v1/support/sessions", { method: "POST", body: JSON.stringify({ session_id: state.sessionId, context: { object_id: state.selectedObject.id } }) });
  } catch (error) { notify(`服务台初始化失败：${error.message}`, true); }
  const initialView = ["home", "chat", "progress"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "home";
  switchView(initialView);
}

document.addEventListener("click", (event) => {
  const nav = event.target.closest("[data-view]"); if (nav) switchView(nav.dataset.view);
  if (event.target.closest("[data-go-chat]")) switchView("chat");
  const reply = event.target.closest("[data-message]"); if (reply) { switchView("chat"); sendChat(reply.dataset.message); }
});
$("#faqSearchForm").addEventListener("submit", (event) => { event.preventDefault(); searchFaq(); });
$("#chatForm").addEventListener("submit", (event) => { event.preventDefault(); sendChat($("#chatInput").value); });
$("#chatInput").addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendChat(event.currentTarget.value); } });
$("#humanBtn").addEventListener("click", () => requestHuman());
$("#refreshProgress").addEventListener("click", loadProgress);
$("#agentDeskBtn").addEventListener("click", () => { location.href = "/static/agent.html"; });

init();
