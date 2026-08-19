const REPO = "ponnmayo15-a11y/rt-work";
const DATA_URL = "./data.json";

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else node.setAttribute(k, v);
  }
  for (const child of [].concat(children)) {
    if (child == null) continue;
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

function newIssueUrl(title, body) {
  const params = new URLSearchParams({ title, body });
  return `https://github.com/${REPO}/issues/new?${params.toString()}`;
}

function participationIssueUrl(course) {
  const body = [
    `course_no: ${course.no}`,
    "",
    "--- 以下は自動生成された参加記録です。編集せずそのまま投稿してください ---",
    `講習会名: ${course.title}`,
    `開催日: ${course.event_date}`,
    `単位種別: ${course.category}`,
    `ポイント数: ${course.points ?? ""}`,
  ].join("\n");
  return newIssueUrl(`[参加チェック] ${course.no}: ${course.title}`, body);
}

function settingsIssueUrl(changes) {
  const lines = ["--- 変更したい設定だけ残してそのまま投稿してください ---", ""];
  for (const [key, value] of Object.entries(changes)) {
    lines.push(`${key}=${value}`);
  }
  return newIssueUrl("[設定変更]", lines.join("\n"));
}

function courseCard(course) {
  const meta = [
    course.event_date,
    course.weekday ? `${course.weekday}曜` : null,
    course.start_time ? `${course.start_time}${course.end_time ? "〜" + course.end_time : ""}` : null,
    course.duration,
    course.mode,
    course.prefecture || null,
  ].filter(Boolean);

  const badges = el("div", { class: "course-meta" }, [
    ...meta.map((m) => el("span", { class: "badge" }, m)),
    el("span", { class: "badge points" }, `${course.category} / ${course.points ?? "?"}単位`),
    course.fee_display ? el("span", { class: "badge" }, `参加費: ${course.fee_display}`) : null,
  ]);

  const actions = el("div", { class: "course-actions" }, [
    course.pdf_url ? el("a", { class: "btn", href: course.pdf_url, target: "_blank", rel: "noopener" }, "詳細PDF") : null,
    course.attended
      ? el("span", { class: "attended-tag" }, "✓ 参加済み")
      : el("a", { class: "btn primary", href: participationIssueUrl(course), target: "_blank", rel: "noopener" }, "参加した"),
  ]);

  return el("div", { class: `course-card${course.attended ? " attended" : ""}` }, [
    el("h3", {}, `No.${course.no} ${course.title}`),
    badges,
    el("p", { class: "course-reason" }, course.reason || ""),
    actions,
  ]);
}

function renderCourseList(containerId, courses) {
  const container = document.getElementById(containerId);
  container.innerHTML = "";
  if (!courses.length) {
    container.appendChild(el("div", { class: "empty-state" }, "該当する講習会はありません"));
    return;
  }
  for (const course of courses) container.appendChild(courseCard(course));
}

function renderSummary(data) {
  const h = data.history;
  const grid = document.getElementById("stat-grid");
  const cards = [
    ["合計ポイント数", `${h.total_points}`, ""],
    ["認定期間満了日", h.renewal_period_end, ""],
    ["満了までの残り日数", `${h.renewal_days_remaining}日`, h.renewal_days_remaining < 180 ? "danger" : h.renewal_days_remaining < 365 ? "warn" : ""],
    ["単位取得の目安日", h.credit_target_date, ""],
    ["目安日までの残り日数", `${h.credit_target_days_remaining}日`, h.credit_target_days_remaining < 180 ? "danger" : h.credit_target_days_remaining < 365 ? "warn" : ""],
    ["対象講習会リスト", `${data.main_list.length}件`, ""],
    ["要確認", `${data.manual_list.length}件`, ""],
  ];
  grid.innerHTML = "";
  for (const [label, value, tone] of cards) {
    grid.appendChild(
      el("div", { class: "stat-card" }, [
        el("div", { class: "label" }, label),
        el("div", { class: `value${tone ? " " + tone : ""}` }, value),
      ])
    );
  }
}

function renderHistory(data) {
  const container = document.getElementById("history-list");
  container.innerHTML = "";
  const records = data.history.records;
  if (!records.length) {
    container.appendChild(el("div", { class: "empty-state" }, "参加記録はまだありません"));
    return;
  }
  const table = el("table", { class: "history-table" }, [
    el("thead", {}, el("tr", {}, [
      el("th", {}, "講習会名"),
      el("th", {}, "開催日"),
      el("th", {}, "単位種別"),
      el("th", {}, "ポイント数"),
    ])),
  ]);
  const tbody = el("tbody");
  for (const r of records) {
    tbody.appendChild(
      el("tr", {}, [
        el("td", {}, r.title),
        el("td", {}, r.event_date),
        el("td", {}, r.category || ""),
        el("td", {}, String(r.points ?? "")),
      ])
    );
  }
  table.appendChild(tbody);
  container.appendChild(table);
}

function renderSettings(data) {
  const form = document.getElementById("settings-form");
  form.innerHTML = "";
  const inputs = {};

  for (const s of data.settings) {
    const value = s.is_list ? (s.value || []).join(",") : s.value;
    const input = el("input", { type: "text", value, "data-key": s.key });
    inputs[s.key] = { input, original: value };
    form.appendChild(
      el("div", { class: "settings-field" }, [
        el("label", {}, s.label),
        el("div", { class: "desc" }, s.description),
        input,
      ])
    );
  }

  const submitBtn = el("a", { class: "btn primary", target: "_blank", rel: "noopener", href: "#" }, "設定変更をリクエスト");
  submitBtn.addEventListener("click", (evt) => {
    const changes = {};
    for (const [key, { input, original }] of Object.entries(inputs)) {
      if (input.value !== original) changes[key] = input.value;
    }
    if (Object.keys(changes).length === 0) {
      evt.preventDefault();
      alert("変更がありません");
      return;
    }
    submitBtn.href = settingsIssueUrl(changes);
  });
  form.appendChild(submitBtn);
}

function setupTabs() {
  const buttons = document.querySelectorAll(".tab-btn");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
    });
  });
}

async function main() {
  setupTabs();
  try {
    const resp = await fetch(DATA_URL, { cache: "no-store" });
    const data = await resp.json();
    document.getElementById("updated-at").textContent = `最終更新: ${data.generated_at}`;
    renderSummary(data);
    renderCourseList("main-list", data.main_list);
    renderCourseList("manual-list", data.manual_list);
    renderHistory(data);
    renderSettings(data);
  } catch (err) {
    document.getElementById("updated-at").textContent = "データの読み込みに失敗しました";
    console.error(err);
  }
}

main();
