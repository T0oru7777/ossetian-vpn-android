package com.ossetian.vpn

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.Socket
import java.net.URL

/** Состояние соединения, общее для окна и VPN-сервиса (один процесс) */
object Core {
    @Volatile var status = "off"
    @Volatile var error = ""
    @Volatile var since = 0L
    @Volatile var ip = ""
    @Volatile var onChange: (() -> Unit)? = null

    fun set(s: String, e: String = "", exitIp: String = "") {
        status = s
        error = e
        ip = exitIp
        since = if (s == "on") System.currentTimeMillis() else 0L
        onChange?.invoke()
    }
}

object Store {
    private var sp: SharedPreferences? = null

    @Synchronized
    fun init(c: Context) {
        if (sp == null) sp = c.applicationContext.getSharedPreferences("ovpn", Context.MODE_PRIVATE)
    }

    private fun s() = sp!!

    fun keys(): JSONArray = try { JSONArray(s().getString("keys", "[]")) } catch (e: Exception) { JSONArray() }
    private fun saveKeys(a: JSONArray) = s().edit().putString("keys", a.toString()).apply()

    var selected: String
        get() = s().getString("selected", "") ?: ""
        set(v) { s().edit().putString("selected", v).apply() }
    var theme: String
        get() = s().getString("theme", "iryston") ?: "iryston"
        set(v) { s().edit().putString("theme", v).apply() }
    var intro: Boolean
        get() = s().getBoolean("intro", true)
        set(v) { s().edit().putBoolean("intro", v).apply() }

    var splitMode: String
        get() = s().getString("splitMode", "off") ?: "off"
        set(v) { s().edit().putString("splitMode", v).apply() }
    var splitApps: List<String>
        get() = (s().getString("splitApps", "") ?: "").split("\n").filter { it.isNotBlank() }
        set(v) { s().edit().putString("splitApps", v.joinToString("\n")).apply() }

    fun selectedRaw(): String? {
        val a = keys()
        for (i in 0 until a.length()) if (a.getJSONObject(i).optString("id") == selected) return a.getJSONObject(i).optString("raw")
        return null
    }

    @Synchronized
    fun addKey(text: String, nameOverride: String = ""): JSONObject {
        val p = try { Keys.parse(text) } catch (e: KeyError) { return JSONObject().put("ok", false).put("error", e.message) }
        val raw = text.trim()
        val a = keys()
        for (i in 0 until a.length()) {
            val k = a.getJSONObject(i)
            if (k.optString("raw") == raw) { selected = k.optString("id"); return JSONObject().put("ok", true).put("dup", true) }
        }
        val id = java.lang.Long.toString(System.currentTimeMillis(), 36) + (1000 + (Math.random() * 8999).toInt())
        a.put(JSONObject().put("id", id).put("name", nameOverride.ifEmpty { p.name }).put("host", p.host).put("port", p.port).put("raw", raw))
        saveKeys(a)
        if (selected.isEmpty()) selected = id
        return JSONObject().put("ok", true).put("id", id)
    }

    @Synchronized
    fun removeKey(id: String) {
        val a = keys()
        val n = JSONArray()
        for (i in 0 until a.length()) if (a.getJSONObject(i).optString("id") != id) n.put(a.getJSONObject(i))
        saveKeys(n)
        if (selected == id) selected = if (n.length() > 0) n.getJSONObject(0).optString("id") else ""
    }

    private const val INFO_URL = "https://app.48-103-98-164.sslip.io/api/app/info"

    private fun fetchInfo(raw: String): JSONObject? = try {
        val c = URL(INFO_URL).openConnection() as HttpURLConnection
        c.connectTimeout = 6000; c.readTimeout = 8000
        c.requestMethod = "POST"; c.doOutput = true
        c.setRequestProperty("Content-Type", "application/json")
        c.outputStream.use { it.write(JSONObject().put("key", raw).toString().toByteArray()) }
        if (c.responseCode == 200) JSONObject(c.inputStream.bufferedReader().readText()) else null
    } catch (e: Exception) { null }

    private fun tcpPing(host: String, port: Int): Int = try {
        val t = System.nanoTime()
        Socket().use { it.connect(InetSocketAddress(host, port), 2500) }
        ((System.nanoTime() - t) / 1_000_000).toInt().coerceAtLeast(1)
    } catch (e: Exception) { -1 }

    /** Подписка, устройства и пинг каждого сервера; если бот отдаёт дополнительные серверы, они добавляются как ключи. */
    fun refresh() {
        val a = keys()
        val known = HashSet<String>()
        for (i in 0 until a.length()) known.add(a.getJSONObject(i).optString("raw"))
        for (i in 0 until a.length()) {
            val k = a.getJSONObject(i)
            val info = fetchInfo(k.optString("raw"))
            if (info != null) {
                k.put("info", info)
                val sv = info.optJSONArray("servers")
                if (sv != null) for (j in 0 until sv.length()) {
                    val o = sv.optJSONObject(j) ?: continue
                    val key = o.optString("key")
                    if (key.isNotEmpty() && key !in known) { known.add(key); addKey(key, o.optString("name")) }
                }
            }
        }
        val b = keys()
        for (i in 0 until b.length()) {
            val k = b.getJSONObject(i)
            val old = a.optJSONObject(i)
            if (old != null && old.optString("id") == k.optString("id") && old.has("info") && !k.has("info")) k.put("info", old.get("info"))
            k.put("ping", tcpPing(k.optString("host"), k.optInt("port", 443)))
        }
        saveKeys(b)
    }

    fun publicState(): JSONObject {
        val ks = JSONArray()
        val a = keys()
        for (i in 0 until a.length()) {
            val k = a.getJSONObject(i)
            ks.put(JSONObject().put("id", k.optString("id")).put("name", k.optString("name"))
                .put("host", k.optString("host")).put("port", k.optInt("port"))
                .put("info", k.optJSONObject("info") ?: JSONObject.NULL).put("ping", k.optInt("ping", -1)))
        }
        return JSONObject().put("keys", ks).put("selected", selected)
            .put("split", JSONObject().put("mode", splitMode).put("apps", JSONArray(splitApps)))
            .put("settings", JSONObject().put("systemProxy", false).put("intro", intro).put("theme", theme))
            .put("state", JSONObject().put("status", Core.status).put("error", Core.error).put("since", Core.since).put("ip", Core.ip))
    }
}
