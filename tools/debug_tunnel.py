#!/usr/bin/env python3
"""Включает подробный лог Xray-сервера, повторяет тест ключа, показывает логи и возвращает настройки."""
import base64, json, os, re, sqlite3, subprocess, sys, time, zlib

DB = "/opt/vpnbot/bot.db"
CT = os.environ.get("XRAY_CONTAINER", "amnezia-xray")
SRV = os.environ.get("XRAY_SERVER_JSON", "/opt/amnezia/xray/server.json")
HOSTCFG = "/root/xray-debug-server.json"
UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def sh(cmd, inp=None, timeout=60):
    r = subprocess.run(cmd, input=inp, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def dx(args, inp=None):
    return sh(["docker", "exec"] + (["-i"] if inp is not None else []) + [CT] + args, inp)


def clean(t):
    return UUID.sub("<uuid>", t)


def put_server(cfg):
    open(HOSTCFG, "w").write(json.dumps(cfg, indent=4))
    sh(["docker", "cp", HOSTCFG, CT + ":" + SRV])
    sh(["docker", "restart", CT])
    time.sleep(4)


def main():
    db = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
    db.row_factory = sqlite3.Row
    row = db.execute("SELECT config FROM keys WHERE revoked = 0 ORDER BY id DESC LIMIT 1").fetchone()
    raw = row["config"].strip()[len("vpn://"):]
    info = json.loads(zlib.decompress(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))[4:]))
    c = next(x for x in info["containers"] if "xray" in x)
    lc = c["xray"]["last_config"]
    out = next(o for o in (json.loads(lc) if isinstance(lc, str) else lc)["outbounds"] if o.get("protocol") == "vless")

    rc, orig_txt = dx(["cat", SRV])
    orig = json.loads(orig_txt)
    open("/root/xray-server.json.before-debug", "w").write(orig_txt)
    dbg = json.loads(orig_txt)
    dbg["log"] = {"loglevel": "debug", "access": "/tmp/xa.log", "error": "/tmp/xe.log"}
    port = next(i for i in dbg["inbounds"] if i.get("protocol") == "vless")["port"]
    dx(["sh", "-c", "rm -f /tmp/xa.log /tmp/xe.log"])
    put_server(dbg)
    try:
        rc, xp = dx(["sh", "-c", "command -v xray"])
        sh(["docker", "cp", CT + ":" + xp.strip(), "/tmp/xray-test"])
        os.chmod("/tmp/xray-test", 0o755)
        rc, ip = sh(["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", CT])
        o2 = json.loads(json.dumps(out))
        o2["tag"] = "proxy"
        o2["settings"]["vnext"][0]["address"] = ip.strip()
        o2["settings"]["vnext"][0]["port"] = port
        json.dump({"log": {"loglevel": "debug"}, "inbounds": [{"listen": "127.0.0.1", "port": 10998, "protocol": "http"}],
                   "outbounds": [o2]}, open("/tmp/xray-test.json", "w"))
        lg = open("/tmp/xray-test.log", "w")
        pr = subprocess.Popen(["/tmp/xray-test", "run", "-c", "/tmp/xray-test.json"], stdout=lg, stderr=lg)
        time.sleep(3)
        rc, r1 = sh(["curl", "-s", "-m", "12", "-x", "http://127.0.0.1:10998", "http://1.1.1.1/cdn-cgi/trace"])
        print("Результат http-запроса:", " ".join(l for l in r1.splitlines() if l.startswith("ip=")) or "НЕТ ОТВЕТА")
        time.sleep(1)
        pr.kill()
        print("\n==== лог КЛИЕНТА (последние строки) ====")
        print(clean(open("/tmp/xray-test.log").read())[-2500:])
        print("\n==== лог СЕРВЕРА (error) ====")
        print(clean(dx(["sh", "-c", "tail -n 40 /tmp/xe.log 2>&1"])[1])[-3500:])
        print("\n==== лог СЕРВЕРА (access) ====")
        print(clean(dx(["sh", "-c", "tail -n 15 /tmp/xa.log 2>&1"])[1])[-1500:])
    finally:
        put_server(orig)
        for f in ("/tmp/xray-test", "/tmp/xray-test.json", "/tmp/xray-test.log", HOSTCFG):
            try:
                os.remove(f)
            except OSError:
                pass
        print("\nНастройки сервера возвращены, контейнер перезапущен.")


try:
    main()
except Exception as e:
    import traceback
    print("[!!] скрипт упал:", type(e).__name__, e)
    traceback.print_exc()
print("== ГОТОВО (если видишь эту строку, вывод полный)")
