"use strict";
(async () => {
  const $ = (s) => document.querySelector(s);
  let savedTheme = "system";
  try {
    savedTheme = localStorage.getItem("profile-theme") || "system";
  } catch {}
  function setTheme(value) {
    $("#theme").value = value;
    if (value === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = value;
    try {
      localStorage.setItem("profile-theme", value);
    } catch {}
  }
  setTheme(
    ["system", "light", "dark"].includes(savedTheme) ? savedTheme : "system",
  );
  $("#theme").addEventListener("change", (e) => setTheme(e.target.value));
  try {
    const response = await fetch("./data.json", { cache: "no-cache" });
    if (!response.ok) throw new Error("Snapshot unavailable");
    const data = await response.json();
    if (
      data.schema_version !== 1 ||
      data.data_kind !== "public_snapshot" ||
      !/^\d{4}-\d{2}-\d{2}$/.test(data.snapshot?.date) ||
      !Array.isArray(data.records) ||
      !Array.isArray(data.repositories)
    )
      throw new Error("Invalid snapshot");
    const end = data.snapshot.date;
    const dayMs = 86400000;
    const dateAt = (s) => new Date(s + "T00:00:00Z");
    const shift = (s, n) =>
      new Date(dateAt(s).getTime() + n * dayMs).toISOString().slice(0, 10);
    const daysBetween = (a, b) => Math.round((dateAt(b) - dateAt(a)) / dayMs);
    const dates = (a, b) =>
      Array.from({ length: daysBetween(a, b) + 1 }, (_, i) => shift(a, i));
    const fmt = (n) => n.toLocaleString("en-US");
    const dateLabel = (
      s,
      opts = { month: "short", day: "numeric", year: "numeric" },
    ) => dateAt(s).toLocaleDateString("en-US", { ...opts, timeZone: "UTC" });
    const escape = (s) =>
      String(s).replace(
        /[&<>"']/g,
        (c) =>
          ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;",
          })[c],
      );
    const safeUrl = (value) => {
      try {
        const url = new URL(value);
        return url.protocol === "https:" &&
          url.hostname === "github.com" &&
          url.pathname.startsWith("/" + data.owner + "/")
          ? url.href
          : "https://github.com/" + encodeURIComponent(data.owner);
      } catch {
        return "https://github.com/LeePepe";
      }
    };
    const state = {
      actor: "all",
      repo: "all",
      metric: "commit",
      range: 365,
      selected: end,
    };
    let calendarDates = [],
      daily = new Map(),
      base = [],
      selectedRecords = [];
    const tooltip = $("#day-tooltip");
    data.repositories.forEach((repo) => {
      const option = document.createElement("option");
      option.value = repo.name;
      option.textContent = repo.name;
      $("#repository").append(option);
    });
    const level = (n) =>
      n === 0 ? 0 : n < 4 ? 1 : n < 10 ? 2 : n < 20 ? 3 : 4;
    function sparkline(values) {
      if (values.length > 60) {
        const size = Math.ceil(values.length / 52);
        values = Array.from(
          { length: Math.ceil(values.length / size) },
          (_, i) =>
            values.slice(i * size, (i + 1) * size).reduce((a, b) => a + b, 0),
        );
      }
      const max = Math.max(...values, 1);
      const points = values.map((v, i) => [
        (i * 200) / Math.max(values.length - 1, 1),
        30 - (v / max) * 26,
      ]);
      const line = "M" + points.map((p) => p.join(",")).join(" L");
      return `<svg class="sparkline" viewBox="0 0 200 32" preserveAspectRatio="none" aria-hidden="true"><path class="area" d="${line} L200,32 L0,32 Z"/><path class="line" d="${line}"/></svg>`;
    }
    function sumRecords(records) {
      return records.reduce(
        (a, r) => ({
          count: a.count + 1,
          added: a.added + (r.additions || 0),
          deleted: a.deleted + (r.deletions || 0),
        }),
        { count: 0, added: 0, deleted: 0 },
      );
    }
    function renderKpis(start) {
      const recent7 = shift(end, -Math.min(6, state.range - 1));
      const recent30 = shift(end, -Math.min(29, state.range - 1));
      const recent = (n) => selectedRecords.filter((r) => r.date >= n);
      const human = selectedRecords.filter((r) => r.actor === "human").length;
      const agent = selectedRecords.length - human;
      const mix = selectedRecords.length
        ? Math.round((human / selectedRecords.length) * 100)
        : 0;
      const unit = state.metric === "commit" ? "commits" : "PRs opened";
      const active = new Set(selectedRecords.map((r) => r.date)).size;
      const values = (s, e) =>
        dates(s, e).map((d) => daily.get(d)?.length || 0);
      const card = (label, value, meta, values, extra = "") =>
        `<article class="kpi"><p class="kpi-label">${label}${extra}</p><p class="kpi-value">${fmt(value)}<small>${unit}</small></p>${sparkline(values)}<p class="kpi-meta">${meta}</p></article>`;
      $("#kpis").innerHTML =
        card(
          `Selected ${state.range} days`,
          selectedRecords.length,
          `${fmt(active)} active ${active === 1 ? "day" : "days"} · UTC`,
          values(start, end),
        ) +
        card(
          "Last 7 days",
          recent(recent7).length,
          `${dateLabel(recent7, { month: "short", day: "numeric" })} – ${dateLabel(end, { month: "short", day: "numeric" })}`,
          values(recent7, end),
        ) +
        card(
          "Last 30 days",
          recent(recent30).length,
          state.range < 30
            ? "Within this 7-day selection"
            : `${dateLabel(recent30, { month: "short", day: "numeric" })} – ${dateLabel(end, { month: "short", day: "numeric" })}`,
          values(recent30, end),
        ) +
        `<article class="kpi"><p class="kpi-label">Human / agent</p><p class="kpi-value">${mix}<small>% human</small></p><div class="mix-bar" aria-hidden="true"><i class="human" style="width:${mix}%"></i><i class="agent" style="width:${selectedRecords.length ? 100 - mix : 0}%"></i></div><div class="mix-legend"><span><i class="actor-dot human"></i>${fmt(human)} human</span><span><i class="actor-dot agent"></i>${fmt(agent)} agent</span></div><p class="kpi-meta">${selectedRecords.length ? "Within the selected filters" : "No matching activity"}</p></article>`;
    }
    function cell(date, recent = false) {
      const count = daily.get(date)?.length || 0;
      const current = state.selected === date;
      return `<button type="button" class="day-cell" data-date="${date}" data-count="${count}" data-level="${level(count)}" aria-label="${dateLabel(date)}: ${count} ${state.metric === "commit" ? "commits" : "pull requests opened"}${current ? ", selected" : ""}" aria-pressed="${current}" tabindex="${current ? 0 : -1}">${recent ? `<span>${dateLabel(date, { month: "short", day: "numeric" })}</span><b>${count}</b>` : ""}</button>`;
    }
    function renderCalendar(start) {
      calendarDates = dates(start, end);
      $("#calendar-title").textContent =
        state.range === 365
          ? `A year of ${state.metric === "commit" ? "commits" : "pull requests"}`
          : `${state.range} days of ${state.metric === "commit" ? "commits" : "pull requests"}`;
      const actorText =
        state.actor === "all"
          ? "Everyone"
          : state.actor === "human"
            ? "Human"
            : "Agent";
      $("#calendar-summary").textContent =
        `${dateLabel(start, { month: "short", day: "numeric", year: "numeric" })} – ${dateLabel(end, { month: "short", day: "numeric", year: "numeric" })} · ${actorText}`;
      if (state.range === 365) {
        const leading = dateAt(start).getUTCDay();
        let monthLabels = "";
        let lastMonth = "";
        calendarDates.forEach((date, i) => {
          const month = date.slice(0, 7);
          if (
            month !== lastMonth &&
            ((i === 0 && Number(start.slice(8)) <= 15) || date.endsWith("-01"))
          ) {
            const left = Math.floor((leading + i) / 7) * 13;
            monthLabels += `<span style="left:${left}px">${dateLabel(date, { month: "short" })}</span>`;
            lastMonth = month;
          }
        });
        const blanks = Array.from(
          { length: leading },
          () => '<span aria-hidden="true"></span>',
        ).join("");
        $("#calendar").innerHTML =
          `<div class="calendar-year"><div class="month-labels" aria-hidden="true">${monthLabels}</div><div class="year-body"><div class="weekday-labels" aria-hidden="true"><span></span><span>Mon</span><span></span><span>Wed</span><span></span><span>Fri</span><span></span></div><div class="year-grid" role="group" aria-label="Daily ${state.metric === "commit" ? "commit" : "pull request"} counts">${blanks}${calendarDates.map((d) => cell(d)).join("")}</div></div></div>`;
        $(".calendar-scroll").setAttribute(
          "aria-label",
          "Calendar. Scroll horizontally to explore the full year.",
        );
      } else {
        $("#calendar").innerHTML =
          `<div class="calendar-recent ${state.range === 7 ? "seven" : ""}" role="group" aria-label="Daily ${state.metric === "commit" ? "commit" : "pull request"} counts">${calendarDates.map((d) => cell(d, true)).join("")}</div>`;
        $(".calendar-scroll").setAttribute(
          "aria-label",
          `${state.range}-day calendar`,
        );
      }
      const pr = state.metric === "pr";
      $("#cohort-note").hidden = !pr;
      if (pr) {
        const merged = selectedRecords.filter(
          (r) => r.state === "merged",
        ).length;
        const open = selectedRecords.filter((r) => r.state === "open").length;
        const closed = selectedRecords.filter(
          (r) => r.state === "closed",
        ).length;
        $("#cohort-note").innerHTML =
          `<strong>${merged} merged · ${open} open · ${closed} closed unmerged</strong><br>Current states of PRs created in this period, not merge events during it.`;
      }
      $("#calendar-hint").innerHTML =
        `Hover or focus · select for details · Arrow keys to browse${state.range === 365 ? '<span class="mobile-hint"> · Swipe the year →</span>' : ""}`;
      $("#calendar")
        .querySelectorAll(".day-cell")
        .forEach((button) => {
          button.addEventListener("mouseenter", () => showTooltip(button));
          button.addEventListener("mouseleave", hideTooltip);
          button.addEventListener("focus", () => showTooltip(button));
          button.addEventListener("blur", hideTooltip);
          button.addEventListener("click", () =>
            selectDate(button.dataset.date),
          );
          button.addEventListener("keydown", (e) => navigateDate(e, button));
        });
    }
    function showTooltip(button) {
      const date = button.dataset.date;
      const records = daily.get(date) || [];
      const human = records.filter((r) => r.actor === "human").length;
      const agent = records.length - human;
      tooltip.innerHTML = `<strong>${dateLabel(date)}</strong>${records.length} ${state.metric === "commit" ? "commits" : "PRs opened"}<br>${human} human · ${agent} agent`;
      tooltip.hidden = false;
      button.setAttribute("aria-describedby", "day-tooltip");
      const rect = button.getBoundingClientRect();
      const box = tooltip.getBoundingClientRect();
      tooltip.style.left =
        Math.max(
          8,
          Math.min(
            innerWidth - box.width - 8,
            rect.left + rect.width / 2 - box.width / 2,
          ),
        ) + "px";
      tooltip.style.top =
        (rect.top - box.height - 10 > 8
          ? rect.top - box.height - 10
          : rect.bottom + 10) + "px";
    }
    function hideTooltip() {
      tooltip.hidden = true;
      document
        .querySelectorAll('[aria-describedby="day-tooltip"]')
        .forEach((e) => e.removeAttribute("aria-describedby"));
    }
    function selectDate(date) {
      state.selected = date;
      $("#calendar")
        .querySelectorAll(".day-cell")
        .forEach((b) => {
          const selected = b.dataset.date === date;
          b.setAttribute("aria-pressed", String(selected));
          b.tabIndex = selected ? 0 : -1;
        });
      renderDay();
      hideTooltip();
    }
    function navigateDate(e, button) {
      let i = calendarDates.indexOf(button.dataset.date);
      let next = i;
      const annual = state.range === 365;
      const cols =
        state.range === 7
          ? innerWidth < 600
            ? 4
            : 7
          : innerWidth < 600
            ? 5
            : 10;
      if (e.key === "ArrowRight") next += annual ? 7 : 1;
      else if (e.key === "ArrowLeft") next -= annual ? 7 : 1;
      else if (e.key === "ArrowDown") next += annual ? 1 : cols;
      else if (e.key === "ArrowUp") next -= annual ? 1 : cols;
      else if (e.key === "Home") next = 0;
      else if (e.key === "End") next = calendarDates.length - 1;
      else if (e.key === "Escape") {
        hideTooltip();
        return;
      } else return;
      e.preventDefault();
      next = Math.max(0, Math.min(calendarDates.length - 1, next));
      const target = $(`[data-date="${calendarDates[next]}"]`);
      target.tabIndex = 0;
      button.tabIndex = -1;
      target.focus();
      target.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
    function renderDay() {
      const records = daily.get(state.selected) || [];
      $("#day-title").textContent = dateLabel(state.selected, {
        month: "long",
        day: "numeric",
      });
      $("#day-total").textContent =
        `${fmt(records.length)} ${state.metric === "commit" ? "commits" : "PRs opened"} · ${state.repo === "all" ? "all repositories" : state.repo}`;
      const actor =
        state.actor === "all"
          ? "the selected authors"
          : state.actor === "human"
            ? "Human"
            : "Agent";
      if (!records.length) {
        $("#day-details").innerHTML =
          `<div class="empty-day"><strong>A quiet day in this view.</strong>No ${state.metric === "commit" ? "commits" : "pull requests"} from ${actor} match these filters. Try another day or a wider selection.</div>`;
        return;
      }
      $("#day-details").innerHTML = records
        .map(
          (r) =>
            `<article class="day-item" data-actor="${r.actor}" data-repository="${escape(state.repo === "all" ? r.repository : state.repo)}" data-metric="${r.type}"><div class="entry-meta"><span class="actor-label"><i class="actor-dot ${r.actor}" aria-hidden="true"></i>${r.actor === "human" ? "Human" : "Agent"}</span><span>·</span><span>${escape(state.repo === "all" ? r.repositories.join(" · ") : state.repo)}</span></div><p class="entry-title"><a href="${escape(safeUrl(r.url))}" rel="noopener">${escape(r.title)}</a></p><p class="entry-footer">${r.type === "commit" ? `Commit · +${fmt(r.additions)} / −${fmt(r.deletions)}` : `PR #${r.number} · <span class="entry-state">${r.state === "closed" ? "Closed unmerged" : r.state === "merged" ? "Merged" : "Open"}</span>`}</p></article>`,
        )
        .join("");
    }
    function renderChart(start) {
      const range = state.range;
      const bins = [];
      if (range === 365) {
        for (let m = 0; m < 13; m++) {
          const d = new Date(
            Date.UTC(
              dateAt(end).getUTCFullYear(),
              dateAt(end).getUTCMonth() - 12 + m,
              1,
            ),
          );
          bins.push({
            key: d.toISOString().slice(0, 7),
            label: d.toLocaleDateString("en-US", {
              month: "short",
              timeZone: "UTC",
            }),
          });
        }
      } else {
        dates(start, end).forEach((date) =>
          bins.push({ key: date, label: dateLabel(date, { day: "numeric" }) }),
        );
      }
      const counts = bins.map(
        (b) => selectedRecords.filter((r) => r.date.startsWith(b.key)).length,
      );
      const max = Math.max(...counts, 1);
      $("#chart-title").textContent =
        range === 365 ? "Monthly rhythm" : "Daily rhythm";
      $("#chart-unit").textContent =
        state.metric === "commit" ? "commits" : "PRs opened";
      $("#monthly-bars").style.gridTemplateColumns =
        `repeat(${bins.length}, minmax(0, 1fr))`;
      $("#monthly-bars").innerHTML = bins
        .map(
          (b, i) =>
            `<div class="month-bar" aria-label="${b.key}: ${counts[i]} ${state.metric === "commit" ? "commits" : "PRs opened"}"><span class="bar-value">${counts[i]}</span><div class="bar" style="height:${Math.max(2, (counts[i] / max) * 65)}%" title="${b.key}: ${counts[i]}"></div><span>${range === 30 && i % 3 !== 0 ? "" : b.label}</span></div>`,
        )
        .join("");
    }
    function renderLonger() {
      const commits = data.records.filter(
        (r) =>
          r.type === "commit" &&
          (state.actor === "all" || r.actor === state.actor) &&
          (state.repo === "all" || r.repositories.includes(state.repo)),
      );
      const ytd = sumRecords(
        commits.filter((r) => r.date >= end.slice(0, 4) + "-01-01"),
      );
      const all = sumRecords(commits);
      $("#longer-totals").innerHTML = [
        [end.slice(0, 4) + " year to date", ytd],
        ["All time", all],
      ]
        .map(
          ([label, s]) =>
            `<tr><td>${label}</td><td>${fmt(s.count)}</td><td>+${fmt(s.added)}</td><td>−${fmt(s.deleted)}</td></tr>`,
        )
        .join("");
    }
    function render() {
      hideTooltip();
      const start = shift(end, -state.range + 1);
      base = data.records.filter(
        (r) =>
          r.type === state.metric &&
          (state.actor === "all" || r.actor === state.actor) &&
          (state.repo === "all" || r.repositories.includes(state.repo)),
      );
      selectedRecords = base.filter((r) => r.date >= start && r.date <= end);
      daily = new Map();
      selectedRecords.forEach((r) => {
        if (!daily.has(r.date)) daily.set(r.date, []);
        daily.get(r.date).push(r);
      });
      if (state.selected < start || state.selected > end) state.selected = end;
      renderKpis(start);
      renderCalendar(start);
      renderDay();
      renderChart(start);
      renderLonger();
      document.documentElement.dataset.currentFilter = `${state.actor}/${state.repo}/${state.metric}/${state.range}`;
    }
    document.querySelectorAll('input[name="actor"]').forEach((e) =>
      e.addEventListener("change", () => {
        state.actor = e.value;
        render();
      }),
    );
    document.querySelectorAll('input[name="metric"]').forEach((e) =>
      e.addEventListener("change", () => {
        state.metric = e.value;
        render();
      }),
    );
    $("#repository").addEventListener("change", (e) => {
      state.repo = e.target.value;
      render();
    });
    $("#range").addEventListener("change", (e) => {
      state.range = Number(e.target.value);
      render();
    });
    $("#latest-day").addEventListener("click", () => {
      selectDate(end);
      const target = $(`[data-date="${end}"]`);
      target.focus();
      target.scrollIntoView({ block: "nearest", inline: "nearest" });
    });
    function repositionTooltip() {
      const button = $(".day-cell[aria-describedby='day-tooltip']");
      if (!button) return;
      const rect = button.getBoundingClientRect();
      if (
        (!button.matches(":hover") && document.activeElement !== button) ||
        rect.bottom < 0 ||
        rect.top > innerHeight ||
        rect.right < 0 ||
        rect.left > innerWidth
      )
        hideTooltip();
      else showTooltip(button);
    }
    window.addEventListener("scroll", repositionTooltip, { passive: true });
    $(".calendar-scroll").addEventListener("scroll", repositionTooltip, {
      passive: true,
    });
    const age = Math.max(
      0,
      (Date.now() - Date.parse(data.snapshot.generated_at)) / 3600000,
    );
    $("#snapshot-status").textContent =
      age > 3 ? "Snapshot delayed" : "Public snapshot";
    $("#snapshot-status").dataset.stale = String(age > 3);
    $("#snapshot-date").textContent = data.snapshot.generated_at
      .replace("T", " ")
      .replace("Z", " UTC");
    $("#data-note").textContent =
      `${data.repositories.length} public repositories · ${data.snapshot.id.slice(0, 12)} · Hourly refresh; scan and cache delays are possible.`;
    document.documentElement.dataset.generation = data.snapshot.id;
    $("#load-message").hidden = true;
    $("#activity-content").hidden = false;
    render();
    requestAnimationFrame(() => {
      const scroll = $(".calendar-scroll");
      if (innerWidth < 800) scroll.scrollLeft = scroll.scrollWidth;
    });
  } catch (error) {
    $("#load-message").hidden = false;
    $("#snapshot-status").textContent = "Unavailable";
    $("#snapshot-date").textContent = "Snapshot could not be loaded";
    $("#load-message").innerHTML =
      'Activity is temporarily unavailable. <a href="https://github.com/LeePepe/LeePepe/blob/main/assets/activity-daily.md">Read the last successful daily table ↗</a>';
    $("#activity-content").hidden = true;
  }
})();
