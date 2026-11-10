package com.ossetian.vpn

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONArray
import org.json.JSONObject

/** Состояние соединения, общее для окна и VPN-сервиса (один процесс) */
object Core {
    @Volatile var status = "off"
    @Volatile var error = ""
    @Volatile var since = 0L
    @Volatile var onChange: (() -> Unit)? = null

    fun set(s: String, e: String = "") {
        status = s
        error = e
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

    fun selectedRaw(): String? {
        val a = keys()
        for (i in 0 until a.length()) if (a.getJSONObject(i).optString("id") == selected) return a.getJSONObject(i).optString("raw")
        return null
    }

    @Synchronized
    fun addKey(text: String): JSONObject {
        val p = try { Keys.parse(text) } catch (e: KeyError) { return JSONObject().put("ok", false).put("error", e.message) }
        val raw = text.trim()
        val a = keys()
        for (i in 0 until a.length()) {
            val k = a.getJSONObject(i)
            if (k.optString("raw") == raw) { selected = k.optString("id"); return JSONObject().put("ok", true).put("dup", true) }
        }
        val id = java.lang.Long.toString(System.currentTimeMillis(), 36) + (1000 + (Math.random() * 8999).toInt())
        a.put(JSONObject().put("id", id).put("name", p.name).put("host", p.host).put("port", p.port).put("raw", raw))
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

    fun publicState(): JSONObject {
        val ks = JSONArray()
        val a = keys()
        for (i in 0 until a.length()) {
            val k = a.getJSONObject(i)
            ks.put(JSONObject().put("id", k.optString("id")).put("name", k.optString("name"))
                .put("host", k.optString("host")).put("port", k.optInt("port")))
        }
        return JSONObject().put("keys", ks).put("selected", selected)
            .put("settings", JSONObject().put("systemProxy", false).put("intro", intro).put("theme", theme))
            .put("state", JSONObject().put("status", Core.status).put("error", Core.error).put("since", Core.since))
    }
}
