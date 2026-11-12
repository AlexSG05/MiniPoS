# simulador.py — Simulador de servicio externo (Unidad III, Sesión 5)
# Programación Distribuida · Facultad de Telemática · Universidad de Colima
#
# Se pone ENTRE su API y el servicio externo (API pública o IA) y puede fallar a propósito.
# En la industria se usan herramientas así (por ejemplo Toxiproxy) para probar qué hace
# una API cuando el servicio del que depende tarda, se cae o responde algo raro.
#
#   python simulador.py                         -> puerto 9000, respuestas simuladas
#   python simulador.py https://api.ejemplo.com -> reenvía cada petición a esa API real
#
# Su API debe leer la dirección del servicio externo de una variable de entorno:
#   set EXTERNO_URL=http://127.0.0.1:9000      (para probar con el simulador)
#
# Control (lo usa probar_api.py y las slides):
#   POST /_control  {"modo": "normal" | "lento" | "falla_una" | "falla_siempre" | "429_una"
#                            | "error_400" | "basura" | "pierde_respuesta", "reiniciar": true}
#   GET  /_control  -> modo actual, llamadas recibidas y correos enviados
#
# Servicio de correo simulado (ticket INT-401):
#   POST /correos  {"para": "...", "asunto": "...", "texto": "..."}
#   Con el encabezado Idempotency-Key, si la misma llave llega dos veces, NO manda otro correo.

import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PUERTO = int(os.environ.get("SIMULADOR_PUERTO", "9000"))
REAL = (sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].startswith("http") else os.environ.get("SIMULADOR_REAL", "")).rstrip("/")
ESTADO = {"modo": "normal", "segundos": 20, "llamadas": [], "correos": [], "llaves": {}, "fallo_hecho": False}
CANDADO = threading.Lock()
MODOS = ("normal", "lento", "falla_una", "falla_siempre", "429_una", "error_400", "basura", "pierde_respuesta")


GRAVES = ("quemad", "humo", "chispa", "no enciende", "descarga", "huele", "urgente", "hoy mismo")


def forma_pedida(texto):
    """Busca en la instrucción la forma del JSON que se le pidió a la IA, por ejemplo
    {"prioridad": "alta" | "media" | "baja", "razon": "máximo 20 palabras"}, y regresa sus campos."""
    m = re.search(r"\{[^{}]*\}", texto)
    if not m:
        return []
    campos = []
    for clave, valores in re.findall(r'"([\w]+)"\s*:\s*("[^"]*"(?:\s*\|\s*"[^"]*")*)', m.group(0)):
        campos.append((clave, re.findall(r'"([^"]*)"', valores)))
    return campos


def respuesta_simulada(ruta, cuerpo):
    """Lo que respondería el servicio si no hay uno real configurado."""
    if ":generatecontent" in ruta.lower():               # formato de la API de Gemini
        texto = ""
        try:
            texto = json.loads(cuerpo or b"{}")["contents"][0]["parts"][0]["text"]
        except Exception:
            pass
        dato = texto.rsplit("\n", 1)[-1].lower()          # el dato del usuario va en la última línea
        grave = any(p in dato for p in GRAVES)
        campos = forma_pedida(texto)
        if campos:                                        # responde con la forma que pidió la instrucción
            datos = {}
            for clave, opciones in campos:
                if len(opciones) > 1:                     # "alta" | "media" | "baja": elige una opción
                    datos[clave] = opciones[0] if grave or len(opciones) < 3 else opciones[len(opciones) // 2]
                else:
                    datos[clave] = "Respuesta simulada: así contestaría la IA (" + clave + ")."
        else:
            datos = {"gravedad": "alta" if grave else "media",
                     "resumen": "Posible daño eléctrico; retirar el equipo de uso." if grave else "Falla menor; revisar en el laboratorio."}
        if "gravedad" in datos and "resumen" in datos and len(datos) == 2:
            datos["resumen"] = ("Posible daño eléctrico; retirar el equipo de uso." if grave
                                else "Falla menor; revisar en el laboratorio.")
        return 200, {"candidates": [{"content": {"parts": [{"text": json.dumps(datos, ensure_ascii=False)}], "role": "model"},
                                     "finishReason": "STOP"}], "simulado": True}
    return 200, {"ok": True, "simulado": True, "ruta": ruta}


class Manejador(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def enviar(self, codigo, obj, extra=None, crudo=None):
        datos = crudo if crudo is not None else json.dumps(obj, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8" if crudo is None else "text/html")
            self.send_header("Content-Length", str(len(datos)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(datos)
        except (BrokenPipeError, ConnectionResetError):
            pass                                          # el cliente se cansó de esperar (timeout)

    def registrar(self, codigo):
        ESTADO["llamadas"].append({"n": len(ESTADO["llamadas"]) + 1, "hora": time.strftime("%H:%M:%S"),
                                   "t": round(time.time(), 2), "metodo": self.command,
                                   "ruta": self.path.split("?")[0][:80], "respondio": codigo,
                                   "idempotency_key": self.headers.get("Idempotency-Key")})

    def do_GET(self):
        self.atender()

    def do_POST(self):
        self.atender()

    def do_PUT(self):
        self.atender()

    def do_DELETE(self):
        self.atender()

    def atender(self):
        n = int(self.headers.get("Content-Length") or 0)
        cuerpo = self.rfile.read(n) if n else b""
        ruta = self.path

        if ruta.startswith("/_control"):
            with CANDADO:
                if self.command == "POST":
                    try:
                        d = json.loads(cuerpo or b"{}")
                    except Exception:
                        return self.enviar(400, {"error": "JSON inválido"})
                    if d.get("modo") and d["modo"] not in MODOS:
                        return self.enviar(400, {"error": f"modo desconocido; usa uno de {', '.join(MODOS)}"})
                    if d.get("reiniciar"):
                        ESTADO.update(llamadas=[], correos=[], llaves={})
                    if d.get("modo"):
                        ESTADO["modo"] = d["modo"]
                        ESTADO["fallo_hecho"] = False
                    if "segundos" in d:
                        ESTADO["segundos"] = float(d["segundos"])
                ll = ESTADO["llamadas"]
                return self.enviar(200, {
                    "modo": ESTADO["modo"], "reenvia_a": REAL or "(respuestas simuladas)",
                    "llamadas_recibidas": len(ll),
                    "llamadas": [{k: v for k, v in x.items() if k != "t"} for x in ll[-6:]],
                    "segundos_entre_llamadas": [round(b["t"] - a["t"], 2) for a, b in zip(ll[-6:], ll[-6:][1:])],
                    "correos_enviados": len(ESTADO["correos"]),
                    "correos": ESTADO["correos"][-4:]})

        modo = ESTADO["modo"]
        if modo == "lento":
            self.registrar(f"200 pero {ESTADO['segundos']:g} s tarde")
            time.sleep(ESTADO["segundos"])
            if ":generatecontent" in ruta.lower():          # sí contesta bien... pero tarde
                return self.enviar(*respuesta_simulada(ruta, cuerpo))
            return self.enviar(200, {"ok": True, "nota": "llegué tarde"})
        if modo == "falla_siempre" or (modo == "falla_una" and not ESTADO["fallo_hecho"]):
            ESTADO["fallo_hecho"] = True
            self.registrar(503)
            return self.enviar(503, {"error": {"code": 503, "message": "The service is currently unavailable.", "status": "UNAVAILABLE"}})
        if modo == "429_una" and not ESTADO["fallo_hecho"]:
            ESTADO["fallo_hecho"] = True
            self.registrar(429)
            return self.enviar(429, {"error": {"code": 429, "message": "Resource exhausted.", "status": "RESOURCE_EXHAUSTED"}},
                               {"Retry-After": "1"})
        if modo == "error_400":
            self.registrar(400)
            return self.enviar(400, {"error": {"code": 400, "message": "Invalid argument.", "status": "INVALID_ARGUMENT"}})
        if modo == "basura":
            self.registrar(200)
            return self.enviar(200, None, crudo=b"<html><body>502 Bad Gateway (proxy)</body></html>")

        # correo simulado (INT-401)
        if ruta.split("?")[0] == "/correos" and self.command == "POST":
            llave = self.headers.get("Idempotency-Key")
            with CANDADO:
                if llave and llave in ESTADO["llaves"]:
                    self.registrar(200)
                    return self.enviar(200, ESTADO["llaves"][llave], {"Idempotent-Replayed": "true"})
                try:
                    d = json.loads(cuerpo or b"{}")
                except Exception:
                    d = {}
                correo = {"id": len(ESTADO["correos"]) + 1, "para": d.get("para"), "asunto": d.get("asunto"),
                          "hora": time.strftime("%H:%M:%S")}
                ESTADO["correos"].append(correo)
                resp = {"enviado": True, "id": correo["id"]}
                if llave:
                    ESTADO["llaves"][llave] = resp
            if modo == "pierde_respuesta" and not ESTADO["fallo_hecho"]:
                ESTADO["fallo_hecho"] = True               # el correo SÍ se mandó, pero la respuesta tarda
                self.registrar(f"200 pero {ESTADO['segundos']:g} s tarde")
                time.sleep(ESTADO["segundos"])
                return self.enviar(200, resp)
            self.registrar(201)
            return self.enviar(201, resp)

        if modo == "pierde_respuesta" and not ESTADO["fallo_hecho"]:
            ESTADO["fallo_hecho"] = True
            self.registrar(f"200 pero {ESTADO['segundos']:g} s tarde")
            time.sleep(ESTADO["segundos"])

        if REAL:                                          # reenviar al servicio real
            req = urllib.request.Request(REAL + ruta, data=cuerpo or None, method=self.command)
            for k in ("Content-Type", "Authorization", "x-goog-api-key", "Accept", "Idempotency-Key"):
                if self.headers.get(k):
                    req.add_header(k, self.headers[k])
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    codigo, datos = r.status, r.read()
            except urllib.error.HTTPError as e:
                codigo, datos = e.code, e.read()
            except Exception as e:
                self.registrar(502)
                return self.enviar(502, {"error": f"el simulador no pudo llegar a {REAL}: {e}"})
            self.registrar(codigo)
            return self.enviar(codigo, None, crudo=datos)
        codigo, obj = respuesta_simulada(ruta, cuerpo)
        self.registrar(codigo)
        return self.enviar(codigo, obj)


def arrancar(puerto=PUERTO):
    srv = ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


if __name__ == "__main__":
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PUERTO), Manejador)
    except OSError:
        sys.exit(f"El puerto {PUERTO} está ocupado: ¿ya hay un simulador abierto?")
    srv.daemon_threads = True
    print(f"Simulador escuchando en http://127.0.0.1:{PUERTO}  ·  " + (f"reenvía a {REAL}" if REAL else "respuestas simuladas"))
    print("Su API debe usar:  set EXTERNO_URL=http://127.0.0.1:%d   ·   Ctrl+C para terminar" % PUERTO)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("Simulador cerrado.")
