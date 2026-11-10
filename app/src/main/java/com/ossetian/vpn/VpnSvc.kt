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
                val cfg = Keys.buildConfig(parsed.outbound).toString()
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
                Core.set("on")
            } catch (e: Throwable) {
                cleanup()
                val m = e.message ?: e.javaClass.simpleName
                Core.set("off", if (e is KeyError || m.startsWith("Сначала")) m else "Не удалось подключиться. $m")
                stopSelf()
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
