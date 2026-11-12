# probar_gemini.py — ¿Funciona tu API key de Gemini? (Unidad III, Sesión 5)
# Uso:   python probar_gemini.py
# Lee la clave de la variable de entorno GEMINI_API_KEY (nunca la escribas en el código).
# 1) Pregunta a Google qué modelos puede usar tu clave.  2) Prueba los "flash", con reintentos
#    ante 503/429 (justo lo que vemos en clase).  3) Te dice cuál guardar en GEMINI_MODELO.
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = "https://generativelanguage.googleapis.com/v1beta"
clave = os.environ.get("GEMINI_API_KEY", "")
if not clave:
    sys.exit("No encuentro la variable GEMINI_API_KEY.\n"
             "Windows: Inicio > 'variables de entorno' > Variables de usuario > Nueva > GEMINI_API_KEY,\n"
             "y abre una ventana NUEVA de cmd. Mac/Linux: export GEMINI_API_KEY=tu-clave")
print(f"GEMINI_API_KEY: definida ({clave[:4]}…, {len(clave)} caracteres)\n")


def pedir(metodo, url, cuerpo=None):
    req = urllib.request.Request(url, data=json.dumps(cuerpo).encode() if cuerpo else None, method=metodo,
                                 headers={"Content-Type": "application/json", "x-goog-api-key": clave})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}
    except Exception as e:
        return None, {"error": {"message": str(e)}}


# 1) ¿Qué modelos puede usar esta clave?
estado, datos = pedir("GET", f"{BASE}/models?pageSize=200")
if estado in (400, 401, 403):
    sys.exit(f"La clave no es válida ({estado}): {datos.get('error', {}).get('message', '')[:150]}")
disponibles = [m["name"].split("/", 1)[1] for m in datos.get("models", [])
               if "generateContent" in m.get("supportedGenerationMethods", [])]
flash = [m for m in disponibles if "flash" in m and "image" not in m and "tts" not in m and "live" not in m]
print(f"Tu clave puede usar {len(disponibles)} modelos; con 'flash' en el nombre: {', '.join(flash[:8]) or '(ninguno)'}\n")

candidatos = [m for m in [os.environ.get("GEMINI_MODELO")] if m] + flash
candidatos = list(dict.fromkeys(candidatos))[:6] or ["gemini-flash-latest"]

# 2) Probar cada uno, reintentando 503 y 429 con espera creciente
pregunta = {"contents": [{"parts": [{"text": 'Responde solo este JSON: {"saludo": "hola desde Gemini"}'}]}],
            "generationConfig": {"responseMimeType": "application/json"}}
for modelo in candidatos:
    for intento in range(1, 4):
        estado, d = pedir("POST", f"{BASE}/models/{modelo}:generateContent", pregunta)
        if estado == 200:
            texto = d["candidates"][0]["content"]["parts"][0]["text"].strip()
            print(f"[OK] {modelo}: {texto}")
            print(f"\nFunciona. Guarda el modelo para que lo use la API:\n   setx GEMINI_MODELO {modelo}\n"
                  "y abre una ventana NUEVA de cmd antes de correr python puente.py")
            sys.exit(0)
        msg = d.get("error", {}).get("message", "")[:90].replace("\n", " ")
        if estado in (429, 500, 503) and intento < 3:
            espera = 2 * 2 ** (intento - 1) + random.uniform(0, 1)
            print(f"[..] {modelo}: {estado} (pasajero) -> reintento en {espera:.0f} s")
            time.sleep(espera)
            continue
        print(f"[X ] {modelo}: {estado} {msg}")
        break

print("\nNingún modelo respondió ahora. Tu clave SÍ es válida (Google contestó 503/429, no 401):")
print("los servidores están saturados. Prueba en unos minutos. Mientras, todo funciona con la IA simulada.")
