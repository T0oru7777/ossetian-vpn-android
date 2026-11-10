#!/usr/bin/env python3
"""Переключает Xray-сервер Amnezia с xhttp на обычный tcp+Reality (под ключи бота).
Делает резервную копию, проверяет конфиг, перезапускает контейнер."""
import json, os, subprocess, sys, time

CT = os.environ.get("XRAY_CONTAINER", "amnezia-xray")
SRV = os.environ.get("XRAY_SERVER_JSON", "/opt/amnezia/xray/server.json")
BAK = "/root/xray-server.json.bak-" + time.strftime("%Y%m%d-%H%M%S")
TMP = "/root/xray-server.json.new"


def run(*a):
    return subprocess.run(list(a), capture_output=True, text=True)


r = run("docker", "exec", CT, "cat", SRV)
if r.returncode:
    sys.exit("Не смог прочитать конфиг: " + r.stdout + r.stderr)
open(BAK, "w").write(r.stdout)
print("Резервная копия:", BAK)

c = json.loads(r.stdout)
changed = False
for i in c["inbounds"]:
    if i.get("protocol") != "vless":
        continue
    ss = i.setdefault("streamSettings", {})
    if ss.get("network") != "tcp":
        ss["network"] = "tcp"
        changed = True
    if "xhttpSettings" in ss:
        del ss["xhttpSettings"]
        changed = True
    # клиентам без flow (созданным под xhttp) ставим vision, как у клиентов бота
    for cl in i["settings"].get("clients", []):
        if not cl.get("flow"):
            cl["flow"] = "xtls-rprx-vision"
            changed = True
if not changed:
    sys.exit("Сервер уже на tcp, менять нечего.")

open(TMP, "w").write(json.dumps(c, indent=4))
t = run("docker", "cp", TMP, CT + ":/tmp/server.json.new")
t = run("docker", "exec", CT, "xray", "run", "-test", "-c", "/tmp/server.json.new")
print("Проверка нового конфига:", "ОК" if t.returncode == 0 else "ОШИБКА\n" + t.stdout + t.stderr)
if t.returncode:
    sys.exit("Ничего не изменено.")
run("docker", "cp", TMP, CT + ":" + SRV)
run("docker", "restart", CT)
time.sleep(3)
print(run("docker", "ps", "--filter", "name=" + CT, "--format", "{{.Names}}  {{.Status}}").stdout.strip())
os.remove(TMP)
print("Готово: сервер переключён на tcp. Вернуть как было: docker cp %s %s:%s && docker restart %s" % (BAK, CT, SRV, CT))
