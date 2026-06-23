/* Strategy Builder — schema-driven stepped wizard (issues #106, #110-UI, #112-share).
 * Talks to the same-origin /api/strategies endpoints. No framework. */
(function () {
  "use strict";

  var schema = null;          // { fields: [...] }
  var groups = [];            // ordered group names
  var stepIndex = 0;
  var editingId = null;       // null = creating, else editing
  var formState = {};         // key -> value
  var liveId = null;
  var liveSupported = false;  // bot exposes LIVE designation? (stock yes, prediction no)
  var chartInstance = null;   // Chart.js instance for the compare view

  var LIVE_COLOR = "#B8730E"; // amber — LIVE strategy
  var PALETTE = ["#1E5BFF", "#2C7A4B", "#C4302E", "#7A4BC4", "#0E8FB8", "#B8460E"];

  function api(path, opts) {
    return fetch("/api" + path, Object.assign({ headers: { "Content-Type": "application/json" } }, opts))
      .then(function (r) {
        if (!r.ok) return r.json().catch(function () { return {}; }).then(function (b) {
          throw new Error(b.detail || ("HTTP " + r.status));
        });
        return r.status === 204 ? null : r.json();
      });
  }

  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (k === "class") n.className = attrs[k];
      else if (k === "html") n.innerHTML = attrs[k];
      else if (k.slice(0, 2) === "on") n.addEventListener(k.slice(2), attrs[k]);
      else n.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { if (c) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return n;
  }

  // ── modal scaffold (injected once) ───────────────────────────────────────
  function ensureModal() {
    if (document.getElementById("sb-backdrop")) return;
    var backdrop = el("div", { id: "sb-backdrop", onclick: function (e) { if (e.target.id === "sb-backdrop") close(); } });
    backdrop.appendChild(el("div", { id: "sb-modal" }));
    document.body.appendChild(backdrop);
  }

  function open() {
    ensureModal();
    document.getElementById("sb-backdrop").classList.add("open");
    loadList();
  }
  function close() {
    var b = document.getElementById("sb-backdrop");
    if (b) b.classList.remove("open");
  }

  // ── strategies list view ─────────────────────────────────────────────────
  function loadList() {
    Promise.all([
      api("/strategies"),
      api("/live-strategy").then(function (r) { liveSupported = true; return r; }).catch(function () { liveSupported = false; return {}; }),
    ])
      .then(function (res) {
        liveId = (res[1] || {}).live_strategy_id || null;
        renderList(res[0] || []);
      })
      .catch(function (e) { renderError(e.message); });
  }

  function renderList(strategies) {
    var modal = document.getElementById("sb-modal");
    modal.innerHTML = "";
    modal.appendChild(el("header", {}, [
      el("h2", {}, ["Strategies"]),
      el("button", { class: "sb-close", onclick: close }, ["×"]),
    ]));
    var body = el("div", { class: "sb-body" });
    if (!strategies.length) {
      body.appendChild(el("div", { class: "sb-empty" }, ["No strategies yet. Create your first one below."]));
    } else {
      var list = el("div", { class: "sb-list" });
      strategies.forEach(function (s) { list.appendChild(renderRow(s)); });
      body.appendChild(list);
    }
    modal.appendChild(body);
    modal.appendChild(el("div", { class: "sb-footer" }, [
      el("button", { class: "sb-btn", onclick: triggerImport }, ["Import…"]),
      el("button", { class: "sb-btn", onclick: renderCompare }, ["Compare equity"]),
      el("button", { class: "sb-btn", onclick: renderTemplates }, ["Templates"]),
      el("button", { class: "sb-btn primary", onclick: function () { startBuilder(null); } }, ["+ New strategy"]),
    ]));
  }

  // ── starter templates (issue #112) ───────────────────────────────────────
  function renderTemplates() {
    api("/strategies/templates").then(function (tpls) {
      var modal = document.getElementById("sb-modal");
      modal.innerHTML = "";
      modal.appendChild(el("header", {}, [
        el("h2", {}, ["Start from a template"]),
        el("button", { class: "sb-close", onclick: loadList }, ["×"]),
      ]));
      var body = el("div", { class: "sb-body" });
      if (!(tpls && tpls.length)) {
        body.appendChild(el("div", { class: "sb-empty" }, ["No templates available."]));
      } else {
        var list = el("div", { class: "sb-list" });
        tpls.forEach(function (t) {
          var info = el("div", {}, [
            el("div", { class: "sb-name" }, [t.name]),
            el("div", { class: "sb-meta" }, [t.description || ""]),
          ]);
          var use = el("button", { class: "sb-btn primary", onclick: function () {
            startBuilder({ name: t.name, params: t.params });
          } }, ["Use"]);
          list.appendChild(el("div", { class: "sb-row" }, [info, el("div", { class: "sb-row-actions" }, [use])]));
        });
        body.appendChild(list);
      }
      modal.appendChild(body);
      modal.appendChild(el("div", { class: "sb-footer" }, [
        el("button", { class: "sb-btn", onclick: loadList }, ["← Back"]),
      ]));
    }).catch(function (e) { renderError(e.message); });
  }

  // ── equity-curve comparison (issue #107) ─────────────────────────────────
  function renderCompare() {
    api("/strategies").then(function (strategies) {
      return Promise.all(strategies.map(function (s) {
        return api("/strategies/" + s.id + "/equity").then(function (curve) {
          return { strategy: s, curve: curve || [] };
        });
      }));
    }).then(function (series) {
      drawCompare(series);
    }).catch(function (e) { renderError(e.message); });
  }

  function drawCompare(series) {
    var modal = document.getElementById("sb-modal");
    if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
    modal.innerHTML = "";
    modal.appendChild(el("header", {}, [
      el("h2", {}, ["Equity comparison"]),
      el("button", { class: "sb-close", onclick: loadList }, ["×"]),
    ]));
    var body = el("div", { class: "sb-body" });

    var withData = series.filter(function (s) { return s.curve.length > 0; });
    if (!withData.length) {
      body.appendChild(el("div", { class: "sb-empty" }, [
        "No equity data yet. Strategies build a curve as the bot runs cycles.",
      ]));
      modal.appendChild(body);
      modal.appendChild(el("div", { class: "sb-footer" }, [
        el("button", { class: "sb-btn", onclick: loadList }, ["← Back"]),
      ]));
      return;
    }

    var wrap = el("div", { style: "position:relative;height:340px;" });
    var canvas = el("canvas", { id: "sb-equity-canvas" });
    wrap.appendChild(canvas);
    body.appendChild(wrap);
    modal.appendChild(body);
    modal.appendChild(el("div", { class: "sb-footer" }, [
      el("button", { class: "sb-btn", onclick: loadList }, ["← Back"]),
    ]));

    var palIdx = 0;
    var datasets = withData.map(function (s) {
      var isLive = liveId === s.strategy.id;
      var color = isLive ? LIVE_COLOR : PALETTE[palIdx++ % PALETTE.length];
      return {
        label: s.strategy.name + (isLive ? " (LIVE)" : ""),
        data: s.curve.map(function (p, i) { return { x: i, y: p.balance }; }),
        borderColor: color,
        backgroundColor: color,
        borderWidth: isLive ? 3 : 2,
        tension: 0.25,
        pointRadius: 0,
      };
    });

    chartInstance = new window.Chart(canvas.getContext("2d"), {
      type: "line",
      data: { datasets: datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: "nearest", intersect: false },
        plugins: { legend: { labels: { font: { family: "JetBrains Mono, monospace" } } } },
        scales: {
          x: { type: "linear", title: { display: true, text: "cycle" },
               ticks: { font: { family: "JetBrains Mono, monospace" } } },
          y: { title: { display: true, text: "$ balance" },
               ticks: { font: { family: "JetBrains Mono, monospace" } } },
        },
      },
    });
  }

  function renderRow(s) {
    var tags = [];
    if (liveId === s.id) tags.push(el("span", { class: "sb-tag live" }, ["LIVE"]));
    var name = el("div", {}, [
      el("span", { class: "sb-name" }, [s.name]),
    ]);
    tags.forEach(function (t) { name.appendChild(t); });
    var meta = el("div", { class: "sb-meta" }, [s.description || s.id.slice(0, 8)]);

    var actions = el("div", { class: "sb-row-actions" }, [
      el("button", { class: "sb-btn", onclick: function () { startBuilder(s); } }, ["Edit"]),
      liveSupported ? el("button", { class: "sb-btn", onclick: function () { designateLive(s); } }, [liveId === s.id ? "LIVE ✓" : "Go LIVE"]) : null,
      el("button", { class: "sb-btn", onclick: function () { exportStrategy(s); } }, ["Export"]),
      el("button", { class: "sb-btn", onclick: function () { archiveStrategy(s); } }, ["Archive"]),
    ]);
    return el("div", { class: "sb-row" }, [el("div", {}, [name, meta]), actions]);
  }

  function renderError(msg) {
    var modal = document.getElementById("sb-modal");
    modal.innerHTML = "";
    modal.appendChild(el("header", {}, [el("h2", {}, ["Strategies"]), el("button", { class: "sb-close", onclick: close }, ["×"])]));
    modal.appendChild(el("div", { class: "sb-body" }, [el("div", { class: "sb-empty" }, ["Error: " + msg])]));
  }

  // ── builder (stepped wizard) ─────────────────────────────────────────────
  function startBuilder(strategy) {
    editingId = strategy ? strategy.id : null;
    formState = {};
    var ensure = schema ? Promise.resolve() : api("/strategies/schema").then(function (s) {
      schema = s;
      groups = [];
      s.fields.forEach(function (f) { var g = f.group || "Settings"; if (groups.indexOf(g) < 0) groups.push(g); });
    });
    ensure.then(function () {
      formState["__name"] = strategy ? strategy.name : "";
      schema.fields.forEach(function (f) {
        var v = strategy && strategy.params && (f.key in strategy.params) ? strategy.params[f.key] : f.default;
        formState[f.key] = v;
      });
      stepIndex = 0;
      renderStep();
    }).catch(function (e) { renderError(e.message); });
  }

  function fieldsForStep(i) {
    var g = groups[i];
    return schema.fields.filter(function (f) { return (f.group || "Settings") === g; });
  }

  function renderStep() {
    var modal = document.getElementById("sb-modal");
    modal.innerHTML = "";
    modal.appendChild(el("header", {}, [
      el("h2", {}, [editingId ? "Edit strategy" : "New strategy"]),
      el("button", { class: "sb-close", onclick: loadList }, ["×"]),
    ]));

    var body = el("div", { class: "sb-body" });
    var pills = el("div", { class: "sb-steps" });
    groups.forEach(function (g, i) {
      var cls = "sb-step-pill" + (i === stepIndex ? " active" : (i < stepIndex ? " done" : ""));
      pills.appendChild(el("span", { class: cls }, [(i + 1) + ". " + g]));
    });
    body.appendChild(pills);

    if (stepIndex === 0) {
      var nameWrap = el("div", { class: "sb-field" }, [el("label", {}, ["Strategy name"])]);
      var nameInput = el("input", { type: "text", value: formState["__name"] || "" });
      nameInput.addEventListener("input", function () { formState["__name"] = nameInput.value; });
      nameWrap.appendChild(nameInput);
      body.appendChild(nameWrap);
    }

    fieldsForStep(stepIndex).forEach(function (f) { body.appendChild(renderField(f)); });
    modal.appendChild(body);

    var isLast = stepIndex === groups.length - 1;
    modal.appendChild(el("div", { class: "sb-footer" }, [
      el("button", { class: "sb-btn", onclick: stepIndex === 0 ? loadList : prevStep }, [stepIndex === 0 ? "Cancel" : "← Back"]),
      el("button", { class: "sb-btn primary", onclick: isLast ? save : nextStep }, [isLast ? "Save strategy" : "Next →"]),
    ]));
  }

  function renderField(f) {
    var wrap, input;
    var val = formState[f.key];
    if (f.type === "bool") {
      input = el("input", { type: "checkbox" });
      input.checked = !!val;
      input.addEventListener("change", function () { formState[f.key] = input.checked; });
      wrap = el("div", { class: "sb-field sb-bool" }, [input, el("label", {}, [f.label])]);
      if (f.help) wrap.appendChild(el("div", { class: "sb-help" }, [f.help]));
      return wrap;
    }
    wrap = el("div", { class: "sb-field" }, [el("label", {}, [f.label])]);
    if (f.help) wrap.appendChild(el("div", { class: "sb-help" }, [f.help]));
    if (f.type === "select") {
      input = el("select");
      (f.options || []).forEach(function (o) {
        var opt = el("option", { value: o }, [o]);
        if (o === val) opt.selected = true;
        input.appendChild(opt);
      });
      input.addEventListener("change", function () { formState[f.key] = input.value; });
    } else if (f.type === "text") {
      input = el("input", { type: "text", value: val == null ? "" : val });
      input.addEventListener("input", function () { formState[f.key] = input.value; });
    } else { // number | percent
      input = el("input", { type: "number", value: val == null ? "" : val });
      if (f.min != null) input.min = f.min;
      if (f.max != null) input.max = f.max;
      if (f.step != null) input.step = f.step;
      input.addEventListener("input", function () {
        formState[f.key] = input.value === "" ? null : parseFloat(input.value);
      });
      if (f.type === "percent") wrap.appendChild(el("div", { class: "sb-help" }, ["Enter as a fraction (e.g. 0.05 = 5%)."]));
    }
    wrap.appendChild(input);
    return wrap;
  }

  function nextStep() { if (stepIndex < groups.length - 1) { stepIndex++; renderStep(); } }
  function prevStep() { if (stepIndex > 0) { stepIndex--; renderStep(); } }

  function save() {
    var name = (formState["__name"] || "").trim();
    if (!name) { stepIndex = 0; renderStep(); alert("Please give the strategy a name."); return; }
    var params = collectParams();
    var req = editingId
      ? api("/strategies/" + editingId, { method: "PUT", body: JSON.stringify({ name: name, params: params }) })
      : api("/strategies", { method: "POST", body: JSON.stringify({ name: name, params: params }) });
    req.then(loadList).catch(function (e) { alert("Save failed: " + e.message); });
  }

  function collectParams() {
    var out = {};
    schema.fields.forEach(function (f) { out[f.key] = formState[f.key]; });
    return out;
  }

  // ── row actions ──────────────────────────────────────────────────────────
  function designateLive(s) {
    api("/strategies/" + s.id + "/designate-live", { method: "POST", body: "{}" })
      .then(loadList)
      .catch(function (e) {
        if (/confirm/i.test(e.message)) alert("Confirm live trading from the header first, then try again.");
        else alert("Could not set LIVE: " + e.message);
      });
  }
  function archiveStrategy(s) {
    if (!window.confirm("Archive \"" + s.name + "\"?")) return;
    api("/strategies/" + s.id + "/archive", { method: "POST", body: "{}" }).then(loadList).catch(function (e) { alert(e.message); });
  }
  function exportStrategy(s) {
    api("/strategies/" + s.id + "/export").then(function (data) {
      var blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      var a = el("a", { href: URL.createObjectURL(blob), download: s.name.replace(/\s+/g, "_") + ".strategy.json" });
      document.body.appendChild(a); a.click(); a.remove();
    }).catch(function (e) { alert("Export failed: " + e.message); });
  }
  function triggerImport() {
    var inp = el("input", { type: "file", accept: ".json" });
    inp.addEventListener("change", function () {
      var file = inp.files[0]; if (!file) return;
      file.text().then(function (txt) {
        var data = JSON.parse(txt);
        return api("/strategies/import", { method: "POST", body: JSON.stringify({
          name: data.name, description: data.description || "", params: data.params || {},
        }) });
      }).then(loadList).catch(function (e) { alert("Import failed: " + e.message); });
    });
    inp.click();
  }

  // Expose a tiny public API for the dashboard button.
  window.StrategyBuilder = { open: open, close: close };
})();
