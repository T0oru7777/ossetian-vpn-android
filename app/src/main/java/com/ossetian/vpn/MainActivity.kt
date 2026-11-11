package com.ossetian.vpn

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.net.VpnService
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.webkit.JavascriptInterface
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import org.json.JSONObject

class MainActivity : Activity() {
    private lateinit var web: WebView
    private val ui = Handler(Looper.getMainLooper())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Store.init(applicationContext)
        Store.iconId = currentIcon()
        web = WebView(this)
        web.setBackgroundColor(Color.parseColor("#0A1224"))
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = true
            cacheMode = WebSettings.LOAD_NO_CACHE
            setSupportZoom(false)
        }
        web.overScrollMode = WebView.OVER_SCROLL_NEVER
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, url: String?): Boolean = true
        }
        web.addJavascriptInterface(Bridge(), "Android")
        setContentView(web)
        web.loadUrl("file:///android_asset/ui/index.html")
    }

    override fun onResume() {
        super.onResume()
        Core.onChange = { push() }
        push()
    }

    override fun onPause() {
        Core.onChange = null
        super.onPause()
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        moveTaskToBack(true)
    }

    private fun push() {
        val js = "window.__state && window.__state(" + JSONObject.quote(Store.publicState().toString()) + ")"
        ui.post { web.evaluateJavascript(js, null) }
    }

    private fun startVpn() {
        val i = VpnService.prepare(this)
        if (i != null) {
            @Suppress("DEPRECATION")
            startActivityForResult(i, 77)
        } else {
            startService(Intent(this, VpnSvc::class.java).setAction("start"))
        }
    }

    private fun stopVpn() {
        startService(Intent(this, VpnSvc::class.java).setAction("stop"))
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == 77) {
            if (resultCode == RESULT_OK) startVpn()
            else Core.set("off", "Нужно разрешить VPN-подключение, иначе приложение не сможет работать.")
        }
    }

    private val iconIds = listOf("classic", "vpn", "gold", "river", "sun", "orn")
    private fun alias(id: String) = android.content.ComponentName(packageName, "com.ossetian.vpn.Icon" + id.replaceFirstChar { it.uppercase() })

    private fun currentIcon(): String {
        for (id in iconIds) {
            val st = packageManager.getComponentEnabledSetting(alias(id))
            if (st == android.content.pm.PackageManager.COMPONENT_ENABLED_STATE_ENABLED) return id
        }
        return "classic"
    }

    private fun setIcon(id: String) {
        if (id !in iconIds || id == Store.iconId) return
        val pm = packageManager
        // сначала включаем новую, потом выключаем остальные, чтобы значок не пропал
        pm.setComponentEnabledSetting(alias(id), android.content.pm.PackageManager.COMPONENT_ENABLED_STATE_ENABLED, android.content.pm.PackageManager.DONT_KILL_APP)
        for (o in iconIds) if (o != id) pm.setComponentEnabledSetting(alias(o), android.content.pm.PackageManager.COMPONENT_ENABLED_STATE_DISABLED, android.content.pm.PackageManager.DONT_KILL_APP)
        Store.iconId = id
    }

    private fun listApps(): String {
        val pm = packageManager
        val i = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val seen = HashSet<String>()
        val out = org.json.JSONArray()
        val items = pm.queryIntentActivities(i, 0).filter { it.activityInfo.packageName != packageName }
        for (r in items) {
            val p = r.activityInfo.packageName
            if (!seen.add(p)) continue
            try {
                val bmp = android.graphics.Bitmap.createBitmap(96, 96, android.graphics.Bitmap.Config.ARGB_8888)
                val d = r.loadIcon(pm)
                d.setBounds(0, 0, 96, 96); d.draw(android.graphics.Canvas(bmp))
                val bo = java.io.ByteArrayOutputStream()
                bmp.compress(android.graphics.Bitmap.CompressFormat.PNG, 90, bo)
                out.put(JSONObject().put("p", p).put("n", r.loadLabel(pm).toString())
                    .put("i", android.util.Base64.encodeToString(bo.toByteArray(), android.util.Base64.NO_WRAP)))
            } catch (e: Throwable) { }
        }
        return out.toString()
    }

    inner class Bridge {
        @JavascriptInterface
        fun call(id: Int, name: String, arg: String) {
            Thread {
                val res = try { handle(name, JSONObject(if (arg.isEmpty()) "{}" else arg)) } catch (e: Throwable) { "false" }
                ui.post { web.evaluateJavascript("window.__res($id, " + JSONObject.quote(res) + ")", null) }
            }.start()
        }

        private fun handle(name: String, a: JSONObject): String {
            when (name) {
                "get" -> return Store.publicState().toString()
                "apps" -> return listApps()
                "icon" -> { setIcon(a.optString("id")); push() }
                "prefs" -> {
                    if (a.has("autoReconnect")) Store.autoReconnect = a.optBoolean("autoReconnect")
                    if (a.has("connectOnStart")) Store.connectOnStart = a.optBoolean("connectOnStart")
                    if (a.has("refreshMin")) Store.refreshMin = a.optInt("refreshMin")
                    push()
                }
                "split" -> {
                    Store.splitMode = a.optString("mode", "off")
                    val arr = a.optJSONArray("apps")
                    Store.splitApps = (0 until (arr?.length() ?: 0)).map { arr!!.getString(it) }
                    push()
                    if (Core.status == "on") { ui.post { stopVpn() }; ui.postDelayed({ startVpn() }, 900) }
                }
                "refresh" -> { Store.refresh(); push() }
                "connect" -> ui.post { startVpn() }
                "disconnect" -> ui.post { stopVpn() }
                "addKey" -> { val r = Store.addKey(a.optString("text")); push(); if (r.optBoolean("ok")) Thread { Store.refresh(); push() }.start(); return r.toString() }
                "removeKey" -> {
                    if (a.optString("id") == Store.selected && Core.status != "off") ui.post { stopVpn() }
                    Store.removeKey(a.optString("id")); push()
                }
                "selectKey" -> {
                    val was = Core.status == "on"
                    if (was) ui.post { stopVpn() }
                    Store.selected = a.optString("id"); push()
                    if (was) ui.postDelayed({ startVpn() }, 900)
                }
                "settings" -> {
                    if (a.has("theme")) Store.theme = a.getString("theme")
                    if (a.has("intro")) Store.intro = a.getBoolean("intro")
                    push()
                }
                "openLink" -> {
                    val u = a.optString("url")
                    if (u.startsWith("https://t.me/")) ui.post {
                        try { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(u))) } catch (e: Exception) { }
                    }
                }
            }
            return "true"
        }
    }
}
