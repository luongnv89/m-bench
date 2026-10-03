/* ==========================================================================
   m-bench — shared render layer for the two landing pages.
   index.html      <body data-page="llm"        data-suites="all,agentic-hard,agentic-all">
   system-one.html <body data-page="system-one" data-suites="system1,phishing-eval">

   Both pages read the same data.json and share these helpers; each page only
   renders the sections its markup provides and only shows the suites its
   data-suites attribute names. Page-local model pickers hide models inside
   that page's rows. Never quote a live-setup number as a model number.
   ========================================================================== */
(function () {
  "use strict";

  const REPO = "https://github.com/luongnv89/m-bench/";
  const NOISE = 8; // pts — differences under this at --samples 2 are ties
  const PAGE = document.body.dataset.page || "llm";
  const PAGE_SUITES = (document.body.dataset.suites || "")
    .split(",").map((s) => s.trim()).filter(Boolean);

  let data = null;
  let activeMachine = 0;
  let sort = { key: "date", dir: "desc" };
  const hiddenModels = new Set();
  let modelNames = [];

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
  // escape, then render `ticks` as inline code (titles in data.json use them)
  const fmt = (s) => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>");
  // directories must go through tree/, files through blob/
  const gh = (p) => REPO + (String(p).endsWith("/") ? "tree/main/" : "blob/main/") + p;
  const machineName = (id) => {
    const m = data.machines.find((x) => x.id === id);
    return m ? m.name : (id || "—");
  };
  const modelVisible = (row) => !hiddenModels.has(row.modelKey || row.model);
  // every row this page owns — the ledger, the strip plot and the derived
  // comparisons are all computed from this pool, never from the whole file
  const pageRows = () => data.results.filter((r) => !PAGE_SUITES.length || PAGE_SUITES.includes(r.suite));

  /* —— nav: two-page switcher + mobile menu —— */
  function initNav() {
    const toggle = $("#nav-toggle");
    const menu = $("#nav-menu");
    if (!toggle || !menu) return;
    const closeMenu = () => {
      menu.classList.remove("open");
      toggle.setAttribute("aria-expanded", "false");
      toggle.textContent = "Menu";
    };
    toggle.addEventListener("click", () => {
      const open = menu.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.textContent = open ? "Close" : "Menu";
    });
    menu.addEventListener("click", (e) => { if (e.target.tagName === "A") closeMenu(); });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && menu.classList.contains("open")) { closeMenu(); toggle.focus(); }
    });
  }

  /* —— copy command —— */
  function initCopy() {
    const btn = $("#copy-cmd");
    const text = $("#cmd-text");
    if (!btn || !text) return;
    btn.addEventListener("click", () => {
      const done = (label) => { btn.textContent = label; setTimeout(() => { btn.textContent = "Copy"; }, 1600); };
      if (!navigator.clipboard) return done("Select it");
      navigator.clipboard.writeText(text.textContent).then(() => done("Copied"), () => done("Select it"));
    });
  }

  /* —— bars: one honest 0–100 axis + the leader's tie band —— */
  function barRow(o) {
    const from = Math.max(0, o.lead - NOISE);
    return `
      <div class="bar-row${o.isLead ? " is-lead" : ""}${o.isBest ? " is-best" : ""}" role="listitem" aria-label="${esc(o.label)}${o.isBest ? " (current best)" : ""}: ${esc(o.value)}. ${esc(o.meta)}">
        <span class="bar-label" aria-hidden="true">${esc(o.label)}${o.isBest ? '<span class="best-tag">BEST</span>' : ""}</span>
        <div class="bar-track" aria-hidden="true">
          <span class="noise-band" style="--from:${from}%;--span:${o.lead - from}%"></span>
          <div class="bar-fill${o.alt ? " alt" : ""}" style="--w:${o.value}%;--d:${o.i * 0.08}s"></div>
        </div>
        <span class="bar-val" aria-hidden="true">${esc(o.value)}</span>
        ${o.showMeta === false ? "" : `<span class="bar-meta" aria-hidden="true">${esc(o.meta)}</span>`}
      </div>`;
  }

  const TICKS = `<div class="ticks">${[0, 25, 50, 75, 100].map((t) => `<span style="--x:${t}%">${t}</span>`).join("")}</div>`;
  const unitName = (u) => (u === "agent" ? "agent score" : u);
  const signed = (d) => (d > 0 ? "+" : d < 0 ? "−" : "±") + Math.abs(d).toFixed(1);
  const where = (r) => [r.harness, r.machine ? machineName(r.machine) : null].filter(Boolean).join(" · ");

  /* —— pairs: one setup measured two ways, everything else equal —— */
  // the report's folder is the campaign; pairing across campaigns would
  // match a run against one from a different day and suite revision
  const campaign = (r) => String(r.report || "").split("/").slice(0, -1).join("/");
  function pairUp(rows, axis, a, b) {
    const keys = ["model", "harness", "machine", "suite", "mode", "thinking"].filter((k) => k !== axis);
    const groups = new Map();
    rows.forEach((r) => {
      const k = keys.map((x) => r[x]).join("|") + "|" + campaign(r);
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(r);
    });
    const out = [];
    groups.forEach((rs) => {
      const A = rs.filter((r) => r[axis] === a), B = rs.filter((r) => r[axis] === b);
      // two runs on one side would make the pairing a guess
      if (A.length === 1 && B.length === 1) out.push({ a: A[0], b: B[0] });
    });
    return out;
  }

  /* —— dumbbell: hollow = first way, filled = second, grouped by suite —— */
  function dumbbells(pairs, o) {
    const bySuite = new Map();
    pairs.forEach((p) => {
      if (!bySuite.has(p.a.suite)) bySuite.set(p.a.suite, []);
      bySuite.get(p.a.suite).push(p);
    });
    return [...bySuite].map(([suite, ps]) => {
      ps.sort((x, y) => (y.b.score - y.a.score) - (x.b.score - x.a.score));
      const unit = unitName(ps[0].a.unit);
      const rows = ps.map((p) => {
        const x = p.a.score, y = p.b.score, d = y - x;
        const lo = Math.min(x, y);
        const tie = Math.abs(d) < NOISE;
        const verdict = tie ? "tie · within noise" : d > 0 ? o.bWins : o.aWins;
        return `
          <div class="db-row" role="listitem">
            <div class="db-label"><a href="${gh(p.a.report)}" rel="noopener">${esc(p.a.model)}</a><small>${esc(where(p.a))}</small></div>
            <div class="db-track">
              <span class="sr-only">${esc(o.aName)} ${x.toFixed(1)}, ${esc(o.bName)} ${y.toFixed(1)} ${esc(unit)}.</span>
              <span class="db-seg" aria-hidden="true" style="--from:${lo}%;--span:${Math.abs(d)}%"></span>
              <i class="dot hollow" aria-hidden="true" style="--x:${x}%"></i>
              <i class="dot${o.bClass ? " " + o.bClass : ""}" aria-hidden="true" style="--x:${y}%"></i>
            </div>
            <div class="db-val${tie ? " tie" : ""}">${signed(d)}<small>${esc(verdict)}</small></div>
          </div>`;
      }).join("");
      return `
        <div class="db-group">
          <div class="db-group-title">${esc(suite)} · ${esc(unit)}</div>
          <div role="list" aria-label="${esc(suite)}, ${esc(unit)}, ${esc(o.aName)} versus ${esc(o.bName)}">${rows}</div>
          <div class="db-axis" aria-hidden="true"><span></span>${TICKS}<span></span></div>
        </div>`;
    }).join("");
  }

  /* —— LLM hero: the real harness spread, not decoration —— */
  function renderHero() {
    const el = $("#gauge-rows");
    if (!el || !data.harnessComparison) return;
    const rows = data.harnessComparison.rows;
    const max = Math.max(...rows.map((r) => r.score));
    const min = Math.min(...rows.map((r) => r.score));
    $("#gauge-score").innerHTML = (max - min).toFixed(1) + '<span class="unit">pt spread</span>';
    const sub = $("#gauge-sub");
    if (sub) sub.textContent = data.harnessComparison.setup;
    el.innerHTML = rows.map((r, i) => `
      <div class="gauge-row${r.score === max ? " top" : ""}">
        <span>${esc(r.harness)}</span>
        <span class="g-track" aria-hidden="true"><span class="g-fill" style="--w:${r.score}%;--d:${0.3 + i * 0.08}s"></span></span>
        <span class="g-val">${r.score.toFixed(1)}</span>
      </div>`).join("");
  }

  /* —— machine tabs (LLM page) —— */
  function selectMachine(i) {
    activeMachine = i;
    renderMachineTabs();
    renderMachinePanel();
    const tab = $("#tab-" + data.machines[i].id);
    if (tab) tab.focus();
  }

  function renderMachineTabs() {
    const el = $("#machine-tabs");
    if (!el) return;
    el.innerHTML = data.machines.map((m, i) => `
      <button class="machine-tab" role="tab" id="tab-${esc(m.id)}"
        aria-selected="${i === activeMachine}" aria-controls="machine-panel"
        tabindex="${i === activeMachine ? 0 : -1}" data-idx="${i}" type="button">
        <span class="tab-name">${esc(m.name)}</span>
        <span class="tab-spec">${esc(m.memory)} · ${esc(m.chip)}</span>
      </button>`).join("");

    $$(".machine-tab", el).forEach((btn) => {
      btn.addEventListener("click", () => selectMachine(Number(btn.dataset.idx)));
      btn.addEventListener("keydown", (e) => {
        const n = data.machines.length;
        const next = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
        if (next) { e.preventDefault(); selectMachine((activeMachine + next + n) % n); }
        if (e.key === "Home") { e.preventDefault(); selectMachine(0); }
        if (e.key === "End") { e.preventDefault(); selectMachine(n - 1); }
      });
    });
  }

  function renderMachinePanel() {
    const panel = $("#machine-panel");
    if (!panel) return;
    const m = data.machines[activeMachine];
    const recs = m.recommendations.map((r, i) => `
      <article class="rec-card${i === 0 ? " primary" : ""}">
        <div class="rec-workload">${esc(r.workload)}</div>
        <div class="rec-score">${esc(r.score)}<small>${esc(r.metric)}</small></div>
        <dl class="rec-pair">
          <div><dt>Harness</dt><dd>${esc(r.harness)}</dd></div>
          <div><dt>Model</dt><dd>${esc(r.model)}</dd></div>
          <div><dt>Thinking</dt><dd>${esc(r.thinking)}</dd></div>
          <div><dt>Serving</dt><dd class="muted" style="font-weight:400;font-size:0.82rem;">${esc(r.serving)}</dd></div>
        </dl>
        ${r.config ? `<div class="rec-config">./bench apply ${esc(r.config)}</div>` : ""}
        <p class="rec-note"><span class="dim">Runner-up · </span>${esc(r.runnerUp)}</p>
        <a class="rec-link" href="${gh(r.report)}" rel="noopener">Read the report →</a>
      </article>`).join("");

    panel.setAttribute("aria-labelledby", "tab-" + m.id);
    panel.innerHTML = `
      <div class="machine-specs">
        <span><strong>CPU</strong> ${esc(m.cpu)}</span>
        <span><strong>Memory</strong> ${esc(m.memory)}</span>
        <span><strong>GPU</strong> ${esc(m.gpu)}</span>
        <span><strong>OS</strong> ${esc(m.os)}</span>
      </div>
      <p class="machine-tagline">${esc(m.tagline)}</p>
      <div class="rec-grid">${recs}</div>`;
  }

  /* —— harness chart (LLM page) —— */
  function renderHarness() {
    const bars = $("#harness-bars");
    if (!bars || !data.harnessComparison) return;
    const h = data.harnessComparison;
    $("#harness-question").textContent = h.question;
    const lead = Math.max(...h.rows.map((r) => r.score));
    bars.innerHTML = h.rows.map((r, i) => barRow({
      i, lead, isLead: r.score === lead, label: r.harness, value: r.score.toFixed(1),
      meta: `solved ${r.solved.toFixed(1)}% · ${r.calls} calls · in-tok ${r.inTok} · ${r.wall}s`,
      showMeta: false, // the panels below chart each of these
    })).join("");
    renderMultiples(h.rows);
    $("#harness-note").innerHTML = esc(h.note) +
      ` <a href="${gh(h.report)}" rel="noopener">Full report →</a>`;
  }

  /* —— small multiples: solved, calls, input tokens, wall —— */
  // "~16k" -> 16000; "—" -> null (not recorded, never a zero bar)
  const parseTok = (s) => {
    const m = String(s == null ? "" : s).match(/([\d.]+)\s*([kKmM]?)/);
    if (!m) return null;
    return parseFloat(m[1]) * ({ k: 1e3, m: 1e6 }[m[2].toLowerCase()] || 1);
  };
  const compact = (n) => (n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e3 ? Math.round(n / 1e3) + "k" : String(Math.round(n)));

  function paintMultiples(el, rows, metrics, nameOf) {
    if (!el) return;
    if (!rows.length) { el.innerHTML = ""; return; }
    el.style.setProperty("--cols", metrics.length);
    el.innerHTML = metrics.map((m) => {
      const vals = rows.map((r) => { const v = m.get(r); return v == null || isNaN(v) ? null : v; });
      const known = vals.filter((v) => v != null);
      const top = m.fixed || Math.max(...known);
      const best = m.hi ? Math.max(...known) : Math.min(...known);
      return `
        <div class="multiple">
          <div class="multiple-title">${esc(m.title)}</div>
          <div class="multiple-sub">${esc(m.sub)}${m.fixed ? "" : " · scaled to max"}</div>
          <div class="m-rows" role="list" aria-label="${esc(m.title)}, ${esc(m.sub)}">
            ${rows.map((r, i) => vals[i] == null ? `
              <div class="m-row" role="listitem"><span class="m-name">${esc(nameOf(r))}</span><span class="m-na">not recorded</span></div>` : `
              <div class="m-row${vals[i] === best && known.length > 1 ? " best" : ""}" role="listitem" aria-label="${esc(nameOf(r))}: ${esc(m.fmt(vals[i]))}">
                <span class="m-name" aria-hidden="true">${esc(nameOf(r))}</span>
                <span class="m-track" aria-hidden="true"><span class="m-fill" style="--w:${(vals[i] / top) * 100}%;--d:${i * 0.06}s"></span></span>
                <span class="m-val" aria-hidden="true">${esc(m.fmt(vals[i]))}</span>
              </div>`).join("")}
          </div>
        </div>`;
    }).join("");
  }

  function renderMultiples(rows) {
    paintMultiples($("#harness-multiples"), rows, [
      { title: "Solved", sub: "% of tasks · higher is better", get: (r) => r.solved, fixed: 100, hi: true, fmt: (v) => v.toFixed(1) + "%" },
      { title: "Tool calls", sub: "mean per task · lower is better", get: (r) => r.calls, fmt: (v) => v.toFixed(1) },
      { title: "Input tokens", sub: "per task · lower is better", get: (r) => parseTok(r.inTok), fmt: (v) => "~" + compact(v) },
      { title: "Wall-clock", sub: "whole suite · lower is better", get: (r) => r.wall, fmt: (v) => v + "s" },
    ], (r) => r.harness);
  }

  /* —— derived comparisons: thinking OFF/ON and isolated/live (LLM page) —— */
  function renderPairs() {
    if (!$("#think-block")) return;
    const rows = pageRows();
    // Pair first, then hide: visibility must not resolve ambiguous candidates.
    const think = pairUp(rows, "thinking", "OFF", "ON").filter((p) => modelVisible(p.a));
    const mode = pairUp(rows, "mode", "isolated", "live").filter((p) => modelVisible(p.a));
    $("#think-block").hidden = think.length < 2;
    $("#mode-block").hidden = mode.length < 2;
    $("#think-dumbbells").innerHTML = "";
    $("#mode-dumbbells").innerHTML = "";
    if (think.length >= 2) {
      $("#think-dumbbells").innerHTML = dumbbells(think, {
        aName: "thinking OFF", bName: "thinking ON", aWins: "OFF better", bWins: "ON better",
      });
    }
    if (mode.length >= 2) {
      $("#mode-dumbbells").innerHTML = dumbbells(mode, {
        aName: "isolated", bName: "live", aWins: "isolated ahead", bWins: "live ahead", bClass: "live",
      });
    }
  }

  /* —— thinking panels (LLM page) —— */
  function renderThinking() {
    const t = data.thinkingTradeoff;
    if (!t || !$("#oneshot-bars")) return;
    $("#oneshot-title").innerHTML = fmt(t.oneShot.title);
    $("#tool-title").innerHTML = fmt(t.toolLoop.title);
    $("#oneshot-delta").textContent = t.oneShot.delta;
    $("#tool-delta").textContent = t.toolLoop.delta;
    $("#oneshot-report").innerHTML = esc(t.oneShot.verdict) +
      ` <a href="${gh(t.oneShot.report)}" rel="noopener">Report →</a>`;
    $("#tool-report").innerHTML = esc(t.toolLoop.verdict) +
      ` <a href="${gh(t.toolLoop.report)}" rel="noopener">Report →</a>`;
    $("#think-lesson").textContent = t.lesson;

    const paint = (rows, root, alt) => {
      const el = $(root);
      if (!el) return;
      const lead = Math.max(...rows.map((r) => r.score));
      el.innerHTML = rows.map((r, i) => barRow({
        i, lead, alt, isLead: r.score === lead, label: r.label, value: r.score,
        meta: "wall " + r.wall + "s" +
          (r.meanTok != null ? " · mean " + r.meanTok + " tok" : "") +
          (r.calls != null ? " · " + r.calls + " calls" : "") +
          (r.truncated ? " · " + r.truncated + " truncated" : ""),
      })).join("");
    };
    paint(t.oneShot.rows, "#oneshot-bars", true);
    paint(t.toolLoop.rows, "#tool-bars", false);
  }

  /* —— System One: typed-decision models behind the standard endpoint —— */
  // solve rate ranks; seconds/question only breaks exact ties
  const bestOf = (rows) => rows.reduce((b, r) =>
    !b || r.score > b.score || (r.score === b.score && r.secPerQ < b.secPerQ) ? r : b, null);

  function renderSystemOneHero() {
    const meta = $("#s1-hero-meta");
    if (!meta || !data.systemOne) return;
    const s = data.systemOne;
    const parts = String(s.setup).split(";")[0].split("·").map((x) => x.trim()).filter(Boolean);
    meta.innerHTML = `<span><strong>${s.rows.length}</strong> models compared</span>` +
      parts.map((p) => `<span>${esc(p)}</span>`).join("");
    const q = $("#s1-hero-question");
    if (q) q.textContent = s.question;

    const board = $("#s1-hero-board");
    if (!board) return;
    const best = bestOf(s.rows);
    // fixed reference: the hero never changes with the page's model picker
    board.innerHTML = s.rows.slice().sort((a, b) =>
      b.score - a.score || a.secPerQ - b.secPerQ).map((r, i) => `
        <div class="board-row${r === best ? " top" : ""}">
          <div class="board-line"><span class="board-name">${esc(r.model)}</span><span class="board-val">${r.score.toFixed(1)}</span></div>
          <span class="board-track" aria-hidden="true"><span class="board-fill" style="--w:${r.score}%;--d:${0.25 + i * 0.06}s"></span></span>
        </div>`).join("");
  }

  function renderSystemOne() {
    const bars = $("#s1-bars");
    if (!bars || !data.systemOne) return;
    const s = data.systemOne;
    const setup = $("#s1-setup");
    if (setup) setup.textContent = s.setup;
    $("#s1-question").textContent = s.question;
    const rows = s.rows.filter(modelVisible);
    const lead = Math.max(...rows.map((r) => r.score));
    // tok/s only means generation speed when the answer is real model output;
    // near-empty answers (0–4 tok) measure fixed latency, so show n/a.
    const best = bestOf(rows);
    const tokPerSec = (r) => (r.outTok >= 10 && r.secPerQ > 0 ? Math.round(r.outTok / r.secPerQ) + " tok/s" : "tok/s n/a");
    bars.innerHTML = rows.length ? rows.map((r, i) => barRow({
      i, lead, isLead: r.score === lead, isBest: r === best, label: r.model, value: r.score.toFixed(1),
      meta: `${r.secPerQ}s/question · ${tokPerSec(r)} · wall ${r.wall}s · ${r.serving} · 95% CI ${r.ci} — ${r.note}`,
    })).join("") : '<p class="chart-note">No models selected. Use Show all above to restore comparisons.</p>';
    paintMultiples($("#s1-multiples"), rows, [
      { title: "Seconds / question", sub: "mean · lower is better", get: (r) => r.secPerQ, fmt: (v) => v + "s" },
      { title: "Output tokens", sub: "per answer · lower is better", get: (r) => r.outTok, fmt: (v) => String(v) },
      { title: "Suite wall-clock", sub: "98 generations · Mercury concurrency 1 · includes quota waits", get: (r) => r.wall, fmt: (v) => v + "s" },
    ], (r) => r.model);
    $("#s1-note").innerHTML = esc(s.note) +
      ` <a href="${gh(s.report)}" rel="noopener">Historical comparison →</a>` +
      (s.latestReport ? ` <a href="${gh(s.latestReport)}" rel="noopener">Mercury results →</a>` : "");

    const r = s.realUseCase;
    if (!r) return;
    $("#s1-real").hidden = false;
    const rSetup = $("#s1r-setup");
    if (rSetup) rSetup.textContent = r.setup;
    $("#s1r-question").textContent = r.question;
    const realRows = r.rows.filter(modelVisible);
    const rLead = Math.max(...realRows.map((x) => x.score));
    const rBest = bestOf(realRows);
    $("#s1r-bars").innerHTML = realRows.length ? realRows.map((x, i) => barRow({
      i, lead: rLead, isLead: x.score === rLead, isBest: x === rBest, label: x.model, value: x.score.toFixed(1),
      meta: `${x.secPerQ}s/email · wall ${x.wall}s · ${x.serving}` +
        (x.ci ? ` · 95% CI ${x.ci}` : "") + ` — ${x.note}`,
    })).join("") : '<p class="chart-note">No models selected. Use Show all above to restore comparisons.</p>';
    paintMultiples($("#s1r-multiples"), realRows, [
      { title: "Seconds / email", sub: "mean · lower is better", get: (x) => x.secPerQ, fmt: (v) => v + "s" },
      { title: "Corpus wall-clock", sub: "16 emails · lower is better", get: (x) => x.wall, fmt: (v) => v + "s" },
    ], (x) => x.model);
    $("#s1r-note").innerHTML = esc(r.note) +
      ` <a href="${gh(r.report)}" rel="noopener">Historical comparison →</a>` +
      (r.latestReport ? ` <a href="${gh(r.latestReport)}" rel="noopener">Mercury results →</a>` : "");
  }

  /* —— ledger filters (both pages, each over its own suites) —— */
  const val = (sel) => { const el = $(sel); return el ? el.value : ""; };

  function fillFilters() {
    const rows = pageRows();
    const uniq = (k) => [...new Set(rows.map((r) => r[k]).filter(Boolean))];
    const fill = (sel, vals, label) => {
      const el = $(sel);
      if (!el) return;
      vals.forEach((v) => {
        const o = document.createElement("option");
        o.value = v;
        o.textContent = label ? label(v) : v;
        el.appendChild(o);
      });
    };
    fill("#f-machine", uniq("machine"), machineName);
    fill("#f-harness", uniq("harness").sort());
    fill("#f-suite", uniq("suite"));
  }

  /* —— model pickers: page-local inventory, shared selection —— */
  function fillModelPickers() {
    const pickers = $$("[data-model-picker]");
    if (!pickers.length) return;
    modelNames = [...new Set(pageRows().map((r) => r.model))].sort();
    pickers.forEach((picker, i) => {
      picker.innerHTML = `
        <summary>Show / hide models · <span class="model-summary"></span></summary>
        <p class="model-help">Applies to this page's charts and ledger rows. Search only narrows this checklist.</p>
        <div class="model-actions">
          <div class="filter-field"><label for="model-search-${i}">Find a model</label>
            <input type="search" id="model-search-${i}" placeholder="Search models" /></div>
          <button type="button" class="filter-reset" data-model-action="show">Show all</button>
          <button type="button" class="filter-reset" data-model-action="hide">Hide all</button>
        </div>
        <div class="model-options" role="group" aria-label="Models to display">
          ${modelNames.map((name) => `<label class="model-choice"><input type="checkbox" data-model="${esc(name)}" checked /><span>${esc(name)}</span></label>`).join("")}
        </div>
        <p class="model-count" aria-live="polite"></p>`;
      $("input[type=search]", picker).addEventListener("input", () => searchModels(picker));
      picker.addEventListener("change", (event) => {
        const input = event.target.closest("input[data-model]");
        if (!input) return;
        if (input.checked) hiddenModels.delete(input.dataset.model);
        else hiddenModels.add(input.dataset.model);
        updateModelVisibility();
      });
      picker.addEventListener("click", (event) => {
        const button = event.target.closest("[data-model-action]");
        if (!button) return;
        hiddenModels.clear();
        if (button.dataset.modelAction === "hide") modelNames.forEach((name) => hiddenModels.add(name));
        updateModelVisibility();
      });
    });
    syncModelPickers();
  }

  function searchModels(picker) {
    const query = $("input[type=search]", picker).value.trim().toLowerCase();
    $$(".model-choice", picker).forEach((label) => {
      label.hidden = !$("input", label).dataset.model.toLowerCase().includes(query);
    });
    syncModelPickers();
  }

  function syncModelPickers() {
    const count = modelNames.length - hiddenModels.size;
    $$("[data-model-picker]").forEach((picker) => {
      $$("input[data-model]", picker).forEach((input) => { input.checked = !hiddenModels.has(input.dataset.model); });
      $(".model-summary", picker).textContent = `${count} / ${modelNames.length} visible`;
      const matches = $$(".model-choice", picker).filter((label) => !label.hidden).length;
      $(".model-count", picker).textContent = `${count} / ${modelNames.length} models shown · ${matches} checklist matches`;
    });
  }

  function updateModelVisibility() {
    syncModelPickers();
    renderResults();
    renderSystemOne();
    renderPairs();
  }

  function sortValue(r, key) {
    if (key === "machine") return machineName(r.machine);
    return r[key] == null ? "" : r[key];
  }

  function filteredResults() {
    const m = val("#f-machine"), h = val("#f-harness"), mode = val("#f-mode"),
          s = val("#f-suite"), th = val("#f-thinking");
    const dir = sort.dir === "asc" ? 1 : -1;
    return pageRows().filter((r) =>
      modelVisible(r) &&
      (!m || r.machine === m) &&
      (!h || r.harness === h) &&
      (!mode || r.mode === mode) &&
      (!s || r.suite === s) &&
      (!th || r.thinking === th || r.thinking === "—")
    ).sort((a, b) => {
      const x = sortValue(a, sort.key), y = sortValue(b, sort.key);
      const c = typeof x === "number" ? x - y : String(x).localeCompare(String(y));
      return c ? c * dir : b.score - a.score;
    });
  }

  function renderResults() {
    const body = $("#results-body");
    if (!body) return;
    const rows = filteredResults();
    const best = {};
    rows.forEach((r) => { best[r.suite] = Math.max(best[r.suite] ?? -Infinity, r.score); });

    $("#results-empty").hidden = rows.length > 0;
    body.innerHTML = rows.map((r) => `
      <tr role="row">
        <td class="mono" role="cell"><span class="col-label">Date</span>${esc(r.date)}</td>
        <td role="cell"><span class="col-label">Machine</span>${esc(machineName(r.machine))}</td>
        <td class="model-cell" role="cell"><span class="col-label">Model</span><a href="${gh(r.report)}" rel="noopener">${esc(r.model)}</a></td>
        <td class="mono" role="cell"><span class="col-label">Harness</span>${esc(r.harness)}</td>
        <td role="cell"><span class="col-label">Mode</span><span class="badge ${esc(r.mode)}">${esc(r.mode)}</span></td>
        <td class="mono" role="cell"><span class="col-label">Think</span>${esc(r.thinking)}</td>
        <td class="mono" role="cell"><span class="col-label">Suite</span>${esc(r.suite)}</td>
        <td class="num score-cell${r.score === best[r.suite] ? " best" : ""}" role="cell"><span class="col-label">Score</span><span class="score-wrap"><span class="s-track" aria-hidden="true"><span class="s-fill" style="--w:${r.score}%"></span></span><span class="s-num">${r.score.toFixed(1)}</span><span class="unit">${esc(r.unit)}</span></span></td>
      </tr>`).join("");
    renderStrip(rows, best);

    $$("#results-table th[data-key]").forEach((th) => {
      if (th.dataset.key === sort.key) th.setAttribute("aria-sort", sort.dir === "asc" ? "ascending" : "descending");
      else th.removeAttribute("aria-sort");
    });
    $("#result-count").textContent =
      rows.length + " of " + pageRows().length + " runs in view · noise " + data.noiseFloor;
  }

  /* —— strip plot: the filtered ledger as dots, one row per suite —— */
  let stripRows = [];
  const NARROW = window.matchMedia("(max-width: 768px)");
  function renderStrip(rows, best) {
    const box = $("#strip");
    if (!box) return;
    box.hidden = rows.length === 0;
    hideTip();
    const count = {};
    rows.forEach((r) => { count[r.suite] = (count[r.suite] || 0) + 1; });
    const suites = Object.keys(count).sort((a, b) => count[b] - count[a] || a.localeCompare(b));
    const LANE = 24;
    // the minimum gap, in points, before two dots share a lane: wide enough
    // that adjacent 24px hit targets (WCAG 2.5.8) never intersect, on phones too
    const GAP = NARROW.matches ? 8 : 4.4;
    stripRows = [];
    $("#strip-rows").innerHTML = suites.map((s) => {
      const rs = rows.filter((r) => r.suite === s).sort((a, b) => a.score - b.score);
      // stack dots that would overlap into lanes (a tiny beeswarm)
      const lanes = [];
      const dots = rs.map((r) => {
        let l = lanes.findIndex((x) => r.score - x >= GAP);
        if (l < 0) { l = lanes.length; lanes.push(r.score); } else lanes[l] = r.score;
        const idx = stripRows.push(r) - 1;
        const cls = (r.score === best[s] ? " best" : r.mode === "live" ? " live" : "");
        return `<button type="button" class="strip-dot${cls}" data-i="${idx}" style="--x:${r.score}%;--y:${6 + l * LANE}px"
          aria-label="${esc(r.model)}, ${esc(where(r))}, ${esc(r.mode)}, thinking ${esc(r.thinking)}: ${r.score.toFixed(1)} ${esc(unitName(r.unit))}"></button>`;
      }).join("");
      const unit = unitName(rs[0].unit);
      return `
        <div class="strip-row" role="group" aria-label="${esc(s)}, ${esc(unit)}">
          <div class="strip-label">${esc(s)}<small>${count[s]} run${count[s] > 1 ? "s" : ""} · ${esc(unit)}</small></div>
          <div class="strip-track" style="--h:${Math.max(1, lanes.length) * LANE + 10}px">${dots}</div>
        </div>`;
    }).join("") + `<div class="strip-row axis" aria-hidden="true"><span></span>${TICKS}</div>`;
  }

  function showTip(btn) {
    const r = stripRows[Number(btn.dataset.i)];
    if (!r) return;
    $$(".strip-dot.on").forEach((d) => d.classList.remove("on"));
    btn.classList.add("on");
    const tip = $("#strip-tip");
    tip.innerHTML = `<strong>${esc(r.model)}</strong>
      <span class="mono">${esc(where(r))} · ${esc(r.mode)} · think ${esc(r.thinking)} · ${esc(r.date)}</span><br />
      <span class="tip-score">${r.score.toFixed(1)}</span> <span class="mono">${esc(unitName(r.unit))} · ${esc(r.suite)}</span>`;
    tip.hidden = false;
    const box = $("#strip").getBoundingClientRect(), b = btn.getBoundingClientRect();
    const left = Math.min(Math.max(8, b.left - box.left - tip.offsetWidth / 2 + b.width / 2), box.width - tip.offsetWidth - 8);
    let top = b.top - box.top - tip.offsetHeight - 10;
    if (top < 4) top = b.bottom - box.top + 10;
    tip.style.left = left + "px";
    tip.style.top = top + "px";
  }
  function hideTip() {
    const tip = $("#strip-tip");
    if (tip) tip.hidden = true;
    $$(".strip-dot.on").forEach((d) => d.classList.remove("on"));
  }

  function resetFilters() {
    ["#f-machine", "#f-harness", "#f-mode", "#f-suite", "#f-thinking"].forEach((s) => {
      const el = $(s);
      if (el) el.value = "";
    });
    hiddenModels.clear();
    $$("[data-model-picker]").forEach((picker) => {
      $("input[type=search]", picker).value = "";
      $$(".model-choice", picker).forEach((label) => { label.hidden = false; });
    });
    updateModelVisibility();
  }

  /* —— campaigns & suites (LLM page) —— */
  function renderCampaigns() {
    const el = $("#campaign-list");
    if (!el) return;
    const list = [...data.campaigns].sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
    el.innerHTML = list.map((c) => `
      <article class="campaign">
        <div class="campaign-date">${esc(c.date)}</div>
        <div class="campaign-q">${esc(c.question)}</div>
        <p class="campaign-a">${esc(c.answer).replace(/^(No\.|Yes\.|Yes,)/, "<strong>$1</strong>")}</p>
        <a class="report-link" href="${gh(c.link)}" rel="noopener">Open campaign →</a>
      </article>`).join("");
  }

  // every page renders the whole suite catalogue, but a suite that belongs to
  // the other page's family is tagged and cross-linked, so the grid never
  // contradicts the copy that says those runs live on their own page
  const SUITE_FAMILY = { system1: "system-one", "phishing-eval": "system-one" };
  const SUITE_PAGE = {
    llm: { href: "index.html", label: "LLM setups" },
    "system-one": { href: "system-one.html", label: "System One" },
  };

  function renderSuites() {
    const el = $("#suite-grid");
    if (!el) return;
    el.innerHTML = data.suites.map((s) => {
      const family = SUITE_FAMILY[s.name] || "llm";
      const foreign = family !== PAGE;
      const chip = foreign
        ? ` <a class="suite-family" href="${SUITE_PAGE[family].href}">${esc(SUITE_PAGE[family].label)} →</a>`
        : "";
      return `
      <div class="suite">
        <div class="suite-name">${esc(s.name)}${chip}</div>
        <div class="suite-tasks">${s.tasks} tasks</div>
        <p class="suite-desc">${esc(s.desc)}</p>
      </div>`;
    }).join("");
  }

  /* —— boot: each page runs only the renderers its markup provides —— */
  const RENDERERS = {
    llm: [renderHero, renderMachineTabs, renderMachinePanel, renderHarness, renderThinking],
    "system-one": [renderSystemOneHero],
  };

  function wire() {
    ["#f-machine", "#f-harness", "#f-mode", "#f-suite", "#f-thinking"].forEach((s) => {
      const el = $(s);
      if (el) el.addEventListener("change", renderResults);
    });
    const reset = $("#f-reset");
    if (reset) reset.addEventListener("click", resetFilters);
    const emptyReset = $("#empty-reset");
    if (emptyReset) emptyReset.addEventListener("click", resetFilters);

    const strip = $("#strip");
    if (strip) {
      strip.addEventListener("mouseover", (e) => { const d = e.target.closest(".strip-dot"); if (d) showTip(d); });
      strip.addEventListener("focusin", (e) => { const d = e.target.closest(".strip-dot"); if (d) showTip(d); });
      strip.addEventListener("click", (e) => { const d = e.target.closest(".strip-dot"); if (d) showTip(d); });
      strip.addEventListener("mouseleave", hideTip);
      strip.addEventListener("focusout", (e) => { if (!strip.contains(e.relatedTarget)) hideTip(); });
      document.addEventListener("keydown", (e) => { if (e.key === "Escape") hideTip(); });
      NARROW.addEventListener("change", renderResults);
    }

    $$("#results-table th[data-key] .sort").forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.parentElement.dataset.key;
        // numbers and dates start high-to-low; text starts A→Z
        const firstDir = key === "score" || key === "date" ? "desc" : "asc";
        sort = sort.key === key
          ? { key, dir: sort.dir === "asc" ? "desc" : "asc" }
          : { key, dir: firstDir };
        renderResults();
      });
    });
  }

  fetch("data.json")
    .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then((json) => {
      data = json;
      const stamp = $("#data-stamp");
      if (stamp) stamp.textContent = "data · " + json.generated;
      (RENDERERS[PAGE] || RENDERERS.llm).forEach((fn) => fn());
      renderSystemOne();
      renderPairs();
      fillFilters();
      fillModelPickers();
      renderResults();
      renderCampaigns();
      renderSuites();
      wire();
      initNav();
      initCopy();
      console.info("m-bench ·", PAGE, "·", pageRows().length, "of", data.results.length, "rows in view");
    })
    .catch((err) => {
      const stamp = $("#data-stamp");
      if (stamp) stamp.textContent = "data · failed to load";
      const box = $("#load-error");
      if (box) {
        box.hidden = false;
        box.textContent = "Could not load data.json (" + err.message + "). Serve this folder over HTTP, not file://, and check the file exists.";
      }
    });
})();
