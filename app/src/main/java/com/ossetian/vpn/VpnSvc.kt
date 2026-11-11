package com.ossetian.vpn

import android.content.Intent
import android.net.VpnService
import android.os.ParcelFileDescriptor
import libv2ray.CoreCallbackHandler
import libv2ray.CoreController
import libv2ray.Libv2ray

class VpnSvc : VpnService() {
    private var pfd: ParcelFileDescriptor? = null
    private var ctrl: CoreController? = null
    private var socksPortNow = 0
    @Volatile private var gen = 0

    private val handler = object : CoreCallbackHandler {
        override fun startup(): Long = 0
        override fun shutdown(): Long = 0
        override fun onEmitStatus(code: Long, msg: String?): Long = 0
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Store.init(applicationContext)
        if (intent?.action == "stop") stopAll() else startAll()
        return START_NOT_STICKY
    }

    private fun startAll() {
        if (Core.status == "on" || Core.status == "connecting") return
        Core.set("connecting")
        Thread {
            try {
                val raw = Store.selectedRaw() ?: throw Exception("Сначала добавь ключ.")
                val parsed = Keys.parse(raw)
                val socksPort = java.net.ServerSocket(0).use { it.localPort }
                socksPortNow = socksPort
                val cfg = Keys.buildConfig(parsed.outbound, socksPort).toString()
                // проверяем, что сервер вообще отвечает (до включения VPN, поэтому напрямую)
                val net = parsed.outbound.optJSONObject("streamSettings")?.optString("network", "tcp") ?: "tcp"
                if (net != "kcp" && net != "mkcp" && net != "quic") {
                    try {
                        java.net.Socket().use { it.connect(java.net.InetSocketAddress(parsed.host, parsed.port), 7000) }
                    } catch (e: Exception) {
                        throw Exception("Сервер ${parsed.host}:${parsed.port} не отвечает. Проверь интернет. Если интернет есть, возможно, закончился срок ключа или сервер недоступен.")
                    }
                }
                val b = Builder()
                    .setSession("Ossetian VPN")
                    .setMtu(1500)
                    .addAddress("172.19.0.1", 30)
                    .addRoute("0.0.0.0", 0)
                    .addDnsServer("1.1.1.1")
                    .addDnsServer("8.8.8.8")
                // раздельная маршрутизация: приложения напрямую или только выбранные через VPN
                val mode = Store.splitMode
                val apps = Store.splitApps.filter { it != packageName }
                if (mode == "only" && apps.isNotEmpty()) {
                    // само приложение не в списке разрешённых, поэтому его трафик (ядро Xray) идёт мимо VPN, петли нет
                    for (p in apps) try { b.addAllowedApplication(p) } catch (e: Exception) { }
                } else {
                    // само приложение (и ядро Xray внутри него) ходит в интернет мимо VPN, иначе будет петля
                    try { b.addDisallowedApplication(packageName) } catch (e: Exception) { }
                    if (mode == "bypass") for (p in apps) try { b.addDisallowedApplication(p) } catch (e: Exception) { }
                }
                val f = b.establish() ?: throw Exception("VPN не разрешён системой.")
                pfd = f
                Libv2ray.initCoreEnv(filesDir.absolutePath, "")
                val c = Libv2ray.newCoreController(handler)
                ctrl = c
                c.startLoop(cfg, f.fd)
                val ip = healthCheck(socksPort) ?: throw Exception("NOTUNNEL")
                Core.set("on", "", ip)
                monitor(++gen)
            } catch (e: Throwable) {
                cleanup()
                val m = e.message ?: e.javaClass.simpleName
                val msg = when {
                    m == "NOTUNNEL" -> "Соединение с сервером есть, но интернет через него не работает. Скорее всего, ключ просрочен или сервер не пропускает трафик. Попробуй другой ключ или напиши в поддержку."
                    e is KeyError || m.startsWith("Сначала") || m.startsWith("Сервер") -> m
                    else -> "Не удалось подключиться. $m"
                }
                Core.set("off", msg)
                stopSelf()
            }
        }.start()
    }

    /**
     * Проверяет, что интернет идёт через туннель. Возвращает внешний IP, пустую строку (ответ получен, но IP неизвестен)
     * или null, если через сервер ничего не проходит.
     */
    private fun healthCheck(socksPort: Int, attempts: Int = 3): String? {
        val proxy = java.net.Proxy(java.net.Proxy.Type.SOCKS, java.net.InetSocketAddress("127.0.0.1", socksPort))
        for (i in 0 until attempts) {
            try {
                val c = java.net.URL("https://1.1.1.1/cdn-cgi/trace").openConnection(proxy) as java.net.HttpURLConnection
                c.connectTimeout = 5000
                c.readTimeout = 5000
                c.instanceFollowRedirects = false
                val body = c.inputStream.bufferedReader().readText()
                c.disconnect()
                val m = Regex("ip=(\\S+)").find(body)
                return m?.groupValues?.get(1) ?: ""
            } catch (e: Exception) {
                // https не вышло: любой ответ по обычному http тоже означает, что туннель работает
                try {
                    val c2 = java.net.URL("http://1.1.1.1/").openConnection(proxy) as java.net.HttpURLConnection
                    c2.connectTimeout = 5000
                    c2.readTimeout = 5000
                    c2.instanceFollowRedirects = false
                    c2.responseCode
                    c2.disconnect()
                    return ""
                } catch (e2: Exception) { }
            }
            try { Thread.sleep(1000) } catch (e: InterruptedException) { }
        }
        return null
    }

    /** Следит за туннелем: обновляет данные по расписанию и переподключает при обрыве. */
    private fun monitor(my: Int) {
        Thread {
            var fails = 0
            var tries = 0
            var lastRefresh = System.currentTimeMillis()
            while (my == gen && Core.status == "on") {
                try { Thread.sleep(15000) } catch (e: InterruptedException) { }
                if (my != gen || Core.status != "on") return@Thread
                val m = Store.refreshMin
                if (m > 0 && System.currentTimeMillis() - lastRefresh >= m * 60000L) {
                    lastRefresh = System.currentTimeMillis()
                    try { Store.refresh() } catch (e: Throwable) { }
                }
                val ok = healthCheck(socksPortNow, 1) != null
                fails = if (ok) 0 else fails + 1
                if (ok) tries = 0
                if (fails >= 2 && Store.autoReconnect) {
                    if (++tries > 5) {
                        cleanup(); Core.set("off", "Связь пропала, и переподключиться не удалось. Проверь интернет и нажми кнопку ещё раз."); stopSelf(); return@Thread
                    }
                    gen++
                    cleanup()
                    Core.set("off")
                    startAll()
                    return@Thread
                }
            }
        }.start()
    }

    private fun cleanup() {
        try { ctrl?.stopLoop() } catch (e: Throwable) { }
        ctrl = null
        try { pfd?.close() } catch (e: Throwable) { }
        pfd = null
    }

    private fun stopAll() {
        gen++
        Thread {
            cleanup()
            Core.set("off")
            stopSelf()
        }.start()
    }

    override fun onRevoke() {
        gen++
        // пользователь выключил VPN в системных настройках
        cleanup()
        Core.set("off")
        super.onRevoke()
    }

    override fun onDestroy() {
        cleanup()
        if (Core.status != "off") Core.set("off")
        super.onDestroy()
    }
}
