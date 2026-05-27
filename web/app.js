const TOKEN_KEY = "srf_jobs_token";
const USER_KEY = "srf_jobs_user";

const STATUS_LABELS = {
  none: "검토전",
  watching: "관심",
  applied: "지원완료",
};

const LEVEL_LABELS = {
  intern: "인턴",
  entry: "신입",
  unknown: "확인 필요",
};

const state = {
  token: localStorage.getItem(TOKEN_KEY) || "",
  user: JSON.parse(localStorage.getItem(USER_KEY) || "null"),
  jobs: [],
  selectedId: "",
  config: {
    saramin_configured: false,
    saramin_key_masked: "",
    telegram_configured: false,
    telegram_token_masked: "",
  },
  filters: {
    q: "",
    level: "all",
    source: "all",
    status: "all",
    view: "all",
    tags: new Set(),
    deadlineOnly: false,
    featuredOnly: false,
  },
  sort: "deadline",
};

const els = {
  loginScreen: document.querySelector("#loginScreen"),
  loginForm: document.querySelector("#loginForm"),
  appShell: document.querySelector("#appShell"),
  userBadge: document.querySelector("#userBadge"),
  logoutButton: document.querySelector("#logoutButton"),
  settingsButton: document.querySelector("#settingsButton"),
  settingsDialog: document.querySelector("#settingsDialog"),
  settingsForm: document.querySelector("#settingsForm"),
  settingsMeta: document.querySelector("#settingsMeta"),
  copyFiltersToNotify: document.querySelector("#copyFiltersToNotify"),
  telegramLinkCode: document.querySelector("#telegramLinkCode"),
  telegramClaim: document.querySelector("#telegramClaim"),
  telegramLinkStatus: document.querySelector("#telegramLinkStatus"),
  notifyTagChoices: document.querySelector("#notifyTagChoices"),
  telegramTest: document.querySelector("#telegramTest"),
  searchInput: document.querySelector("#searchInput"),
  levelFilter: document.querySelector("#levelFilter"),
  sourceFilter: document.querySelector("#sourceFilter"),
  statusFilter: document.querySelector("#statusFilter"),
  viewFilter: document.querySelector("#viewFilter"),
  deadlineOnly: document.querySelector("#deadlineOnly"),
  featuredOnly: document.querySelector("#featuredOnly"),
  tagFilterList: document.querySelector("#tagFilterList"),
  sortSelect: document.querySelector("#sortSelect"),
  refreshJobs: document.querySelector("#refreshJobs"),
  openAddDialog: document.querySelector("#openAddDialog"),
  jobDialog: document.querySelector("#jobDialog"),
  jobForm: document.querySelector("#jobForm"),
  jobList: document.querySelector("#jobList"),
  resultCount: document.querySelector("#resultCount"),
  syncState: document.querySelector("#syncState"),
  metricActive: document.querySelector("#metricActive"),
  metricSoon: document.querySelector("#metricSoon"),
  metricSaved: document.querySelector("#metricSaved"),
  metricComments: document.querySelector("#metricComments"),
  toast: document.querySelector("#toast"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function parseList(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function joinList(value) {
  return Array.isArray(value) ? value.join(", ") : "";
}

function showToast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => els.toast.classList.remove("show"), 2800);
}

function setSync(message) {
  els.syncState.textContent = message;
}

function authHeaders() {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${state.token}`,
  };
}

async function apiFetch(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      Authorization: `Bearer ${state.token}`,
      ...(options.headers || {}),
    },
  });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) {
    logout(false);
    throw new Error(data.error || "로그인이 필요합니다.");
  }
  if (!response.ok) {
    throw new Error(data.error || "요청에 실패했습니다.");
  }
  return data;
}

function showApp() {
  els.loginScreen.classList.add("hidden");
  els.appShell.classList.remove("hidden");
  els.userBadge.textContent = state.user?.display_name || "";
}

function showLogin() {
  els.appShell.classList.add("hidden");
  els.loginScreen.classList.remove("hidden");
}

function logout(showMessage = true) {
  state.token = "";
  state.user = null;
  state.jobs = [];
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  showLogin();
  if (showMessage) showToast("로그아웃했습니다.");
}

async function login(form) {
  const formData = new FormData(form);
  const response = await fetch("/api/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      display_name: formData.get("display_name"),
      password: formData.get("password"),
    }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "로그인하지 못했습니다.");
  state.token = data.token;
  state.user = data.user;
  localStorage.setItem(TOKEN_KEY, state.token);
  localStorage.setItem(USER_KEY, JSON.stringify(state.user));
  showApp();
  await fetchMe();
  await fetchJobs();
}

async function fetchMe() {
  const data = await apiFetch("/api/me");
  state.user = data.user;
  state.config = data.config || state.config;
  localStorage.setItem(USER_KEY, JSON.stringify(state.user));
  els.userBadge.textContent = state.user.display_name;
  updateSettingsMeta();
}

async function fetchJobs() {
  setSync("불러오는 중");
  const data = await apiFetch("/api/jobs");
  state.jobs = data.jobs || [];
  if (state.selectedId && !state.jobs.some((job) => job.id === state.selectedId)) {
    state.selectedId = "";
  }
  setSync("동기화됨");
  render();
}

function deadlineDate(job) {
  if (!job.deadline || ["상시", "수시", "채용시"].includes(job.deadline)) return null;
  const value = new Date(`${job.deadline}T23:59:59`);
  return Number.isNaN(value.getTime()) ? null : value;
}

function daysLeft(job) {
  const deadline = deadlineDate(job);
  if (!deadline) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.ceil((deadline - today) / 86400000);
}

function deadlineLabel(job) {
  if (["상시", "수시", "채용시"].includes(job.deadline)) return job.deadline;
  const left = daysLeft(job);
  if (left === null) return "마감 확인";
  if (left < 0) return "마감";
  if (left === 0) return "오늘 마감";
  return `D-${left}`;
}

function deadlineClass(job) {
  const left = daysLeft(job);
  if (left === null) return "";
  if (left < 0) return "closed";
  if (left <= 7) return "soon";
  return "";
}

function userState(job) {
  const personal = {
    saved: false,
    status: "none",
    comment: "",
    hidden: false,
    ...(job.user_state || {}),
  };
  if (personal.status === "watching") {
    personal.saved = true;
  }
  if (!["none", "watching", "applied"].includes(personal.status)) {
    personal.status = "none";
  }
  return personal;
}

function visibleJobs() {
  const query = state.filters.q.trim().toLowerCase();
  const selectedTags = [...state.filters.tags];
  return state.jobs
    .filter((job) => {
      const personal = userState(job);
      if (job.hidden || job.auto_hidden) return false;
      if (state.filters.level !== "all" && job.level !== state.filters.level) return false;
      if (state.filters.source !== "all" && job.source !== state.filters.source) return false;
      if (state.filters.status === "watching" && !personal.saved) return false;
      if (state.filters.status === "applied" && personal.status !== "applied") return false;
      if (state.filters.view === "saved" && !personal.saved) return false;
      if (state.filters.view === "commented" && !personal.comment) return false;
      if (state.filters.view === "applied" && personal.status !== "applied") return false;
      if (state.filters.featuredOnly && !job.featured) return false;
      if (selectedTags.length && !selectedTags.every((tag) => (job.tags || []).includes(tag))) return false;
      if (state.filters.deadlineOnly) {
        const left = daysLeft(job);
        if (left === null || left < 0 || left > 7) return false;
      }
      if (query) {
        const haystack = [
          job.company,
          job.title,
          job.source,
          job.location,
          job.employment_type,
          personal.comment,
          ...(job.tags || []),
        ]
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(query)) return false;
      }
      return true;
    })
    .sort((a, b) => {
      if (state.sort === "featured") {
        if (Boolean(a.featured) !== Boolean(b.featured)) return a.featured ? -1 : 1;
      }
      if (state.sort === "latest") {
        return String(b.published_at || b.created_at || "").localeCompare(String(a.published_at || a.created_at || ""));
      }
      const aTime = deadlineDate(a)?.getTime() ?? Number.MAX_SAFE_INTEGER;
      const bTime = deadlineDate(b)?.getTime() ?? Number.MAX_SAFE_INTEGER;
      if (aTime !== bTime) return aTime - bTime;
      return String(a.title).localeCompare(String(b.title));
    });
}

function uniqueOptions(field) {
  return [...new Set(state.jobs.map((job) => job[field]).filter(Boolean))].sort((a, b) => a.localeCompare(b));
}

function uniqueTags() {
  return [...new Set(state.jobs.flatMap((job) => job.tags || []))].sort((a, b) => a.localeCompare(b));
}

function syncSelectOptions(select, values, allLabel) {
  const current = select.value;
  select.innerHTML = `<option value="all">${escapeHtml(allLabel)}</option>${values
    .map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`)
    .join("")}`;
  select.value = values.includes(current) ? current : "all";
}

function renderTagFilters() {
  const tags = uniqueTags();
  if (!tags.length) {
    els.tagFilterList.innerHTML = `<span class="muted-text">태그 없음</span>`;
    return;
  }
  els.tagFilterList.innerHTML = tags
    .map((tag) => {
      const active = state.filters.tags.has(tag) ? " active" : "";
      return `<button class="tag-filter${active}" type="button" data-filter-tag="${escapeHtml(tag)}">${escapeHtml(tag)}</button>`;
    })
    .join("");
}

function renderNotificationTagChoices() {
  const tags = uniqueTags();
  const activeTags = new Set(state.user?.notification?.filters?.tags || []);
  if (!tags.length) {
    els.notifyTagChoices.innerHTML = `<span class="muted-text">태그 없음</span>`;
    return;
  }
  els.notifyTagChoices.innerHTML = tags
    .map((tag) => {
      const active = activeTags.has(tag) ? " active" : "";
      return `<button class="tag-filter${active}" type="button" data-notify-tag="${escapeHtml(tag)}">${escapeHtml(tag)}</button>`;
    })
    .join("");
}

function renderMetrics() {
  const visible = state.jobs.filter((job) => !job.hidden && !job.auto_hidden);
  const active = visible.filter((job) => (daysLeft(job) ?? 1) >= 0);
  els.metricActive.textContent = active.length;
  els.metricSoon.textContent = active.filter((job) => {
    const left = daysLeft(job);
    return left !== null && left >= 0 && left <= 7;
  }).length;
  els.metricSaved.textContent = visible.filter((job) => userState(job).saved).length;
  els.metricComments.textContent = visible.filter((job) => userState(job).comment).length;
}

function splitBullets(value) {
  if (Array.isArray(value)) return value.filter(Boolean);
  const text = String(value || "").trim();
  if (!text) return ["원문 확인 필요"];
  const normalized = text.replace(/\.$/, "");
  const parts = normalized
    .split(/(?:,\s*|ㆍ|;\s*|\n+)/)
    .map((item) => item.trim())
    .filter(Boolean);
  return parts.length > 1 ? parts.slice(0, 5) : [normalized];
}

function bulletList(value) {
  return `<ul class="bullet-list">${splitBullets(value)
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("")}</ul>`;
}

function linkButton(url, label) {
  if (!url || url === "#") {
    return `<span class="button disabled">${escapeHtml(label)}</span>`;
  }
  return `<a class="button link-button" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(label)} ↗</a>`;
}

function renderDetail(job) {
  const summary = job.summary || {};
  const personal = userState(job);
  const sourceUrl = job.source_url || job.apply_url || "";
  return `
    <div class="job-detail">
      <div class="detail-actions">
        <button class="chip-button${personal.saved ? " active" : ""}" type="button" data-toggle-save="${escapeHtml(job.id)}">관심</button>
        <button class="chip-button${personal.status === "applied" ? " active" : ""}" type="button" data-personal-status="applied" data-job-id="${escapeHtml(job.id)}">지원완료</button>
      </div>

      <div class="summary-grid">
        <section class="summary-item">
          <span class="summary-label">주요업무</span>
          ${bulletList(summary.work)}
        </section>
        <section class="summary-item">
          <span class="summary-label">지원자격</span>
          ${bulletList(summary.requirements)}
        </section>
        <section class="summary-item">
          <span class="summary-label">우대사항</span>
          ${bulletList(summary.advantages)}
        </section>
        <section class="summary-item">
          <span class="summary-label">확인</span>
          ${bulletList(summary.notice)}
        </section>
      </div>

      <label class="field note-field">
        <span>내 코멘트</span>
        <textarea data-comment-input="${escapeHtml(job.id)}" placeholder="예: 영문 CV 필요, 마감 전 리마인드">${escapeHtml(personal.comment || "")}</textarea>
      </label>
      <div class="detail-bottom">
        <button class="button" type="button" data-save-comment="${escapeHtml(job.id)}">코멘트 저장</button>
        <div class="link-row">
          ${linkButton(sourceUrl, "원문 보기")}
        </div>
      </div>
    </div>
  `;
}

function renderJobCard(job) {
  const selected = job.id === state.selectedId;
  const personal = userState(job);
  const sample = job.is_sample ? `<span class="sample-pill">샘플</span>` : "";
  const saved = personal.saved ? `<span class="saved-pill">내 관심</span>` : "";
  const commentPreview = personal.comment
    ? `<p class="comment-preview">${escapeHtml(personal.comment)}</p>`
    : "";
  const recommended = job.featured
    ? `<span class="recommended-pill">추천 ${Number(job.reaction_count || 0)}명</span>`
    : "";
  return `
    <article class="job-card${selected ? " selected" : ""}${job.featured ? " recommended" : ""}">
      <button class="job-summary" type="button" data-select="${escapeHtml(job.id)}" aria-expanded="${selected ? "true" : "false"}">
        <div class="card-top">
          <div>
            <p class="company">${escapeHtml(job.company || "회사 확인")}</p>
            <h3 class="job-title">${escapeHtml(job.title || "공고명 확인")}</h3>
          </div>
          <span class="deadline-pill ${deadlineClass(job)}">${escapeHtml(deadlineLabel(job))}</span>
        </div>
        <div class="meta-row">
          <span>${escapeHtml(LEVEL_LABELS[job.level] || "확인 필요")}</span>
          <span>${escapeHtml(job.employment_type || "고용형태 확인")}</span>
          <span>${escapeHtml(job.location || "지역 확인")}</span>
          <span>${escapeHtml(job.source || "출처 확인")}</span>
          ${recommended}
          ${personal.status === "applied" ? `<span class="status-pill">${escapeHtml(STATUS_LABELS.applied)}</span>` : ""}
          ${saved}
          ${sample}
        </div>
        <div class="tags">
          ${(job.tags || [])
            .map((tag) => `<span class="tag" data-inline-tag="${escapeHtml(tag)}">${escapeHtml(tag)}</span>`)
            .join("")}
        </div>
        ${commentPreview}
      </button>
      ${selected ? renderDetail(job) : ""}
    </article>
  `;
}

function renderList() {
  const jobs = visibleJobs();
  els.resultCount.textContent = `${jobs.length}개 공고`;
  if (!jobs.length) {
    els.jobList.innerHTML = `<div class="empty-list">조건에 맞는 공고가 없습니다.</div>`;
    return;
  }
  els.jobList.innerHTML = jobs.map(renderJobCard).join("");
}

function render() {
  syncSelectOptions(els.sourceFilter, uniqueOptions("source"), "전체");
  renderTagFilters();
  renderNotificationTagChoices();
  renderMetrics();
  renderList();
}

function updateLocalJob(jobId, userStateUpdates) {
  const index = state.jobs.findIndex((job) => job.id === jobId);
  if (index < 0) return;
  state.jobs[index].user_state = {
    ...userState(state.jobs[index]),
    ...userStateUpdates,
  };
}

function replaceLocalJob(updatedJob) {
  if (!updatedJob?.id) return;
  const index = state.jobs.findIndex((job) => job.id === updatedJob.id);
  if (index >= 0) {
    state.jobs[index] = updatedJob;
  } else if (!updatedJob.hidden && !updatedJob.auto_hidden) {
    state.jobs.push(updatedJob);
  }
}

async function patchPersonalJob(id, updates) {
  const data = await apiFetch(`/api/user/jobs/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(updates),
  });
  if (data.job) replaceLocalJob(data.job);
  else updateLocalJob(id, data.user_state);
  render();
}

async function addJob(form) {
  const formData = new FormData(form);
  const tags = String(formData.get("tags") || "")
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
  const sourceUrl = String(formData.get("source_url") || "");
  const payload = {
    company: formData.get("company"),
    title: formData.get("title"),
    level: formData.get("level"),
    employment_type: formData.get("employment_type"),
    location: formData.get("location"),
    deadline: formData.get("deadline"),
    source: "Manual",
    source_url: sourceUrl,
    apply_url: sourceUrl,
    tags,
  };
  await apiFetch("/api/jobs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  await fetchJobs();
  showToast("공고를 추가했습니다.");
}

function updateSettingsMeta() {
  const saramin = state.config.saramin_configured
    ? `공유 사람인 키 저장됨: ${state.config.saramin_key_masked}. 서버가 1시간마다 자동 수집합니다.`
    : "사람인 키 미설정. KOFIA와 슈퍼루키는 서버가 1시간마다 자동 수집합니다.";
  const telegram = state.config.telegram_configured
    ? "텔레그램 봇 설정됨."
    : "텔레그램 봇 토큰 미설정.";
  els.settingsMeta.textContent = `${saramin} ${telegram}`;
}

function populateNotificationForm() {
  const notification = state.user?.notification || {};
  const filters = notification.filters || {};
  els.settingsForm.elements.notify_enabled.checked = Boolean(notification.enabled);
  const linked = Boolean(notification.telegram_chat_id);
  const code = notification.telegram_link_code;
  els.telegramLinkStatus.textContent = linked
    ? "이 계정의 텔레그램이 연결되어 있습니다."
    : code
    ? `텔레그램 봇에게 ${code} 를 보낸 뒤 연결 확인을 누르세요.`
    : "연결 코드 만들기를 누르고, 나온 코드를 텔레그램 봇에게 보내세요.";
  renderNotificationTagChoices();
}

function copyCurrentFiltersToNotificationForm() {
  const notification = state.user?.notification || {};
  notification.filters = {
    ...(notification.filters || {}),
    tags: [...state.filters.tags],
    q: "",
    levels: [],
    sources: [],
    deadline_days: 0,
    featured_only: false,
  };
  state.user.notification = notification;
  els.settingsForm.elements.notify_enabled.checked = true;
  renderNotificationTagChoices();
}

async function saveNotificationSettings(form) {
  const formData = new FormData(form);
  const notification = state.user?.notification || {};
  const filters = notification.filters || {};
  const payload = {
    enabled: formData.get("notify_enabled") === "on",
    filters: {
      q: "",
      levels: [],
      sources: [],
      tags: filters.tags || [],
      deadline_days: 0,
      featured_only: false,
    },
  };
  const data = await apiFetch("/api/me/notification", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  state.user.notification = data.notification;
  localStorage.setItem(USER_KEY, JSON.stringify(state.user));
  return data.notification_result || { sent: 0 };
}

function notificationResultText(result, baseMessage) {
  const sent = Number(result?.sent || 0);
  const matched = Number(result?.matched || 0);
  const alreadyNotified = Number(result?.already_notified || 0);
  const errors = result?.errors || [];
  if (sent > 0 && errors.length) {
    return `${baseMessage}. 기존 공고 ${sent}개를 보냈고, ${errors.length}개는 실패했습니다.`;
  }
  if (sent > 0) {
    return `${baseMessage}. 기존 공고 ${sent}개를 텔레그램으로 보냈습니다.`;
  }
  if (result?.reason === "no_chat") {
    return `${baseMessage}. 텔레그램 연결 확인을 먼저 완료해야 발송됩니다.`;
  }
  if (result?.reason === "no_token") {
    return `${baseMessage}. 서버에 텔레그램 봇 토큰이 없어 발송하지 못했습니다.`;
  }
  if (result?.reason === "no_tags") {
    return `${baseMessage}. 알림 태그를 1개 이상 선택해야 발송됩니다.`;
  }
  if (result?.reason === "send_failed") {
    return `${baseMessage}. 텔레그램 발송이 실패했습니다: ${errors[0] || "원인 확인 필요"}`;
  }
  if (matched > 0 && alreadyNotified >= matched) {
    return `${baseMessage}. 매칭 공고 ${matched}개는 이미 알림 보낸 공고입니다.`;
  }
  if (matched === 0) {
    return `${baseMessage}. 현재 선택한 태그와 맞는 기존 공고는 없습니다.`;
  }
  return baseMessage;
}

async function saveSettings(form) {
  const result = await saveNotificationSettings(form);
  updateSettingsMeta();
  showToast(notificationResultText(result, "설정을 저장했습니다"));
  return result;
}

async function sendTelegramTest() {
  await saveNotificationSettings(els.settingsForm);
  await apiFetch("/api/telegram/test", { method: "POST" });
  showToast("텔레그램 테스트 메시지를 보냈습니다.");
}

async function createTelegramLinkCode() {
  const data = await apiFetch("/api/telegram/link-code", { method: "POST" });
  state.user.notification = {
    ...(state.user.notification || {}),
    telegram_link_code: data.code,
  };
  localStorage.setItem(USER_KEY, JSON.stringify(state.user));
  populateNotificationForm();
  showToast("텔레그램 연결 코드를 만들었습니다.");
}

async function claimTelegramChat() {
  const data = await apiFetch("/api/telegram/claim-chat", { method: "POST" });
  state.user.notification = data.notification;
  localStorage.setItem(USER_KEY, JSON.stringify(state.user));
  populateNotificationForm();
  const base = data.name ? `${data.name} 텔레그램을 연결했습니다.` : "텔레그램을 연결했습니다.";
  showToast(notificationResultText(data.notification_result || {}, base));
}

function bindEvents() {
  els.loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await login(els.loginForm);
    } catch (error) {
      showToast(error.message);
    }
  });

  document.addEventListener("click", (event) => {
    const closeButton = event.target.closest("[data-close-dialog]");
    if (!closeButton) return;
    const dialog = document.querySelector(`#${CSS.escape(closeButton.dataset.closeDialog)}`);
    if (dialog?.close) dialog.close();
  });

  els.logoutButton.addEventListener("click", () => logout());

  els.settingsButton.addEventListener("click", () => {
    els.settingsForm.reset();
    populateNotificationForm();
    updateSettingsMeta();
    els.settingsDialog.showModal();
  });

  els.copyFiltersToNotify.addEventListener("click", () => {
    copyCurrentFiltersToNotificationForm();
    showToast("현재 필터를 알림 필터로 복사했습니다.");
  });

  els.telegramLinkCode.addEventListener("click", async () => {
    try {
      await createTelegramLinkCode();
    } catch (error) {
      showToast(error.message);
    }
  });

  els.telegramClaim.addEventListener("click", async () => {
    try {
      await claimTelegramChat();
    } catch (error) {
      showToast(error.message);
    }
  });

  els.telegramTest.addEventListener("click", async () => {
    try {
      await sendTelegramTest();
    } catch (error) {
      showToast(error.message);
    }
  });

  els.settingsForm.addEventListener("submit", async (event) => {
    if (event.submitter?.value === "cancel") return;
    event.preventDefault();
    try {
      const result = await saveSettings(els.settingsForm);
      const keepOpenReasons = new Set(["no_chat", "no_token", "no_tags", "send_failed"]);
      if (state.token && !keepOpenReasons.has(result.reason)) els.settingsDialog.close();
    } catch (error) {
      showToast(error.message);
    }
  });

  els.searchInput.addEventListener("input", (event) => {
    state.filters.q = event.target.value;
    render();
  });
  els.levelFilter.addEventListener("change", (event) => {
    state.filters.level = event.target.value;
    render();
  });
  els.sourceFilter.addEventListener("change", (event) => {
    state.filters.source = event.target.value;
    render();
  });
  els.statusFilter.addEventListener("change", (event) => {
    state.filters.status = event.target.value;
    render();
  });
  els.viewFilter.addEventListener("change", (event) => {
    state.filters.view = event.target.value;
    render();
  });
  els.deadlineOnly.addEventListener("change", (event) => {
    state.filters.deadlineOnly = event.target.checked;
    render();
  });
  els.featuredOnly.addEventListener("change", (event) => {
    state.filters.featuredOnly = event.target.checked;
    render();
  });
  els.sortSelect.addEventListener("change", (event) => {
    state.sort = event.target.value;
    render();
  });
  els.tagFilterList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-filter-tag]");
    if (!button) return;
    const tag = button.dataset.filterTag;
    if (state.filters.tags.has(tag)) state.filters.tags.delete(tag);
    else state.filters.tags.add(tag);
    render();
  });
  els.notifyTagChoices.addEventListener("click", (event) => {
    const button = event.target.closest("[data-notify-tag]");
    if (!button) return;
    const tag = button.dataset.notifyTag;
    const notification = state.user?.notification || {};
    const filters = notification.filters || {};
    const tags = new Set(filters.tags || []);
    if (tags.has(tag)) tags.delete(tag);
    else tags.add(tag);
    state.user.notification = {
      ...notification,
      filters: {
        ...filters,
        tags: [...tags],
      },
    };
    localStorage.setItem(USER_KEY, JSON.stringify(state.user));
    renderNotificationTagChoices();
  });
  els.refreshJobs.addEventListener("click", async () => {
    try {
      await fetchJobs();
      showToast("새로고침했습니다.");
    } catch (error) {
      showToast(error.message);
    }
  });
  els.openAddDialog.addEventListener("click", () => {
    els.jobForm.reset();
    els.jobDialog.showModal();
  });
  els.jobForm.addEventListener("submit", async (event) => {
    if (event.submitter?.value === "cancel") return;
    event.preventDefault();
    try {
      await addJob(els.jobForm);
      els.jobDialog.close();
    } catch (error) {
      showToast(error.message);
    }
  });
  els.jobList.addEventListener("click", async (event) => {
    const tag = event.target.closest("[data-inline-tag]");
    if (tag) {
      state.filters.tags.add(tag.dataset.inlineTag);
      render();
      return;
    }

    const saveButton = event.target.closest("[data-toggle-save]");
    if (saveButton) {
      const id = saveButton.dataset.toggleSave;
      const job = state.jobs.find((item) => item.id === id);
      try {
        await patchPersonalJob(id, { saved: !userState(job).saved });
        showToast(userState(state.jobs.find((item) => item.id === id)).saved ? "관심 표시했습니다." : "관심을 취소했습니다.");
      } catch (error) {
        showToast(error.message);
      }
      return;
    }

    const statusButton = event.target.closest("[data-personal-status]");
    if (statusButton) {
      const id = statusButton.dataset.jobId;
      const job = state.jobs.find((item) => item.id === id);
      const nextStatus = userState(job).status === statusButton.dataset.personalStatus ? "none" : statusButton.dataset.personalStatus;
      try {
        await patchPersonalJob(id, { status: nextStatus });
        showToast("내 상태를 저장했습니다.");
      } catch (error) {
        showToast(error.message);
      }
      return;
    }

    const commentButton = event.target.closest("[data-save-comment]");
    if (commentButton) {
      const id = commentButton.dataset.saveComment;
      const input = document.querySelector(`[data-comment-input="${CSS.escape(id)}"]`);
      try {
        await patchPersonalJob(id, { comment: input?.value || "" });
        showToast("코멘트를 저장했습니다.");
      } catch (error) {
        showToast(error.message);
      }
      return;
    }

    const cardButton = event.target.closest("[data-select]");
    if (cardButton) {
      state.selectedId = state.selectedId === cardButton.dataset.select ? "" : cardButton.dataset.select;
      render();
    }
  });
}

async function boot() {
  bindEvents();
  if (!state.token) {
    showLogin();
    return;
  }
  showApp();
  try {
    await fetchMe();
    await fetchJobs();
  } catch (error) {
    showToast(error.message);
  }
}

boot();
