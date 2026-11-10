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
                "connect" -> ui.post { startVpn() }
                "disconnect" -> ui.post { stopVpn() }
                "addKey" -> { val r = Store.addKey(a.optString("text")); push(); return r.toString() }
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
