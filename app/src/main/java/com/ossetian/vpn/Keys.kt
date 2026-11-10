package com.ossetian.vpn

import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.URI
import java.net.URLDecoder
import java.util.zip.Inflater

class KeyError(msg: String) : Exception(msg)

class Parsed(val name: String, val host: String, val port: Int, val outbound: JSONObject)

object Keys {
    private val LOOPBACK = setOf("", "127.0.0.1", "localhost", "0.0.0.0", "::1")

    private fun b64(s: String): ByteArray {
        val clean = s.filter { !it.isWhitespace() }.trimEnd('=').replace('+', '-').replace('/', '_')
        return Base64.decode(clean, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
    }

    private fun inflate(b: ByteArray, off: Int, nowrap: Boolean): ByteArray? = try {
        val inf = Inflater(nowrap)
        inf.setInput(b, off, b.size - off)
        val out = ByteArrayOutputStream()
        val buf = ByteArray(8192)
        while (!inf.finished()) {
            val n = inf.inflate(buf)
            if (n == 0 && (inf.needsInput() || inf.needsDictionary())) break
            out.write(buf, 0, n)
        }
        inf.end()
        if (out.size() > 0) out.toByteArray() else null
    } catch (e: Exception) {
        null
    }

    private fun inflateAny(b: ByteArray): ByteArray? {
        if (b.size < 6) return null
        return inflate(b, 4, false) ?: inflate(b, 0, false) ?: inflate(b, 4, true)
    }

    private fun parseAmnezia(text: String): Parsed {
        val bad = KeyError("Не удалось расшифровать ключ. Скопируй его из бота целиком.")
        val raw = text.trim().substring(6)
        val data = try { b64(raw) } catch (e: Exception) { throw bad }
        val js = inflateAny(data) ?: throw bad
        val info = try { JSONObject(String(js, Charsets.UTF_8)) } catch (e: Exception) {
            throw KeyError("Ключ повреждён или скопирован не полностью.")
        }
        val containers = info.optJSONArray("containers") ?: JSONArray()
        var xray: JSONObject? = null
        for (i in 0 until containers.length()) {
            val c = containers.optJSONObject(i) ?: continue
            if (c.has("xray")) { xray = c.getJSONObject("xray"); break }
        }
        if (xray == null) throw KeyError("Этот ключ не для Xray (VLESS). Возьми ключ из бота Ossetian VPN.")
        val lc = xray.opt("last_config")
        val cfg = try { if (lc is String) JSONObject(lc) else lc as JSONObject } catch (e: Exception) {
            throw KeyError("Ключ повреждён.")
        }
        val outs = cfg.optJSONArray("outbounds") ?: JSONArray()
        var out: JSONObject? = null
        for (i in 0 until outs.length()) {
            val o = outs.optJSONObject(i) ?: continue
            if (o.optString("protocol") == "vless") { out = o; break }
        }
        if (out == null) throw KeyError("В ключе не найден VLESS-сервер.")
        val vnext = out.getJSONObject("settings").getJSONArray("vnext").getJSONObject(0)
        var addr = vnext.optString("address", "")
        if (addr in LOOPBACK) {
            val h = info.optString("hostName", "")
            if (h.isNotEmpty()) { addr = h; vnext.put("address", h) }
        }
        out.put("tag", "proxy")
        val name = info.optString("description").ifEmpty { info.optString("name") }.ifEmpty { addr }
        return Parsed(name, addr, vnext.optInt("port", 443), out)
    }

    private fun parseVless(text: String): Parsed {
        val u = try { URI(text.trim()) } catch (e: Exception) { throw KeyError("Ссылка vless:// повреждена.") }
        val host = u.host ?: throw KeyError("Ссылка vless:// повреждена.")
        val id = u.userInfo ?: throw KeyError("Ссылка vless:// повреждена.")
        val q = HashMap<String, String>()
        (u.rawQuery ?: "").split("&").filter { it.contains("=") }.forEach {
            val i = it.indexOf("=")
            q[it.substring(0, i)] = URLDecoder.decode(it.substring(i + 1), "UTF-8")
        }
        fun g(k: String, d: String = "") = q[k]?.takeIf { it.isNotEmpty() } ?: d
        val port = if (u.port > 0) u.port else 443
        val net = g("type", "tcp")
        val sec = g("security", "none")
        val stream = JSONObject().put("network", net).put("security", sec)
        if (sec == "reality") {
            stream.put("realitySettings", JSONObject().put("serverName", g("sni")).put("fingerprint", g("fp", "chrome"))
                .put("publicKey", g("pbk")).put("shortId", g("sid")).put("spiderX", g("spx")))
        } else if (sec == "tls") {
            stream.put("tlsSettings", JSONObject().put("serverName", g("sni", host)).put("fingerprint", g("fp", "chrome")))
        }
        if (net == "ws") {
            val ws = JSONObject().put("path", g("path", "/"))
            if (g("host").isNotEmpty()) ws.put("headers", JSONObject().put("Host", g("host")))
            stream.put("wsSettings", ws)
        }
        if (net == "grpc") stream.put("grpcSettings", JSONObject().put("serviceName", g("serviceName")))
        val user = JSONObject().put("id", id).put("encryption", g("encryption", "none"))
        if (g("flow").isNotEmpty()) user.put("flow", g("flow"))
        val out = JSONObject().put("tag", "proxy").put("protocol", "vless")
            .put("settings", JSONObject().put("vnext", JSONArray().put(
                JSONObject().put("address", host).put("port", port).put("users", JSONArray().put(user)))))
            .put("streamSettings", stream)
        val name = (u.fragment ?: "").ifEmpty { host }
        return Parsed(name, host, port, out)
    }

    fun parse(text: String): Parsed {
        val t = text.trim().trim('`', '"', '\'', '«', '»', '<', '>').trim()
        if (t.isEmpty()) throw KeyError("Вставь ключ.")
        val l = t.lowercase()
        val iv = l.indexOf("vpn://")
        val il = l.indexOf("vless://")
        if (iv >= 0 && (il < 0 || iv < il)) {
            val s = t.substring(iv)
            return try {
                parseAmnezia(s)
            } catch (e: KeyError) {
                // в тексте мог быть лишний текст после ключа: пробуем только первое «слово»
                val first = s.split(Regex("\\s+"))[0]
                if (first == s) throw e
                try { parseAmnezia(first) } catch (e2: KeyError) { throw e }
            }
        }
        if (il >= 0) return parseVless(t.substring(il).split(Regex("\\s+"))[0])
        throw KeyError("Ключ должен начинаться с vpn:// или vless://")
    }

    /** Конфиг Xray: весь трафик с VPN-интерфейса (tun) идёт в сервер из ключа */
    fun buildConfig(outbound: JSONObject): JSONObject {
        val sniff = JSONObject().put("enabled", true).put("destOverride", JSONArray().put("http").put("tls"))
        return JSONObject()
            .put("log", JSONObject().put("loglevel", "warning"))
            .put("inbounds", JSONArray()
                .put(JSONObject().put("tag", "tun").put("protocol", "tun")
                    .put("settings", JSONObject().put("name", "xray0").put("MTU", 1500).put("userLevel", 0))
                    .put("sniffing", sniff))
                // локальный SOCKS нужен только самому приложению для проверки, что туннель работает
                .put(JSONObject().put("tag", "socks-in").put("listen", "127.0.0.1").put("port", 10808).put("protocol", "socks")
                    .put("settings", JSONObject().put("udp", false).put("auth", "noauth"))))
            .put("outbounds", JSONArray().put(outbound)
                .put(JSONObject().put("tag", "direct").put("protocol", "freedom"))
                .put(JSONObject().put("tag", "block").put("protocol", "blackhole")))
            .put("routing", JSONObject().put("domainStrategy", "AsIs").put("rules", JSONArray()
                // QUIC (UDP 443) через VLESS+Vision не работает: блокируем, чтобы приложения сразу переходили на TCP
                .put(JSONObject().put("type", "field").put("network", "udp").put("port", "443").put("outboundTag", "block"))))
    }
}
