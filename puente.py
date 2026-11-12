# puente.py — Terminal en vivo para las slides de la Unidad III, Sesión 5
# Programación Distribuida · Facultad de Telemática · Universidad de Colima
#
# Qué hace:
#   Abre las slides en tu navegador y, cuando das clic en un paso, ejecuta de verdad
#   el comando en esta computadora (arrancar o reiniciar la API, mandar una petición,
#   correr probar_api.py) y muestra la salida real en la terminal de la slide.
#
# Cómo usarlo (Windows, Mac o Linux):
#   1. pip install fastapi uvicorn pyjwt bcrypt     (solo la primera vez)
#   2. python puente.py
#   3. Se abre el navegador en http://127.0.0.1:8765  (si no, ábrelo tú)
#   Para terminar: Ctrl+C en esta ventana (también detiene las APIs que arrancó).
#
# Seguridad: solo escucha en tu propia computadora (127.0.0.1) y solo ejecuta la lista fija
# de comandos de este archivo. Las peticiones solo pueden ir a la API (8000) y al simulador (9000).
# Si existe GEMINI_API_KEY, el simulador reenvía a Gemini de verdad; si no, responde simulado.

import glob
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))
os.chdir(AQUI)
PUERTO = 8765
WIN = os.name == "nt"
CARPETA = os.path.basename(AQUI)
COMO_WIN = WIN or os.environ.get("PUENTE_GRABAR") == "1"   # solo para grabar la salida de respaldo
DIR_MOSTRAR = f"C:\\{CARPETA}" if COMO_WIN and not WIN else AQUI
PROMPT = f"C:\\{CARPETA}>" if COMO_WIN else f"~/{CARPETA}$"

APIS = {  # puerto -> (módulo, descripción)
    8000: ("api_equipos", "API con login, roles, préstamos, IA y correo"),
}
PROCS = {}       # puerto -> (Popen, archivo de log)
CANDADO = threading.Lock()
ENV = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1",
           EXTERNO_URL="http://127.0.0.1:9000", CORREO_URL="http://127.0.0.1:9000")
GEMINI = "https://generativelanguage.googleapis.com"
SIM = {"proc": None}


def arrancar_simulador():
    if SIM["proc"] and SIM["proc"].poll() is None:
        return "(el simulador ya estaba corriendo)"
    if puerto_abierto(9000):
        return "ERROR: algo ya usa el puerto 9000: ¿hay otro simulador abierto? Ciérralo."
    real = GEMINI if os.environ.get("GEMINI_API_KEY") and os.environ.get("PUENTE_GRABAR") != "1" else ""
    extra = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WIN else {}
    SIM["proc"] = subprocess.Popen([sys.executable, "simulador.py"] + ([real] if real else []), cwd=AQUI,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=ENV, **extra)
    for _ in range(40):
        if puerto_abierto(9000):
            break
        time.sleep(0.2)
    return f"Simulador en http://127.0.0.1:9000 · " + (f"reenvía a {real} (tu GEMINI_API_KEY)" if real else "respuestas simuladas (no hay GEMINI_API_KEY)")


# ---------------------------------------------------------------- utilidades
def puerto_abierto(p):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", p)) == 0


def leer_log(ruta, desde=0):
    try:
        with open(ruta, encoding="utf-8", errors="replace") as f:
            f.seek(desde)
            return f.read()
    except OSError:
        return ""


def limpiar_log(t):
    # quita las líneas de cada petición para que la salida se lea fácil
    return "\n".join(l for l in t.splitlines() if l.strip() and '" 2' not in l and '" 4' not in l and '" 5' not in l)


# ---------------------------------------------------------------- comandos
def arrancar(p):
    mod, desc = APIS[p]
    if p in PROCS and PROCS[p][0].poll() is None:
        return f"INFO:     Uvicorn running on http://127.0.0.1:{p} (ya estaba corriendo: {desc})"
    if puerto_abierto(p):
        return (f"ERROR: algo ya está usando el puerto {p}.\n"
                f"Si dejaste una API abierta en otra ventana, ciérrala con Ctrl+C y vuelve a dar clic.")
    ruta = os.path.join(AQUI, f".log_{p}.txt")
    log = open(ruta, "w", encoding="utf-8")
    extra = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WIN else {}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", f"{mod}:app", "--port", str(p)],
                            cwd=AQUI, stdout=log, stderr=subprocess.STDOUT, env=ENV, **extra)
    PROCS[p] = (proc, ruta, log)
    for _ in range(80):
        if puerto_abierto(p):
            break
        if proc.poll() is not None:
            return "ERROR: la API no arrancó.\n" + leer_log(ruta)[-1500:] + \
                   "\n¿Instalaste fastapi y uvicorn?  pip install fastapi uvicorn"
        time.sleep(0.25)
    time.sleep(0.3)
    return limpiar_log(leer_log(ruta))


def detener(p):
    if p not in PROCS or PROCS[p][0].poll() is not None:
        PROCS.pop(p, None)
        return f"(no había una API corriendo en el puerto {p})"
    proc, ruta, log = PROCS.pop(p)
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
    for _ in range(20):
        if not puerto_abierto(p):
            break
        time.sleep(0.2)
    return "^C\nINFO:     Shutting down\nINFO:     Finished server process"


def reiniciar(p):
    return detener(p) + "\n\n" + PROMPT + " " + comando_arrancar(p) + "\n" + arrancar(p)


def comando_arrancar(p):
    return f"uvicorn {APIS[p][0]}:app --port {p}"


def probar():
    r = subprocess.run([sys.executable, "probar_api.py"], cwd=AQUI, capture_output=True, env=ENV, timeout=120)
    return (r.stdout + r.stderr).decode("utf-8", errors="replace").rstrip()


def script(nombre, *args):
    r = subprocess.run([sys.executable, nombre, *args], cwd=AQUI, capture_output=True, env=ENV, timeout=60)
    return (r.stdout + r.stderr).decode("utf-8", errors="replace").rstrip()


TOKEN_RE = __import__("re").compile(r"^[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+$")
CON_ARG = {  # id -> (comando que se muestra, función que recibe el token)
    "decodificar": ("python decodificar_jwt.py {arg}", lambda t: script("decodificar_jwt.py", t)),
    "falsificar": ("python decodificar_jwt.py {arg} --rol encargado", lambda t: script("decodificar_jwt.py", t, "--rol", "encargado")),
    "romperfirma": ("python decodificar_jwt.py {arg} --romper-firma", lambda t: script("decodificar_jwt.py", t, "--romper-firma")),
}


def ver_clave():
    c = os.environ.get("GEMINI_API_KEY", "")
    if not c:
        return "GEMINI_API_KEY no está definida (las slides usan la IA simulada)"
    return f"GEMINI_API_KEY está definida: {c[:4]}{'*' * 12} ({len(c)} caracteres)\nNunca la imprimas completa: ni en la terminal, ni en un log, ni en una captura."


def buscar_clave():
    c = os.environ.get("GEMINI_API_KEY", "")
    if not c:
        return "No hay GEMINI_API_KEY definida: no hay nada que buscar."
    hallados = []
    for raiz, dirs, archivos in os.walk(AQUI):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__")]
        for a in archivos:
            try:
                with open(os.path.join(raiz, a), encoding="utf-8", errors="ignore") as f:
                    if c in f.read():
                        hallados.append(a)
            except OSError:
                pass
    n = sum(len(f) for _, _, f in os.walk(AQUI))
    return (f"Revisé {n} archivos de la carpeta.\n" + ("¡La clave aparece en: " + ", ".join(hallados) + "!" if hallados
            else "La clave NO aparece en ningún archivo: el código la lee de la variable de entorno."))


def ver_log():
    ruta = os.path.join(AQUI, ".log_8000.txt")
    lineas = [l for l in leer_log(ruta).splitlines() if "[externo]" in l or "/reportes" in l or "/demo/" in l]
    return "\n".join(lineas[-8:]) or "(todavía no hay llamadas al servicio externo)"


def reset_sim():
    try:
        urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:9000/_control", method="POST",
                               data=b'{"modo":"normal","reiniciar":true}', headers={"Content-Type": "application/json"}), timeout=3)
        return "(simulador en modo normal, contadores en cero)"
    except Exception:
        return arrancar_simulador()


def ver_bd():
    if WIN:
        r = subprocess.run("dir equipos.db", shell=True, cwd=AQUI, capture_output=True)
        return r.stdout.decode("cp850", errors="replace").rstrip() or "No se encuentra el archivo"
    if not os.path.exists("equipos.db"):
        return "No se encuentra el archivo"
    st = os.stat("equipos.db")
    fecha = datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y  %H:%M")
    return (f" Directorio de {DIR_MOSTRAR}\n\n{fecha}    {st.st_size:>14,} equipos.db\n"
            f"               1 archivos     {st.st_size:>10,} bytes")


def desde_cero():
    salida = [detener(8000), reset_sim()]
    for patron in ("equipos.db", ".persistencia_U3S5_*.json", "reporte_U3S5_*.txt"):
        for f in glob.glob(patron):
            try:
                os.remove(f)
            except OSError:
                pass
    salida.append("(se borró equipos.db y el estado de probar_api.py)")
    salida.append(PROMPT + " " + comando_arrancar(8000) + "\n" + arrancar(8000))
    return "\n".join(salida)


SH = {  # id -> (comando que se muestra, función)
    "arrancar8000": (comando_arrancar(8000), lambda: arrancar(8000)),
    "detener8000": ("Ctrl+C   (en la ventana de la API)", lambda: detener(8000)),
    "reiniciar8000": ("Ctrl+C   (en la ventana de la API)", lambda: reiniciar(8000)),
    "probar": ("python probar_api.py", probar),
    "verbd": ("dir equipos.db", ver_bd),
    "verclave": ("echo GEMINI_API_KEY (sin mostrarla completa)", ver_clave),
    "buscarclave": ('findstr /s /m "<la clave>" *.*', buscar_clave),
    "verlog": ("(ventana de la API: líneas [externo])", ver_log),
    "gemini": ("python probar_gemini.py", lambda: script("probar_gemini.py")),
    "cero": ("(empezar la demostración desde cero)", desde_cero),
}


def peticion(d):
    p, m, u = int(d.get("port", 0)), str(d.get("m", "GET")).upper(), str(d.get("u", "/"))
    if p not in (*APIS, 9000) or m not in ("GET", "POST", "PUT", "DELETE") or not u.startswith("/"):
        return {"error": "Petición no permitida"}
    cuerpo = d.get("b")
    datos = None
    if cuerpo is not None:
        datos = (cuerpo if isinstance(cuerpo, str) else json.dumps(cuerpo, ensure_ascii=False)).encode("utf-8")
    req = urllib.request.Request(f"http://127.0.0.1:{p}{u}", data=datos, method=m)
    auth = (d.get("hdr") or {}).get("Authorization")
    if isinstance(auth, str) and len(auth) < 4000:
        req.add_header("Authorization", auth)            # el único encabezado que se deja pasar
    if datos is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            st, rz, hd, bd = r.status, r.reason, r.headers, r.read()
    except urllib.error.HTTPError as e:
        st, rz, hd, bd = e.code, e.reason, e.headers, e.read()
    except (urllib.error.URLError, OSError):
        return {"conn": f"curl: (7) Failed to connect to 127.0.0.1 port {p}: Connection refused\n"
                        f"(no hay ninguna API corriendo en el puerto {p}; arráncala primero)"}
    hs = {k.lower(): v for k, v in hd.items() if k.lower() in ("content-type", "location", "www-authenticate")}
    return {"status": st, "reason": rz, "headers": hs, "body": bd.decode("utf-8", errors="replace")}


# ---------------------------------------------------------------- servidor
def slides():
    archivos = sorted(glob.glob("u3_sesion*_slides.html"))
    return archivos[-1] if archivos else None


class Manejador(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def responder(self, codigo, cuerpo, tipo="application/json; charset=utf-8"):
        datos = cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(datos)

    def origen_valido(self):
        host = self.headers.get("Host", "")
        origen = self.headers.get("Origin")
        validos = (f"127.0.0.1:{PUERTO}", f"localhost:{PUERTO}")
        return host in validos and (origen is None or origen in [f"http://{v}" for v in validos])

    def do_GET(self):
        if not self.origen_valido():
            return self.responder(403, {"error": "origen no permitido"})
        ruta = self.path.split("?")[0]
        if ruta == "/estado":
            return self.responder(200, {"ok": True, "prompt": PROMPT, "win": WIN,
                                        "apis": {p: puerto_abierto(p) for p in (*APIS, 9000)}})
        nombre = slides() if ruta in ("/", "/index.html") else ruta.lstrip("/")
        if nombre and "/" not in nombre and "\\" not in nombre and nombre.endswith(".html") and os.path.isfile(nombre):
            with open(nombre, "rb") as f:
                return self.responder(200, f.read(), "text/html; charset=utf-8")
        self.responder(404, {"error": "no existe"})

    def do_POST(self):
        if not self.origen_valido() or self.path != "/run":
            return self.responder(403, {"error": "no permitido"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            d = json.loads(self.rfile.read(min(n, 100000)) or b"{}")
        except Exception:
            return self.responder(400, {"error": "JSON inválido"})
        t0 = time.time()
        with CANDADO:
            if "sh" in d and d["sh"] in CON_ARG:
                arg = str(d.get("arg", ""))
                if not TOKEN_RE.match(arg) or len(arg) > 4000:
                    return self.responder(400, {"error": "falta el token (corre antes el paso del login)"})
                cmd, fn = CON_ARG[d["sh"]]
                res = {"cmd": cmd.format(arg="<token>"), "out": fn(arg)}
            elif "sh" in d:
                if d["sh"] not in SH:
                    return self.responder(403, {"error": "comando no permitido"})
                cmd, fn = SH[d["sh"]]
                try:
                    out = fn()
                except Exception as e:
                    out = f"ERROR: {e}"
                res = {"cmd": cmd, "out": out}
            else:
                res = peticion(d)
        res["ms"] = int((time.time() - t0) * 1000)
        res["apis"] = {p: puerto_abierto(p) for p in APIS}
        self.responder(200, res)


def main():
    faltan = []
    for m in ("fastapi", "uvicorn", "jwt", "bcrypt"):
        try:
            __import__(m)
        except ImportError:
            faltan.append(m)
    if faltan:
        sys.exit(f"Falta instalar: {' '.join(faltan)}\n   pip install fastapi uvicorn pyjwt bcrypt")
    if not slides():
        sys.exit("No encuentro el archivo de slides (u3_sesion05_slides.html) en esta carpeta.")
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PUERTO), Manejador)
    except OSError:
        sys.exit(f"El puerto {PUERTO} está ocupado: ¿ya tienes el puente abierto en otra ventana?")
    print(arrancar_simulador())
    print("Arrancando la API en el puerto 8000 (EXTERNO_URL y CORREO_URL apuntan al simulador)…")
    print(arrancar(8000))
    url = f"http://127.0.0.1:{PUERTO}/"
    print(f"\nPuente listo. Abre las slides en:  {url}")
    print("La demostración (slide 5):         http://127.0.0.1:8000/demo")
    print("Las slides de consulta (nivel 2):  " + url + "u3_sesion05_consulta.html\nPara terminar: Ctrl+C\n")
    if "--sin-navegador" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for p in list(PROCS):
            detener(p)
        if SIM["proc"]:
            SIM["proc"].terminate()
        print("Puente cerrado.")


if __name__ == "__main__":
    main()
