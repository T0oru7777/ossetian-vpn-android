#!/usr/bin/env python3
"""Проверка последнего ключа бота прямо на сервере. Секреты не выводит.
Запуск (на сервере, под root): curl -sL <ссылка на этот файл> | python3 -
"""
import base64, json, os, sqlite3, subprocess, sys, time, zlib

DB = os.environ.get("BOT_DB", "/opt/vpnbot/bot.db")
CT = os.environ.get("XRAY_CONTAINER", "amnezia-xray")
SRV = os.environ.get("XRAY_SERVER_JSON", "/opt/amnezia/xray/server.json")


def sh(cmd, inp=None, timeout=40):
    r = subprocess.run(cmd, input=inp, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def dx(args, inp=None, timeout=40):
    return sh(["docker", "exec"] + (["-i"] if inp is not None else []) + [CT] + args, inp, timeout)


def ok(flag, text):
    print(("  [ОК]  " if flag else "  [!!]  ") + text)
    return flag


def decode(key):
    raw = key.strip()[len("vpn://"):]
    data = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    info = json.loads(zlib.decompress(data[4:]))
    c = next(x for x in info["containers"] if "xray" in x)
    cfg = c["xray"]["last_config"]
    cfg = json.loads(cfg) if isinstance(cfg, str) else cfg
    out = next(o for o in cfg["outbounds"] if o.get("protocol") == "vless")
    return info, out


def main():
    sys.stdout.reconfigure(line_buffering=True)
    print("== 1. Ключ из базы бота")
    try:
        db = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT id, protocol, config, expires_at FROM keys WHERE revoked = 0 ORDER BY id DESC LIMIT 1").fetchone()
    except Exception as e:
        print("  Не смог открыть базу бота:", e); return
    if not row:
        print("  В базе нет ни одного ключа."); return
    exp = row["expires_at"]
    left = (exp - time.time()) / 86400 if exp else 0
    ok(left > 0, "ключ №%s, протокол %s, осталось дней: %.1f" % (row["id"], row["protocol"], left))
    try:
        info, out = decode(row["config"])
    except Exception as e:
        ok(False, "не удалось разобрать ключ (%s: %s). Это не Xray-ключ или он повреждён." % (type(e).__name__, e)); return
    vn = out["settings"]["vnext"][0]
    user = vn["users"][0]
    st = out.get("streamSettings") or {}
    rs = st.get("realitySettings") or {}
    print("  сервер %s:%s, сеть %s, защита %s, flow %s, SNI %s" % (
        vn.get("address") or info.get("hostName"), vn.get("port"), st.get("network"), st.get("security"),
        user.get("flow"), rs.get("serverName")))

    print("== 2. Что на сервере")
    rc, txt = dx(["cat", SRV])
    if rc != 0:
        ok(False, "не смог прочитать конфиг сервера: " + txt[:200]); return
    srv = json.loads(txt)
    inb = next((i for i in srv["inbounds"] if i.get("protocol") == "vless"), srv["inbounds"][0])
    sset = inb.get("settings", {})
    clients = sset.get("clients", [])
    ok(any(c.get("id") == user.get("id") for c in clients), "клиент из ключа есть в конфиге сервера (всего клиентов: %d)" % len(clients))
    rset = (inb.get("streamSettings") or {}).get("realitySettings") or {}
    ok(rs.get("serverName") in (rset.get("serverNames") or []), "SNI ключа совпадает с серверным (%s)" % rset.get("serverNames"))
    ok(rs.get("shortId", "") in (rset.get("shortIds") or []), "shortId ключа совпадает с серверным")
    rc, x = dx(["xray", "x25519", "-i", rset.get("privateKey", "")])
    pub = ""
    for ln in x.splitlines():
        if ln.lower().startswith(("public", "password")):
            pub = ln.split(":", 1)[1].strip()
    if pub:
        ok(pub == rs.get("publicKey"), "публичный ключ в ключе подходит к серверному")
    else:
        print("  (не смог вычислить публичный ключ сервера, пропускаю)")
    print("  порт сервера:", inb.get("port"), "| flow сервера у клиента:", next((c.get("flow") for c in clients if c.get("id") == user.get("id")), None))

    print("== 3. Живой тест на сервере (без вашего провайдера)")
    rc, xp = dx(["sh", "-c", "command -v xray"])
    sh(["docker", "cp", CT + ":" + xp.strip(), "/tmp/xray-test"])
    os.chmod("/tmp/xray-test", 0o755)
    rc, ip = sh(["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}", CT])
    out2 = json.loads(json.dumps(out))
    out2["tag"] = "proxy"
    out2["settings"]["vnext"][0]["address"] = ip.split()[0]
    out2["settings"]["vnext"][0]["port"] = inb.get("port")
    cfg = {"log": {"loglevel": "warning"},
           "inbounds": [{"listen": "127.0.0.1", "port": 10998, "protocol": "http"}],
           "outbounds": [out2]}
    json.dump(cfg, open("/tmp/xray-test.json", "w"))
    lg = open("/tmp/xray-test.log", "w")
    pr = subprocess.Popen(["/tmp/xray-test", "run", "-c", "/tmp/xray-test.json"], stdout=lg, stderr=lg)
    time.sleep(3)
    good = False
    try:
        rc, r1 = sh(["curl", "-s", "-m", "15", "-x", "http://127.0.0.1:10998", "http://1.1.1.1/cdn-cgi/trace"], timeout=25)
        good = "ip=" in r1
        ok(good, "http-запрос через ключ " + ("прошёл: " + " ".join(l for l in r1.splitlines() if l.startswith("ip=")) if good else "НЕ прошёл"))
        rc, r2 = sh(["curl", "-s", "-m", "15", "-x", "http://127.0.0.1:10998", "-o", "/dev/null", "-w", "%{http_code}", "https://www.google.com"], timeout=25)
        ok(r2.strip().startswith(("2", "3")), "https-запрос (google.com) через ключ: код " + r2.strip())
    finally:
        pr.kill()
    if not good:
        print("  лог теста:", open("/tmp/xray-test.log").read()[-600:])
    for f in ("/tmp/xray-test", "/tmp/xray-test.json", "/tmp/xray-test.log"):
        try:
            os.remove(f)
        except OSError:
            pass

    print("== Вывод")
    if good:
        print("  Сам ключ и сервер исправны. Значит, трафик не доходит от вашего устройства до сервера (провайдер/сеть/порт).")
    else:
        print("  Ключ не работает даже на самом сервере: проблема в настройках сервера или клиента (см. пункты [!!] выше).")


try:
    main()
except Exception as e:
    import traceback
    print("  [!!]  скрипт упал:", type(e).__name__, e)
    traceback.print_exc()
finally:
    try:
        dx(["sh", "-c", "kill $(ps | grep '/tmp/t.json' | grep -v grep | awk '{print $1}') 2>/dev/null"])
    except Exception:
        pass
    print("== ГОТОВО (если видишь эту строку, вывод полный)")
