(function () {
  "use strict";
  var NS = "http://www.w3.org/2000/svg";
  function el(tag, attrs) {
    var n = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      if (k === "class") n.className = attrs[k];
      else if (k === "text") n.textContent = attrs[k];
      else if (k.slice(0, 2) === "on") n.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    }
    for (var i = 2; i < arguments.length; i++) { var c = arguments[i]; if (c == null || c === false) continue; n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); }
    return n;
  }
  function svg(d) {
    var s = document.createElementNS(NS, "svg");
    s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("fill", "none"); s.setAttribute("stroke", "currentColor");
    s.setAttribute("stroke-width", "1.8"); s.setAttribute("stroke-linecap", "round"); s.setAttribute("stroke-linejoin", "round");
    var p = document.createElementNS(NS, "path"); p.setAttribute("d", d); s.appendChild(p); return s;
  }
  var ICON = {
    home: "M2.5 19.5 9 8.5l3.6 6 2.4-3.4 6.5 8.4H2.5zM9 8.5l1.8 3",
    key: "M14.5 9.5a4 4 0 1 1-1.2-2.8L21 14.5V18h-3v-2h-2v-2h-2l-2.2-2.2M8 8.5h.01",
    help: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM9.5 9.5a2.5 2.5 0 1 1 3.6 2.2c-.7.4-1.1 1-1.1 1.8M12 17h.01",
    power: "M12 3v8M6.3 6.8a8 8 0 1 0 11.4 0",
    x: "M6 6l12 12M18 6L6 18",
    plus: "M12 5v14M5 12h14",
    gear: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 13.5a7.5 7.5 0 0 0 0-3l2-1.5-2-3.4-2.3.9a7.5 7.5 0 0 0-2.6-1.5L14 2.5h-4l-.5 2.5a7.5 7.5 0 0 0-2.6 1.5l-2.3-.9-2 3.4 2 1.5a7.5 7.5 0 0 0 0 3l-2 1.5 2 3.4 2.3-.9a7.5 7.5 0 0 0 2.6 1.5l.5 2.5h4l.5-2.5a7.5 7.5 0 0 0 2.6-1.5l2.3.9 2-3.4-2-1.5z",
    chat: "M4 5h16v11H9l-5 4V5z",
    chev: "M9 6l6 6-6 6"
  };
  var PRESETS = {
    iryston: { name: "Ирыстон", gold: "#e9b949", river: "#5fd0c6", red: "#d8453a", b1: "#1b2a4d", b2: "#101a33", b3: "#0a1224" },
    rassvet: { name: "Рассвет", gold: "#ff9a5c", river: "#ffd36b", red: "#ff5d73", b1: "#3d2140", b2: "#271428", b3: "#1a0e1c" },
    izumrud: { name: "Изумруд", gold: "#6fe3a0", river: "#4fd1c5", red: "#e8715e", b1: "#14383f", b2: "#0c2229", b3: "#06141a" },
    rubin: { name: "Рубин", gold: "#ff7a6b", river: "#f2c94c", red: "#ff3d57", b1: "#3a1626", b2: "#22101a", b3: "#150a10" },
    led: { name: "Лёд", gold: "#8ec5ff", river: "#7ee8fa", red: "#9a86ff", b1: "#162b52", b2: "#0d1a33", b3: "#070f1f" }
  };
  function hexRgb(h) { return [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)]; }
  function mix(a, b, t) { var x = hexRgb(a), y = hexRgb(b); return "#" + [0, 1, 2].map(function (i) { return Math.round(x[i] + (y[i] - x[i]) * t).toString(16).padStart(2, "0"); }).join(""); }
  function applyTheme(name) {
    var p = PRESETS[name] || PRESETS.iryston, st = document.documentElement.style;
    st.setProperty("--gold", p.gold); st.setProperty("--gold-soft", mix(p.gold, "#ffffff", .45)); st.setProperty("--gold-hi", mix(p.gold, "#ffffff", .5)); st.setProperty("--gold-lo", mix(p.gold, "#000000", .1));
    st.setProperty("--gold-rgb", hexRgb(p.gold).join(","));
    st.setProperty("--river", p.river); st.setProperty("--river-rgb", hexRgb(p.river).join(",")); st.setProperty("--river-deep", mix(p.river, "#000000", .4));
    st.setProperty("--red", p.red); st.setProperty("--red-rgb", hexRgb(p.red).join(","));
    st.setProperty("--bg", p.b3); st.setProperty("--bg1", p.b1); st.setProperty("--bg2", p.b2);
    st.setProperty("--panel-rgb", hexRgb(p.b2).join(",")); st.setProperty("--deep-rgb", hexRgb(p.b3).join(","));
  }

  var S = null, tab = "home", prevTab = "home", timer = null;
  var ORDER = ["home", "keys", "help"];
  var TABS = [["home", "Главная", ICON.home], ["keys", "Ключи", ICON.key], ["help", "Помощь", ICON.help]];
  var app = document.getElementById("app"), nav = document.getElementById("tabs"), navInd = null;

  function toast(t) { var o = document.getElementById("toast"); if (o) o.remove(); var n = el("div", { id: "toast", class: "toast", text: t }); document.body.appendChild(n); setTimeout(function () { n.remove(); }, 3200); }
  function banner() {
    var b = el("div", { class: "banner" });
    b.innerHTML = window.SCENE;
    var lay = b.firstChild.children, cn = [null, null, null, "b-far", "b-peak", "b-peak", "b-front", "b-trees", null, null, null, "b-front"];
    for (var i = 3; i <= 11; i++) if (cn[i] && lay[i]) lay[i].setAttribute("class", cn[i]);
    for (var f = 0; f < 7; f++) {
      var fl = el("span", { class: "fly" });
      fl.style.left = (8 + Math.random() * 84).toFixed(0) + "%"; fl.style.top = (38 + Math.random() * 46).toFixed(0) + "%";
      fl.style.animationDelay = (Math.random() * 7).toFixed(1) + "s"; fl.style.animationDuration = (5 + Math.random() * 4).toFixed(1) + "s";
      b.appendChild(fl);
    }
    var eg = el("div", { class: "eagle" });
    eg.innerHTML = '<svg viewBox="0 0 40 16" aria-hidden="true"><path d="M0 7 Q9 -1 20 8 Q31 -1 40 7 Q30 6 20 13 Q10 6 0 7Z" fill="#0a1226"/></svg>';
    b.appendChild(eg);
    b.appendChild(el("div", { class: "title" }, el("div", { class: "eyebrow", text: "Ирыстон" }), el("div", { class: "brand" }, "Ossetian ", el("b", { text: "VPN" }))));
    return b;
  }
  function fmt(ms) { var s = Math.floor(ms / 1000), h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60); s %= 60; return (h ? h + ":" : "") + String(m).padStart(h ? 2 : 1, "0") + ":" + String(s).padStart(2, "0"); }
  function curKey() { return S.keys.filter(function (k) { return k.id === S.selected; })[0]; }

  /* ---------- вкладки ---------- */
  function viewHome() {
    var st = S.state, k = curKey(), on = st.status === "on", busy = st.status === "connecting";
    var btn = el("button", { class: "power" + (on ? " on" : "") + (busy ? " busy" : ""), onclick: function () {
      if (busy) return;
      if (!k) { go("keys"); openAdd(); return; }
      on ? window.vpn.disconnect() : window.vpn.connect();
    } }, svg(ICON.power));
    var timerEl = el("small", { id: "tm", text: on ? "Подключено " + fmt(Date.now() - st.since) + (st.ip ? " · IP " + st.ip : "") : busy ? "Соединяемся…" : k ? "Нажми, чтобы подключиться" : "Сначала добавь ключ" });
    var w = el("div", null, banner(), el("div", { class: "orn" }),
      el("div", { class: "power-wrap" }, btn),
      el("div", { class: "state" }, on ? "Защищено" : busy ? "Подключаем" : "Отключено", timerEl),
      st.error ? el("div", { class: "err", text: st.error }) : null,
      el("button", { class: "glass keycard", onclick: function () { go("keys"); } },
        el("div", { class: "ic" }, svg(ICON.key)),
        el("div", { class: "t" }, el("b", { text: k ? k.name : "Ключ не выбран" }), el("span", { text: k ? k.host + ":" + k.port : "Нажми, чтобы добавить" })),
        svg(ICON.chev)));
    return w;
  }
  function viewKeys() {
    var w = el("div", null, el("div", { class: "h2", text: "Мои ключи" }), el("div", { class: "orn" }));
    if (!S.keys.length) w.appendChild(el("p", { class: "sub", text: "Ключей пока нет. Получи ключ в боте и вставь его сюда." }));
    S.keys.forEach(function (k) {
      w.appendChild(el("div", { class: "glass dev" + (k.id === S.selected ? " sel" : ""), style: "cursor:pointer", onclick: function () { if (k.id !== S.selected) window.vpn.selectKey(k.id); } },
        el("div", { class: "hero-icon" + (k.id === S.selected ? " ok" : ""), style: "width:44px;height:44px;margin:0;flex:none" }, svg(ICON.key)),
        el("div", { class: "t" }, el("b", { text: k.name }), el("span", { text: k.host + ":" + k.port + (k.id === S.selected ? " · выбран" : "") })),
        el("button", { class: "x", title: "Удалить", onclick: function (e) { e.stopPropagation(); window.vpn.removeKey(k.id); } }, svg(ICON.x))));
    });
    w.appendChild(el("button", { class: "btn btn-main", style: "margin-top:14px", onclick: openAdd }, "Добавить ключ"));
    return w;
  }
  function viewHelp() {
    var steps = [["Получи ключ", "Открой бота Ossetian VPN в Telegram и купи или возьми подписку. Бот пришлёт ключ, который начинается с vpn://"],
      ["Скопируй и вставь", "Скопируй ключ целиком, во вкладке «Ключи» нажми «Добавить ключ» и вставь его."],
      ["Подключись", "На главной нажми большую кнопку. Когда появится «Защищено», браузер и другие программы пойдут через VPN."],
      ["Если не работает", "Проверь, что ключ скопирован целиком и подписка не закончилась. Отключись и подключись ещё раз. Если Android спросит разрешение на VPN, нажми «ОК»."]];
    var w = el("div", null, el("div", { class: "h2", text: "Как пользоваться" }), el("div", { class: "orn" }));
    steps.forEach(function (s, i) { w.appendChild(el("div", { class: "glass step" }, el("i", { text: String(i + 1) }), el("div", null, el("b", { text: s[0] }), el("span", { text: s[1] })))); });
    w.appendChild(el("button", { class: "glass row", onclick: function () { window.vpn.openLink("https://t.me/vpnOsset1a_bot"); } },
      el("div", { class: "ic" }, svg(ICON.chat)), el("div", { class: "t" }, el("b", { text: "Открыть бота" }), el("span", { text: "@vpnOsset1a_bot" })), el("div", { class: "chev" }, svg(ICON.chev))));
    w.appendChild(el("button", { class: "glass row", onclick: openSettings }, el("div", { class: "ic" }, svg(ICON.gear)),
      el("div", { class: "t" }, el("b", { text: "Настройки" }), el("span", { text: "Цвета и заставка" })), el("div", { class: "chev" }, svg(ICON.chev))));
    return w;
  }
  var VIEWS = { home: viewHome, keys: viewKeys, help: viewHelp };

  /* ---------- окна ---------- */
  function sheet(content) {
    var bg = el("div", { class: "sheet-bg", onclick: function (e) { if (e.target === bg) bg.remove(); } }, el("div", { class: "glass sheet" }, content));
    document.body.appendChild(bg); return bg;
  }
  function openAdd() {
    var ta = el("textarea", { class: "kin", placeholder: "vpn://… или vless://…", spellcheck: "false" });
    var bg;
    var go_ = el("button", { class: "btn btn-main", onclick: async function () {
      var r = await window.vpn.addKey(ta.value);
      if (r.ok) { bg.remove(); toast(r.dup ? "Такой ключ уже есть" : "Ключ добавлен"); } else toast(r.error);
    } }, "Сохранить");
    bg = sheet(el("div", null, el("h3", { text: "Добавить ключ" }), el("p", { text: "Вставь ключ из бота целиком." }), ta, go_));
    ta.focus();
  }
  function openSettings() {
    var bg;
    var sw = function (title, desc, key) {
      var s = el("div", { class: "sw" + (S.settings[key] ? " on" : "") });
      return el("button", { class: "swrow", style: "width:100%;text-align:left", onclick: function () { var v = !S.settings[key]; S.settings[key] = v; s.classList.toggle("on", v); var o = {}; o[key] = v; window.vpn.setSettings(o); } },
        el("div", null, el("b", { text: title }), el("span", { class: "d", text: desc })), s);
    };
    var themes = el("div", { class: "swatches", style: "display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:0 0 14px" });
    Object.keys(PRESETS).forEach(function (k) {
      var p = PRESETS[k];
      themes.appendChild(el("button", { class: "swatch" + (S.settings.theme === k ? " sel" : ""), onclick: function () {
        window.vpn.setSettings({ theme: k }); applyTheme(k);
        Array.prototype.forEach.call(themes.children, function (c) { c.classList.remove("sel"); }); this.classList.add("sel");
      } }, el("i", { style: "background:linear-gradient(135deg," + p.gold + "," + p.river + ")" }), p.name));
    });
    bg = sheet(el("div", null, el("h3", { text: "Настройки" }), el("p", { text: "Цвета приложения" }), themes,
      sw("Заставка при запуске", "Анимация с горами", "intro"),
      el("button", { class: "btn btn-ghost", style: "margin-top:12px", onclick: function () { bg.remove(); } }, "Готово")));
  }

  /* ---------- рендер ---------- */
  function render(animate) {
    app.textContent = "";
    var v = VIEWS[tab]();
    if (animate) { v.className = (v.className ? v.className + " " : "") + "enter"; v.style.setProperty("--dir", ORDER.indexOf(tab) >= ORDER.indexOf(prevTab) ? 1 : -1); }
    app.appendChild(v);
    syncNav();
    clearInterval(timer);
    if (S.state.status === "on") timer = setInterval(function () { var t = document.getElementById("tm"); if (t) t.textContent = "Подключено " + fmt(Date.now() - S.state.since) + (S.state.ip ? " · IP " + S.state.ip : ""); }, 1000);
  }
  function go(t) { if (t === tab) return; prevTab = tab; tab = t; render(true); }
  function buildNav() {
    navInd = el("span", { class: "tab-ind" }); nav.appendChild(navInd);
    TABS.forEach(function (t) { nav.appendChild(el("button", { class: "tab", "data-tab": t[0], onclick: function () { go(t[0]); } }, svg(t[2]), t[1])); });
  }
  function syncNav(instant) {
    var btns = nav.querySelectorAll(".tab"), on = null;
    for (var i = 0; i < btns.length; i++) { var is = btns[i].getAttribute("data-tab") === tab; btns[i].classList.toggle("on", is); if (is) on = btns[i]; }
    if (!on) return;
    if (instant) navInd.style.transition = "none";
    navInd.style.width = on.offsetWidth + "px"; navInd.style.height = on.offsetHeight + "px";
    navInd.style.transform = "translate(" + on.offsetLeft + "px," + on.offsetTop + "px)";
    if (instant) { void navInd.offsetWidth; navInd.style.transition = ""; }
  }
  function playIntro() {
    document.body.classList.add("introing");
    var holder = document.createElement("div"); holder.innerHTML = window.SCENE;
    var svgEl = holder.firstChild;  // SCENE: статичная картинка из этого файла
    svgEl.setAttribute("class", "world");
    var asp = window.innerWidth / window.innerHeight, wide = asp > 0.9;
    if (wide) { var hh = 440, ww = hh * asp; svgEl.setAttribute("viewBox", (195 - ww / 2).toFixed(1) + " -178 " + ww.toFixed(1) + " " + hh); }
    else svgEl.setAttribute("viewBox", "40 -440 310 702");
    var k = Array.prototype.slice.call(svgEl.children);  // 0 defs, 1 солнце, 2 звёзды, 3 дальние горы, 4 главная вершина, 5 снег, 6 передний план, 7 ёлки, 8 река, 9 блики, 10 земля
    var names = [null, "i-sun", null, "i-far", "i-peak", "i-snow", "i-front", "i-trees", "i-river", "i-flow", "i-base", "i-trees"];
    for (var i = 0; i < names.length; i++) if (names[i] && k[i]) k[i].setAttribute("class", names[i]);
    if (k[8]) k[8].setAttribute("pathLength", "1");
    k[2].setAttribute("opacity", "0");
    var NS = "http://www.w3.org/2000/svg";
    var sky = document.createElementNS(NS, "g");
    sky.innerHTML = '<defs><linearGradient id="iSky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#030714"/><stop offset=".55" stop-color="#101d44"/><stop offset=".88" stop-color="#3b2b52"/><stop offset="1" stop-color="#7a4a4f"/></linearGradient></defs>' +
      '<rect x="-2000" y="-460" width="4400" height="720" fill="url(#iSky)"/>';
    var stars = document.createElementNS(NS, "g");
    for (var n = 0; n < 150; n++) {
      var c = document.createElementNS(NS, "circle");
      c.setAttribute("cx", (-300 + Math.random() * 1000).toFixed(1)); c.setAttribute("cy", (-450 + Math.random() * 520).toFixed(1));
      c.setAttribute("r", (0.5 + Math.random() * 1.1).toFixed(2)); c.setAttribute("fill", "#fff");
      if (n % 4 === 0) { c.setAttribute("class", "i-star"); c.style.animationDelay = (Math.random() * 2.4).toFixed(2) + "s"; } else c.setAttribute("opacity", (0.35 + Math.random() * 0.6).toFixed(2));
      stars.appendChild(c);
    }
    var glint = document.createElementNS(NS, "g");  // вспышка ровно на вершине (172, 64)
    glint.setAttribute("transform", "translate(172,64)");
    glint.innerHTML = '<defs><radialGradient id="iGl"><stop offset="0" stop-color="#fff" stop-opacity=".95"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient></defs>' +
      '<g class="i-glint"><circle r="11" fill="url(#iGl)"/><path d="M0,-17 L1.7,-1.7 L17,0 L1.7,1.7 L0,17 L-1.7,1.7 L-17,0 L-1.7,-1.7Z" fill="#fff"/>' +
      '<path d="M0,-7 L1,-1 L7,0 L1,1 L0,7 L-1,1 L-7,0 L-1,-1Z" fill="#fff" transform="rotate(45)"/></g>';
    if (wide) {  // на широком экране горы растворяются по краям
      var defs = document.createElementNS(NS, "defs");
      defs.innerHTML = '<linearGradient id="iFadeG" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#000"/><stop offset=".22" stop-color="#fff"/><stop offset=".78" stop-color="#fff"/><stop offset="1" stop-color="#000"/></linearGradient>' +
        '<mask id="iFade" maskUnits="userSpaceOnUse" x="-10" y="-100" width="420" height="400"><rect x="-10" y="-100" width="420" height="400" fill="url(#iFadeG)"/></mask>';
      svgEl.insertBefore(defs, svgEl.firstChild);
      var grp = document.createElementNS(NS, "g"); grp.setAttribute("mask", "url(#iFade)");
      svgEl.insertBefore(grp, k[3]);
      for (var q = 3; q <= 11; q++) if (k[q]) grp.appendChild(k[q]);
    }
    svgEl.insertBefore(stars, k[1]); svgEl.insertBefore(sky, stars); svgEl.appendChild(glint);

    var letters = "Ossetian VPN".split(""), brand = el("div", { class: "i-brand" });
    letters.forEach(function (ch, idx) {
      var sp = el("span", { class: idx > 8 ? "gold" : "", text: ch === " " ? "\u00a0" : ch });
      sp.style.animationDelay = (1.9 + idx * 0.07).toFixed(2) + "s"; brand.appendChild(sp);
    });
    var box = el("div", { class: "intro", id: "intro" },
      el("div", { class: "aurora a1" }), el("div", { class: "aurora a2" }), svgEl,
      el("div", { class: "i-title" }, el("div", { class: "i-eyebrow", text: "Ирыстон" }), brand, el("div", { class: "i-orn" }),
        el("div", { class: "i-tag", text: "Свободный интернет из сердца гор" })),
      el("div", { class: "i-skip", text: "НАЖМИ, ЧТОБЫ ПРОПУСТИТЬ" }));
    document.body.appendChild(box);

    var done = false;
    function finish() {
      if (done) return; done = true;
      box.classList.add("out");
      setTimeout(function () {  // интерфейс появляется под тающей заставкой
        document.body.classList.remove("introing");
        var v = document.getElementById("app"); var view = v && v.querySelector(".view");
        if (view) { view.classList.remove("enter"); void view.offsetWidth; view.classList.add("enter"); }
        var nav = document.getElementById("tabs"); if (nav) { nav.classList.remove("rise"); void nav.offsetWidth; nav.classList.add("rise"); }
      }, 160);
      setTimeout(function () { box.remove(); }, 760);
    }
    var t0 = Date.now();
    box.addEventListener("click", function () { if (Date.now() - t0 > 700) finish(); });
    setTimeout(finish, 5200);
  }

  window.addEventListener("resize", function () { syncNav(true); });
  buildNav();
  var first = true;
  window.vpn.onState(function (s) {
    var was = S && S.state.status; S = s; applyTheme(s.settings.theme);
    if (document.querySelector(".sheet-bg")) { if (tab === "keys" || tab === "home") render(false); return; }
    render(false);
  });
  window.vpn.get().then(function (s) {
    S = s; applyTheme(s.settings.theme); render(false); syncNav(true);
    if (s.settings.intro) playIntro();
  });
})();
