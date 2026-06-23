/* First-run setup + license onboarding — Wallstrdev. Same-origin /api calls. */
(function () {
  "use strict";

  var step = 0;
  var state = {
    license_key: "", license_ok: false,
    t212_key: "", t212_secret: "", t212_env: "demo",
    anthropic_key: "", risk_profile: "balanced",
  };
  var STEPS = ["welcome", "license", "broker", "ai", "risk", "done"];

  function api(path, opts) {
    return fetch("/api" + path, Object.assign({ headers: { "Content-Type": "application/json" } }, opts))
      .then(function (r) { return r.json().catch(function () { return {}; }); });
  }

  function el(tag, attrs, kids) {
    var n = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (k === "class") n.className = attrs[k];
      else if (k === "html") n.innerHTML = attrs[k];
      else if (k.slice(0, 2) === "on") n.addEventListener(k.slice(2), attrs[k]);
      else n.setAttribute(k, attrs[k]);
    });
    (kids || []).forEach(function (c) { if (c) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return n;
  }

  function ensureRoot() {
    var r = document.getElementById("wds-setup");
    if (!r) { r = el("div", { id: "wds-setup" }); document.body.appendChild(r); }
    return r;
  }
  function open() { ensureRoot().classList.add("open"); render(); }
  function close() { var r = document.getElementById("wds-setup"); if (r) r.classList.remove("open"); }

  function progress() {
    var bar = el("div", { class: "wds-progress" });
    STEPS.forEach(function (_, i) {
      bar.appendChild(el("i", { class: i === step ? "on" : (i < step ? "done" : "") }));
    });
    return bar;
  }

  function field(label, hint, input) {
    var w = el("div", { class: "wds-field" }, [el("label", {}, [label])]);
    if (hint) w.appendChild(el("p", { class: "hint" }, [hint]));
    w.appendChild(input);
    return w;
  }
  function textInput(key, type, placeholder) {
    var i = el("input", { type: type || "text", value: state[key] || "", placeholder: placeholder || "" });
    i.addEventListener("input", function () { state[key] = i.value; });
    return i;
  }

  function foot(kids) { return el("div", { class: "wds-foot" }, kids); }
  function backBtn() { return el("button", { class: "wds-btn", onclick: prev }, ["← Back"]); }
  function nextBtn(label) { return el("button", { class: "wds-btn primary", onclick: next }, [label || "Continue ", el("span", { class: "arrow" }, ["→"])]); }

  function next() { if (step < STEPS.length - 1) { step++; render(); } }
  function prev() { if (step > 0) { step--; render(); } }

  function render() {
    var root = ensureRoot();
    root.innerHTML = "";
    var card = el("div", { class: "wds-card" });
    card.appendChild(progress());
    ({
      welcome: renderWelcome, license: renderLicense, broker: renderBroker,
      ai: renderAI, risk: renderRisk, done: renderDone,
    })[STEPS[step]](card);
    root.appendChild(card);
  }

  function renderWelcome(card) {
    card.appendChild(el("span", { class: "wds-eyebrow" }, ["Welcome"]));
    card.appendChild(el("h1", {}, ["Let's get you trading."]));
    card.appendChild(el("p", { class: "lede" }, [
      "A few quick steps: activate your license, connect your broker and AI, and pick a risk profile. Takes about a minute.",
    ]));
    card.appendChild(foot([
      el("span", {}, []),
      nextBtn("Get started "),
    ]));
  }

  function renderLicense(card) {
    card.appendChild(el("span", { class: "wds-eyebrow" }, ["Step 1 · License"]));
    card.appendChild(el("h2", {}, ["Activate your license"]));
    card.appendChild(el("p", { class: "lede" }, ["Paste the key from your purchase email. We'll verify it instantly."]));
    var input = textInput("license_key", "text", "WDS-XXXX-XXXX-XXXX");
    card.appendChild(field("License key", "", input));
    var status = el("div", { class: "wds-status" });
    var validateBtn = el("button", { class: "wds-btn", onclick: function () {
      status.className = "wds-status busy"; status.textContent = "Validating…";
      api("/license/activate", { method: "POST", body: JSON.stringify({ key: state.license_key }) })
        .then(function (r) {
          state.license_ok = !!r.valid;
          if (r.valid) { status.className = "wds-status ok"; status.textContent = "✓ License active" + (r.tier ? " (" + r.tier + ")" : ""); }
          else { status.className = "wds-status err"; status.textContent = r.reason || "Invalid license key."; }
          render2(); // refresh footer enable-state
        });
    } }, ["Validate"]);
    card.appendChild(el("div", { style: "display:flex;gap:10px;align-items:center;margin-bottom:6px" }, [validateBtn, status]));
    function render2() {
      foots.innerHTML = "";
      foots.appendChild(backBtn());
      var n = nextBtn();
      if (!state.license_ok) n.disabled = true;
      foots.appendChild(n);
    }
    var foots = foot([]);
    card.appendChild(foots);
    render2();
    card.appendChild(el("button", { class: "wds-skip", style: "margin-top:14px", onclick: next }, ["Skip for now (trial)"]));
  }

  function renderBroker(card) {
    card.appendChild(el("span", { class: "wds-eyebrow" }, ["Step 2 · Broker"]));
    card.appendChild(el("h2", {}, ["Connect Trading212"]));
    card.appendChild(el("p", { class: "lede" }, ["Your keys stay on this machine. Start in Demo (paper money) — switch to Live later."]));
    card.appendChild(field("API key", "", textInput("t212_key", "text", "your Trading212 API key")));
    card.appendChild(field("API secret", "", textInput("t212_secret", "password", "your Trading212 API secret")));
    var env = el("select", {}, [el("option", { value: "demo" }, ["Demo — paper money (recommended)"]), el("option", { value: "live" }, ["Live — real money"])]);
    env.value = state.t212_env; env.addEventListener("change", function () { state.t212_env = env.value; });
    card.appendChild(field("Mode", "", env));
    card.appendChild(foot([backBtn(), nextBtn()]));
  }

  function renderAI(card) {
    card.appendChild(el("span", { class: "wds-eyebrow" }, ["Step 3 · AI"]));
    card.appendChild(el("h2", {}, ["Add your AI provider"]));
    card.appendChild(el("p", { class: "lede" }, ["The bot uses Claude to read the market and generate signals. Paste your Anthropic API key."]));
    card.appendChild(field("Anthropic API key", "", textInput("anthropic_key", "password", "sk-ant-…")));
    card.appendChild(foot([backBtn(), nextBtn()]));
  }

  function renderRisk(card) {
    card.appendChild(el("span", { class: "wds-eyebrow" }, ["Step 4 · Risk"]));
    card.appendChild(el("h2", {}, ["Pick a risk profile"]));
    card.appendChild(el("p", { class: "lede" }, ["Sets your default position size and stops. You can fine-tune any strategy later."]));
    var cards = el("div", { class: "wds-cards" });
    [["cautious", "🛡️", "Cautious", "Small size, tight stops"],
     ["balanced", "⚖️", "Balanced", "Sensible defaults"],
     ["bold", "🚀", "Bold", "Larger size, wider stops"]].forEach(function (r) {
      var c = el("div", { class: "wds-rcard" + (state.risk_profile === r[0] ? " sel" : ""), onclick: function () { state.risk_profile = r[0]; renderRisk2(); } }, [
        el("div", { class: "emoji" }, [r[1]]), el("div", { class: "t" }, [r[2]]), el("div", { class: "d" }, [r[3]]),
      ]);
      cards.appendChild(c);
    });
    card.appendChild(cards);
    function renderRisk2() { render(); }
    card.appendChild(foot([backBtn(), nextBtn()]));
  }

  function renderDone(card) {
    card.appendChild(el("span", { class: "wds-eyebrow" }, ["All set"]));
    card.appendChild(el("h1", {}, ["You're ready."]));
    card.appendChild(el("p", { class: "lede" }, [
      "Build or pick a strategy from the Strategies panel, then start the bot. It'll trade per your rules and report back here.",
    ]));
    var finish = el("button", { class: "wds-btn primary", onclick: function () {
      finish.disabled = true; finish.textContent = "Saving…";
      api("/setup/save", { method: "POST", body: JSON.stringify({
        t212_key: state.t212_key, t212_secret: state.t212_secret, t212_env: state.t212_env,
        anthropic_key: state.anthropic_key, risk_profile: state.risk_profile,
      }) }).then(function () { close(); });
    } }, ["Finish & open dashboard ", el("span", { class: "arrow" }, ["→"])]);
    card.appendChild(foot([backBtn(), finish]));
  }

  // Auto-open on first run.
  function maybeOpen() {
    api("/setup/status").then(function (s) { if (s && s.complete === false) open(); }).catch(function () {});
  }

  window.WallstrdevSetup = { open: open, close: close };
  if (document.readyState !== "loading") maybeOpen();
  else document.addEventListener("DOMContentLoaded", maybeOpen);
})();
