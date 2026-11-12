# probar_ia.py — ¿Qué hace SU API cuando la IA falla?  (Unidad III, Sesión 5)
# Programación Distribuida · Facultad de Telemática · Universidad de Colima
#
# Prueba su endpoint con IA en 4 situaciones: la IA funciona, está muy lenta, está caída o responde basura.
# Para lograrlo, se pone el simulador ENTRE su API y la IA (como Toxiproxy en la industria).
#
# Cómo usarlo (Windows, cmd):
#   1. Ventana 1, en la carpeta de SU API:
#        set EXTERNO_URL=http://127.0.0.1:9000
#        (y arranquen su API como siempre: uvicorn ..., node ..., php -S ...)
#   2. Ventana 2, en la carpeta de este archivo (con su prueba.json):
#        python probar_ia.py
#
# En prueba.json, el bloque "externo" dice qué endpoint probar (el kit lo genera):
#   "externo": {"metodo": "POST", "ruta": "/tareas/prioridad", "cuerpo": {"titulo": "Entregar el reporte hoy"}}
#   Si su endpoint pide token, agreguen  "token": "admin"  y el bloque "auth" de la sesión 4.

import json
import os
import sys
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ARCHIVO = sys.argv[1] if len(sys.argv) > 1 else "prueba.json"
try:
    with open(ARCHIVO, encoding="utf-8") as f:
        cfg = json.load(f)
except FileNotFoundError:
    sys.exit(f"No encuentro {ARCHIVO} en esta carpeta. Cópienlo aquí o escriban: python probar_ia.py ruta\\a\\prueba.json")
except json.JSONDecodeError as e:
    sys.exit(f"{ARCHIVO} no es un JSON válido (línea {e.lineno}): revisen comas y comillas.")

BASE = str(cfg.get("base", "http://127.0.0.1:8000")).rstrip("/")
EXT = cfg.get("externo") or {}
if not EXT.get("ruta"):
    sys.exit('En prueba.json falta el bloque "externo" con la ruta de su endpoint con IA (cópienlo del kit).')
METODO = str(EXT.get("metodo", "POST")).upper()
RUTA = "/" + str(EXT["ruta"]).strip("/")
CUERPO = EXT.get("cuerpo")
SIM = str(EXT.get("simulador", "http://127.0.0.1:9000")).rstrip("/")


def pedir(metodo, url, cuerpo=None, token=None, espera=15):
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(cuerpo).encode() if cuerpo is not None else None, method=metodo, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=espera) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except (TimeoutError, OSError) as e:
        if "timed out" in str(e) or isinstance(e, TimeoutError):
            return None, ""
        raise


def control(datos=None):
    req = urllib.request.Request(SIM + "/_control", data=json.dumps(datos).encode() if datos else None,
                                 method="POST" if datos else "GET", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


# 1. El simulador: si no hay uno abierto, lo arrancamos aquí mismo
ia = "simulada"
try:
    ia = "Gemini real" if str(control().get("reenvia_a", "")).startswith("http") else "simulada"
except Exception:
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import simulador
        if os.environ.get("GEMINI_API_KEY"):                  # con clave: en modo "funciona" contesta Gemini de verdad
            simulador.REAL = "https://generativelanguage.googleapis.com"
            ia = "Gemini real"
        simulador.arrancar(int(SIM.rsplit(":", 1)[1]))
        time.sleep(0.3)
    except Exception as e:
        sys.exit(f"No pude arrancar el simulador ({e}). ¿Está simulador.py en esta carpeta?")

# 2. Token, solo si su endpoint lo pide
token = None
if EXT.get("token") in ("admin", "usuario"):
    auth = cfg.get("auth", {})
    cred = auth.get(EXT["token"], {})
    try:
        c, t = pedir("POST", BASE + "/" + str(auth.get("login", "/login")).strip("/"), cred)
        d = json.loads(t)
        token = next((d[k] for k in (auth.get("campo_token", "access_token"), "access_token", "token", "jwt") if k in d), None)
    except Exception:
        token = None
    if not token:
        print("(no pude iniciar sesión con el bloque \"auth\": pruebo sin token)")

print(f"\nProbando {METODO} {BASE}{RUTA}   ·   IA: {ia}\n")
CASOS = [
    ("normal", "funciona", "La IA funciona"),
    ("lento", "lenta", "La IA está muy lenta (20 s)"),
    ("falla_siempre", "caida", "La IA está caída (503)"),
    ("basura", "basura", "La IA responde basura (HTML)"),
]
bien = 0
pasaron_por_simulador = 0
for modo, clave, titulo in CASOS:
    try:
        control({"modo": modo, "segundos": 20, "reiniciar": True})
    except Exception:
        sys.exit(f"No hay simulador en {SIM}.")
    t0 = time.time()
    try:
        c, t = pedir(METODO, BASE + RUTA, CUERPO, token)
    except OSError as e:
        sys.exit(f"No pude conectarme a {BASE}: {e}\n¿Está corriendo su API? ¿En prueba.json \"base\" tiene el puerto correcto?")
    dt = time.time() - t0
    try:
        llamadas = control()["llamadas_recibidas"]
    except Exception:
        llamadas = 0
    pasaron_por_simulador += llamadas > 0
    try:
        cuerpo = json.loads(t)
        es_json = True
    except ValueError:
        cuerpo, es_json = t[:80], False
    resp = f"{c} en {dt:.1f} s" if c else f"nada en {dt:.0f} s"
    if clave == "funciona":
        ok = c is not None and 200 <= c < 300 and es_json
        nota = json.dumps(cuerpo, ensure_ascii=False)[:90] if ok else "debería responder 2xx con el JSON de la IA"
    elif clave == "lenta":
        ok = c in (502, 503, 504) and dt <= 10 and es_json
        nota = "el usuario no se queda esperando" if ok else ("¿tiene timeout la llamada a la IA?" if not c or dt > 10
                                                               else "debería responder 504 (o 502) con un error en JSON")
    else:
        ok = c in (502, 503) and es_json
        nota = (f"mensaje: {json.dumps(cuerpo, ensure_ascii=False)[:80]}" if ok
                else "500 = su código tronó: atrapen el error y respondan 502" if c == 500
                else "debería responder 502 con un error en JSON")
    bien += ok
    print(f" {'[OK]' if ok else '[X ]'} {titulo:30} su API: {resp:14}  {nota}")

try:
    control({"modo": "normal"})
except Exception:
    pass

print(f"\nRESULTADO: {bien} de 4")
if pasaron_por_simulador == 0:
    print("\n>>> ¡Su API no le habló al simulador! Ciérrenla y arránquenla otra vez en una ventana donde antes escribieron:\n"
          "        set EXTERNO_URL=http://127.0.0.1:9000\n"
          "    y revisen que su código lea EXTERNO_URL (la primera línea de la función del kit).")
elif bien == 4:
    print("Su API ya no se cae cuando la IA falla. Ahora corran probar_api.py para el reporte de la tarea.")
