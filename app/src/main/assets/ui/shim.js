(function () {
  "use strict";
  var pend = {}, n = 0, cb = null;
  window.__res = function (id, s) { var f = pend[id]; delete pend[id]; if (f) f(JSON.parse(s)); };
  window.__state = function (s) { if (cb) cb(JSON.parse(s)); };
  function call(name, arg) {
    return new Promise(function (res) { var id = ++n; pend[id] = res; window.Android.call(id, name, JSON.stringify(arg || {})); });
  }
  window.vpn = {
    get: function () { return call("get"); },
    refresh: function () { return call("refresh"); },
    apps: function () { return call("apps"); },
    setSplit: function (v) { return call("split", v); },
    setPrefs: function (v) { return call("prefs", v); },
    setIcon: function (id) { return call("icon", { id: id }); },
    connect: function () { return call("connect"); },
    disconnect: function () { return call("disconnect"); },
    addKey: function (t) { return call("addKey", { text: t }); },
    removeKey: function (id) { return call("removeKey", { id: id }); },
    selectKey: function (id) { return call("selectKey", { id: id }); },
    setSettings: function (s) { return call("settings", s); },
    openLink: function (u) { return call("openLink", { url: u }); },
    onState: function (f) { cb = f; }
  };
  document.addEventListener("contextmenu", function (e) { if (!/TEXTAREA|INPUT/.test(e.target.tagName)) e.preventDefault(); });
})();
