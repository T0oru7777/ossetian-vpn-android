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
                // само приложение (и ядро Xray внутри него) ходит в интернет мимо VPN, иначе будет петля
                try { b.addDisallowedApplication(packageName) } catch (e: Exception) { }
                val f = b.establish() ?: throw Exception("VPN не разрешён системой.")
                pfd = f
                Libv2ray.initCoreEnv(filesDir.absolutePath, "")
                val c = Libv2ray.newCoreController(handler)
                ctrl = c
                c.startLoop(cfg, f.fd)
                val ip = healthCheck(socksPort) ?: throw Exception("NOTUNNEL")
                Core.set("on", "", ip)
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

    /** Делает запрос через туннель и возвращает внешний IP (или null, если интернет через сервер не идёт) */
    private fun healthCheck(socksPort: Int): String? {
        val proxy = java.net.Proxy(java.net.Proxy.Type.SOCKS, java.net.InetSocketAddress("127.0.0.1", socksPort))
        for (i in 0 until 3) {
            try {
                val c = java.net.URL("http://1.1.1.1/cdn-cgi/trace").openConnection(proxy) as java.net.HttpURLConnection
                c.connectTimeout = 5000
                c.readTimeout = 5000
                val body = c.inputStream.bufferedReader().readText()
                c.disconnect()
                val m = Regex("ip=(\\S+)").find(body)
                if (m != null) return m.groupValues[1]
            } catch (e: Exception) { }
            try { Thread.sleep(1000) } catch (e: InterruptedException) { }
        }
        return null
    }

    private fun cleanup() {
        try { ctrl?.stopLoop() } catch (e: Throwable) { }
        ctrl = null
        try { pfd?.close() } catch (e: Throwable) { }
        pfd = null
    }

    private fun stopAll() {
        Thread {
            cleanup()
            Core.set("off")
            stopSelf()
        }.start()
    }

    override fun onRevoke() {
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
