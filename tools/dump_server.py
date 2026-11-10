#!/usr/bin/env python3
"""Показывает конфиг Xray-сервера Amnezia без секретов. Запуск: curl -sL <ссылка> | python3 -"""
import json, subprocess, os
CT = os.environ.get("XRAY_CONTAINER", "amnezia-xray")
SRV = os.environ.get("XRAY_SERVER_JSON", "/opt/amnezia/xray/server.json")
SECRET = {"id", "privateKey", "shortIds", "password", "email", "publicKey", "uuid", "pass", "user"}

def red(o):
    if isinstance(o, dict):
        return {k: ("<скрыто>" if k in SECRET else red(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [red(x) for x in o]
    return o

r = subprocess.run(["docker", "exec", CT, "cat", SRV], capture_output=True, text=True)
if r.returncode:
    print(r.stdout, r.stderr)
else:
    c = json.loads(r.stdout)
    for i in c.get("inbounds", []):
        s = i.get("settings", {})
        if isinstance(s.get("clients"), list):
            s["clients"] = "<%d клиентов, flow: %s>" % (len(s["clients"]), sorted({str(x.get("flow")) for x in s["clients"]}))
    print(json.dumps(red(c), indent=1, ensure_ascii=False))
