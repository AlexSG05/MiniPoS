# probar_api.py (versión 2) — Pruebas automáticas de tu API
# Programación Distribuida · Unidad III, Sesión 3
#
# Versión 2: además de las 11 pruebas del CRUD, revisa el contrato OpenAPI (12–14)
# y que los datos sobrevivan a un reinicio del servidor (15).
#
# Funciona con cualquier lenguaje (Python, Node, PHP…): solo habla HTTP con tu API.
# No necesita instalar nada: usa únicamente la biblioteca estándar de Python.
#
# Uso:
#   1. Edita prueba.json con los datos de TU recurso.
#   2. Con tu API corriendo en otra terminal:
#        python probar_api.py
#   3. La primera vez, la prueba 15 queda pendiente: reinicia tu API (Ctrl+C y vuelve
#      a correrla) y corre otra vez probar_api.py.
#   4. Pega en el artefacto todo lo que imprime (también queda en reporte_U3S3_<matrícula>.txt).

import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request

CONFIG = sys.argv[1] if len(sys.argv) > 1 else "prueba.json"

try:
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
except FileNotFoundError:
    sys.exit(f"No encuentro {CONFIG}. Debe estar en la misma carpeta que probar_api.py.")
except json.JSONDecodeError as e:
    sys.exit(f"{CONFIG} no es un JSON válido (línea {e.lineno}): revisa comas y comillas.")

MAT = str(cfg.get("matricula", ""))
BASE = cfg.get("base", "http://127.0.0.1:8000").rstrip("/")
COL = "/" + cfg.get("coleccion", "/recursos").strip("/")
CAMPO_ID = cfg.get("campo_id", "id")
VALIDO = cfg.get("valido", {})
INVALIDO = cfg.get("invalido", {})
CAMBIO = cfg.get("cambio", VALIDO)
METODO_CAMBIO = cfg.get("metodo_cambio", "PUT").upper()
ID_INEXISTENTE = str(cfg.get("id_inexistente", "999999"))
ENCABEZADOS = cfg.get("encabezados", {})
OPENAPI = "/" + str(cfg.get("openapi", "/openapi.json")).strip("/")
ESTADO = f".persistencia_U3S3_{MAT}_{hashlib.sha256((BASE + COL).encode()).hexdigest()[:6]}.json"

if not (MAT.isdigit() and len(MAT) == 8):
    sys.exit("En prueba.json, \"matricula\" debe ser tu matrícula de 8 dígitos.")
if not VALIDO or not INVALIDO:
    sys.exit("En prueba.json faltan \"valido\" o \"invalido\".")
if METODO_CAMBIO not in ("PUT", "PATCH"):
    sys.exit("\"metodo_cambio\" debe ser PUT o PATCH.")


def pedir(metodo, ruta, cuerpo=None, crudo=None):
    """Manda una petición y regresa (código, encabezados, cuerpo_texto)."""
    datos = crudo.encode() if crudo is not None else (json.dumps(cuerpo).encode() if cuerpo is not None else None)
    h = {"Accept": "application/json", **ENCABEZADOS}
    if datos is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + ruta, data=datos, method=metodo, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        sys.exit(f"No pude conectarme a {BASE}: {e.reason}. ¿Tu API está corriendo?")


def como_json(texto):
    try:
        return json.loads(texto)
    except (json.JSONDecodeError, ValueError):
        return None


def lista_de(cuerpo):
    """Acepta [..] o {"datos": [..]} / {"data": [..]} / cualquier objeto con una lista dentro."""
    if isinstance(cuerpo, list):
        return cuerpo
    if isinstance(cuerpo, dict):
        for v in cuerpo.values():
            if isinstance(v, list):
                return v
    return None


def objeto_de(cuerpo):
    """Acepta {..} o {"datos": {..}} / {"data": {..}}."""
    if isinstance(cuerpo, dict) and CAMPO_ID not in cuerpo:
        for v in cuerpo.values():
            if isinstance(v, dict) and CAMPO_ID in v:
                return v
    return cuerpo


def contiene(obj, esperado):
    return isinstance(obj, dict) and all(str(obj.get(k)) == str(v) for k, v in esperado.items())


resultados = []
salida = []


def registrar(n, nombre, ok, detalle):
    resultados.append("1" if ok else "0")
    linea = f"[{'OK' if ok else 'X '}] {n:>2}. {nombre:<44} {detalle}"
    salida.append(linea)
    print(linea)


def es_error_json(cuerpo_texto):
    return como_json(cuerpo_texto) is not None


print(f"Probando {BASE}{COL} con la matrícula {MAT}\n")

# 15 (parte 2). ¿Sigue ahí el registro que dejamos antes de reiniciar?
persistio = None
if os.path.exists(ESTADO):
    try:
        with open(ESTADO, encoding="utf-8") as f:
            guardado = json.load(f)
    except (OSError, json.JSONDecodeError):
        guardado = {}
    if guardado.get("url") == BASE + COL and guardado.get("id"):
        c, _, t = pedir("GET", f"{COL}/{guardado['id']}")
        persistio = c == 200 and contiene(objeto_de(como_json(t)), VALIDO)
        pedir("DELETE", f"{COL}/{guardado['id']}")          # lo limpiamos para no chocar con la prueba 1
    os.remove(ESTADO)

# 1. Crear
c, h, t = pedir("POST", COL, VALIDO)
creado = objeto_de(como_json(t))
nuevo_id = None
if isinstance(creado, dict) and CAMPO_ID in creado:
    nuevo_id = str(creado[CAMPO_ID])
else:
    loc = {k.lower(): v for k, v in h.items()}.get("location", "")
    if loc:
        nuevo_id = loc.rstrip("/").split("/")[-1]
registrar(1, "POST con datos válidos crea (201)", c == 201 and nuevo_id is not None,
          f"-> {c}" + ("" if nuevo_id else "  (no encontré el id en la respuesta ni en Location)"))
if not nuevo_id:
    print("\nSin el id del recurso creado no puedo seguir. Revisa que el POST responda 201 y regrese el recurso con su id.")
    sys.exit(1)
UNO = f"{COL}/{nuevo_id}"

# 2. Consultar
c, h, t = pedir("GET", UNO)
registrar(2, "GET del recurso creado (200)", c == 200 and contiene(objeto_de(como_json(t)), VALIDO), f"-> {c}")

# 3. Listar
c, h, t = pedir("GET", COL)
lista = lista_de(como_json(t))
esta = isinstance(lista, list) and any(isinstance(x, dict) and str(x.get(CAMPO_ID)) == nuevo_id for x in lista)
registrar(3, "GET de la colección lo incluye (200)", c == 200 and esta, f"-> {c}")
antes = len(lista) if isinstance(lista, list) else None

# 4. Datos inválidos: se rechazan y no se guardan
c, h, t = pedir("POST", COL, INVALIDO)
_, _, t2 = pedir("GET", COL)
l2 = lista_de(como_json(t2))
despues = len(l2) if isinstance(l2, list) else None
protegido = antes is not None and despues == antes
registrar(4, "POST inválido se rechaza (422 o 400)", c in (400, 422), f"-> {c}")
registrar(5, "…y no se guardó nada (la foto no cambió)", protegido,
          f"antes {antes}, después {despues}" if antes is not None else "no pude leer la colección")
ok6 = c in (400, 422) and es_error_json(t)
registrar(6, "…y el error viene en JSON", ok6, "" if ok6 else ("la respuesta no es JSON" if c in (400, 422) else "no hubo error"))

# 7. JSON roto
c, h, t = pedir("POST", COL, crudo='{"esto no es": JSON,,}')
ok7 = c in (400, 422) and es_error_json(t)
nota7 = "  (un 500 es un bug: tu API se cayó)" if c >= 500 else ("  (el error no viene en JSON)" if c in (400, 422) and not ok7 else "")
registrar(7, "JSON roto: 400/422 con error en JSON", ok7, f"-> {c}" + nota7)

# 8. No existe
c, h, t = pedir("GET", f"{COL}/{ID_INEXISTENTE}")
registrar(8, "GET de uno que no existe (404)", c == 404, f"-> {c}")

# 9. Cambio dos veces: idempotente
c1, _, _ = pedir(METODO_CAMBIO, UNO, CAMBIO)
_, _, f1 = pedir("GET", UNO)
c2, _, _ = pedir(METODO_CAMBIO, UNO, CAMBIO)
_, _, f2 = pedir("GET", UNO)
foto1, foto2 = objeto_de(como_json(f1)), objeto_de(como_json(f2))
ok9 = c1 in (200, 204) and c2 in (200, 204) and foto1 == foto2 and contiene(foto1, CAMBIO)
registrar(9, f"{METODO_CAMBIO} dos veces: misma foto", ok9, f"-> {c1} y {c2}" + ("" if foto1 == foto2 else "  (la foto cambió)"))

# 10. Borrar dos veces
c1, _, _ = pedir("DELETE", UNO)
c2, _, _ = pedir("DELETE", UNO)
registrar(10, "DELETE dos veces (204/200 y luego 404)", c1 in (200, 204) and c2 == 404, f"-> {c1} y {c2}")

# 11. Ya no existe
c, _, _ = pedir("GET", UNO)
registrar(11, "GET después de borrar (404)", c == 404, f"-> {c}")

# 12–14. El contrato OpenAPI
c, h, t = pedir("GET", OPENAPI)
es_openapi = c == 200 and re.search(r'["\']?openapi["\']?\s*:\s*["\']?3\.', t) is not None
registrar(12, f"El contrato OpenAPI existe ({OPENAPI})", es_openapi,
          f"-> {c}" + ("" if es_openapi or c != 200 else "  (no dice openapi: 3.x)"))
col_re = re.escape(COL)
documenta = es_openapi and re.search(col_re + r'["\']?\s*:', t) is not None and re.search(col_re + r'/\{[^}]+\}', t) is not None
registrar(13, "…documenta la colección y /{id}", documenta, "" if documenta else f"no encuentro {COL} y {COL}/{{id}}")
cods = [k for k in ("201", "404", "422") if re.search(r'(["\']' + k + r'["\']|^\s*' + k + r')\s*:', t, re.M)]
ok14 = es_openapi and len(cods) == 3
registrar(14, "…y documenta 201, 404 y 422", ok14, "" if ok14 else f"solo encontré: {', '.join(cods) or 'ninguno'}")

# 15. Persistencia
if persistio is None:
    c, h, t = pedir("POST", COL, VALIDO)
    obj = objeto_de(como_json(t))
    pid = str(obj[CAMPO_ID]) if isinstance(obj, dict) and CAMPO_ID in obj else None
    if c == 201 and pid:
        with open(ESTADO, "w", encoding="utf-8") as f:
            json.dump({"url": BASE + COL, "id": pid}, f)
        registrar(15, "Los datos sobreviven a un reinicio", False, "PENDIENTE: reinicia tu API y vuelve a correr la prueba")
    else:
        registrar(15, "Los datos sobreviven a un reinicio", False, f"no pude crear el registro de prueba (-> {c})")
else:
    registrar(15, "Los datos sobreviven a un reinicio", persistio,
              "" if persistio else "el registro desapareció: ¿sigues guardando en memoria?")

bits = "".join(resultados)
codigo = hashlib.sha256(f"{MAT}|U3S3|{bits}".encode()).hexdigest()[:8].upper()
total = bits.count("1")
fin = [
    "",
    f"RESULTADO: {total} de {len(bits)}",
    f"U3S3;{MAT};{BASE}{COL};{bits};{codigo}",
]
for x in fin:
    print(x)
salida.extend(fin)

with open(f"reporte_U3S3_{MAT}.txt", "w", encoding="utf-8") as f:
    f.write(f"Probando {BASE}{COL} con la matrícula {MAT}\n\n" + "\n".join(salida) + "\n")
if persistio is None and os.path.exists(ESTADO):
    print("\n>>> Falta la prueba 15: reinicia tu API (Ctrl+C y vuelve a correrla) y corre otra vez: python probar_api.py")
print(f"\nGuardado en reporte_U3S3_{MAT}.txt. Pégalo completo en el artefacto.")
