
from pathlib import Path
import os
import sqlite3
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

import json, os, urllib.request, urllib.error
from fastapi import HTTPException

SECRETO = os.environ.get(
    "JWT_SECRETO",
    "clave-de-desarrollo-cambiala-en-produccion-2026"
)
ALGORITMO = "HS256"
DURACION_TOKEN_MINUTOS = 30

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "productos.db"

app = FastAPI(
    title="MiniPoS - Control de inventario",
    description=(
        "API de inventario con autenticación JWT, autorización por roles "
        "y control de propiedad de ventas (SEC-311/BOLA)."
    ),
    version="3.0"
)

bearer = HTTPBearer(auto_error=False)

def obtener_conexion():
    conexion = sqlite3.connect(DB_PATH)
    conexion.row_factory = sqlite3.Row
    return conexion


def inicializar_bd():
    """Crea las tablas y agrega usuarios de demostración sin duplicarlos."""
    conexion = obtener_conexion()
    try:
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS productos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                precio REAL NOT NULL CHECK(precio > 0),
                stock INTEGER NOT NULL CHECK(stock >= 0),
                codigo_barras TEXT NOT NULL UNIQUE
            )
        """)

        conexion.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                usuario TEXT PRIMARY KEY,
                clave_hash TEXT NOT NULL,
                rol TEXT NOT NULL
            )
        """)

        conexion.execute("""
            CREATE TABLE IF NOT EXISTS ventas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                descripcion TEXT NOT NULL,
                total REAL NOT NULL CHECK(total > 0),
                usuario TEXT NOT NULL,
                fecha TEXT NOT NULL,
                FOREIGN KEY(usuario) REFERENCES usuarios(usuario)
            )
        """)

        usuarios_demo = [
            ("encargado", "encargado123", "encargado"),
            ("ana", "ana12345", "cajero"),
            ("beto", "beto12345", "cajero"),
        ]

        for usuario, clave, rol in usuarios_demo:
            existe = conexion.execute(
                "SELECT 1 FROM usuarios WHERE usuario = ?",
                (usuario,)
            ).fetchone()

            if existe is None:
                clave_hash = bcrypt.hashpw(
                    clave.encode("utf-8"),
                    bcrypt.gensalt(rounds=12)
                ).decode("utf-8")

                conexion.execute(
                    """
                    INSERT INTO usuarios (usuario, clave_hash, rol)
                    VALUES (?, ?, ?)
                    """,
                    (usuario, clave_hash, rol)
                )

        conexion.commit()
    finally:
        conexion.close()


inicializar_bd()


class Credenciales(BaseModel):
    usuario: str = Field(..., min_length=1)
    clave: str = Field(..., min_length=1)


class ProductoNuevo(BaseModel):
    nombre: str = Field(..., min_length=1, examples=["Sabritas 50g"])
    precio: float = Field(..., gt=0, allow_inf_nan=False, examples=[21.0])
    stock: int = Field(..., ge=0, examples=[15])
    codigo_barras: str = Field(..., min_length=1, examples=["7501234567890"])


class VentaNueva(BaseModel):
    descripcion: str = Field(
        ...,
        min_length=1,
        examples=["Venta de prueba"]
    )
    total: float = Field(..., gt=0, allow_inf_nan=False, examples=[100.0])


class ErrorRespuesta(BaseModel):
    error: str
    detalles: list[str] = []


E401 = {
    401: {
        "model": ErrorRespuesta,
        "description": "Falta el token, es inválido o ya expiró"
    }
}
E403 = {
    403: {
        "model": ErrorRespuesta,
        "description": "El rol del usuario no tiene permiso"
    }
}
E404 = {
    404: {
        "model": ErrorRespuesta,
        "description": "El recurso no existe o no pertenece al usuario"
    }
}
E409 = {
    409: {
        "model": ErrorRespuesta,
        "description": "Conflicto: código de barras duplicado"
    }
}
E422 = {
    422: {
        "model": ErrorRespuesta,
        "description": "Datos de entrada no válidos"
    }
}


def error(codigo: int, mensaje: str, detalles=None):
    return JSONResponse(
        status_code=codigo,
        content={
            "error": mensaje,
            "detalles": detalles or []
        }
    )


@app.exception_handler(HTTPException)
async def error_http(request: Request, exc: HTTPException):
    return error(exc.status_code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def error_validacion(request: Request, exc: RequestValidationError):
    errores = exc.errors()

    if any(e["type"] == "json_invalid" for e in errores):
        return error(400, "El cuerpo no es un JSON válido")

    detalles = [
        f"{'.'.join(str(x) for x in e['loc'][1:])}: {e['msg']}"
        for e in errores
    ]
    return error(422, "Los datos no son válidos", detalles)


@app.exception_handler(Exception)
async def error_interno(request: Request, exc: Exception):
    return error(500, "Error interno del servidor")

@app.post(
    "/login",
    tags=["autenticación"],
    responses={
        401: {
            "model": ErrorRespuesta,
            "description": "Usuario o clave incorrectos"
        },
        422: E422[422]
    }
)
def login(c: Credenciales):
    conexion = obtener_conexion()
    try:
        fila = conexion.execute(
            """
            SELECT usuario, clave_hash, rol
            FROM usuarios
            WHERE usuario = ?
            """,
            (c.usuario,)
        ).fetchone()

        if fila is None or not bcrypt.checkpw(
            c.clave.encode("utf-8"),
            fila["clave_hash"].encode("utf-8")
        ):
            raise HTTPException(
                status_code=401,
                detail="Usuario o clave incorrectos"
            )

        ahora = datetime.now(timezone.utc)
        token = jwt.encode(
            {
                "sub": fila["usuario"],
                "rol": fila["rol"],
                "iat": ahora,
                "exp": ahora + timedelta(minutes=DURACION_TOKEN_MINUTOS)
            },
            SECRETO,
            algorithm=ALGORITMO
        )

        return {
            "access_token": token,
            "token_type": "bearer"
        }
    finally:
        conexion.close()



def usuario_actual(
    cred: HTTPAuthorizationCredentials = Depends(bearer)
) -> dict:
    if cred is None:
        raise HTTPException(
            status_code=401,
            detail="Falta el token: inicia sesión en POST /login"
        )

    try:
        datos = jwt.decode(
            cred.credentials,
            SECRETO,
            algorithms=["HS256"]
        )

        usuario = datos.get("sub")
        rol = datos.get("rol")
        if not usuario or not rol:
            raise jwt.InvalidTokenError("Faltan claims requeridos")

        return {"usuario": usuario, "rol": rol}

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="El token no es válido o ya expiró"
        )


@app.get(
    "/yo",
    tags=["autenticación"],
    responses={**E401}
)
def ver_usuario(yo: dict = Depends(usuario_actual)):
    return yo



def solo_encargado(yo: dict = Depends(usuario_actual)) -> dict:
    if yo["rol"] != "encargado":
        raise HTTPException(
            status_code=403,
            detail="Tu rol no puede hacer esto"
        )
    return yo


def buscar_producto(producto_id: int):
    conexion = obtener_conexion()
    try:
        producto = conexion.execute(
            "SELECT * FROM productos WHERE id = ?",
            (producto_id,)
        ).fetchone()

        if producto is None:
            raise HTTPException(
                status_code=404,
                detail=f"No existe el producto {producto_id}"
            )
        return dict(producto)
    finally:
        conexion.close()


def codigo_repetido(codigo_barras: str, excepto: int = 0):
    conexion = obtener_conexion()
    try:
        fila = conexion.execute(
            """
            SELECT id FROM productos
            WHERE codigo_barras = ? AND id != ?
            """,
            (codigo_barras, excepto)
        ).fetchone()
        return fila is not None
    finally:
        conexion.close()


@app.get(
    "/productos",
    tags=["productos"],
    responses={**E401, 422: E422[422]}
)
def listar_productos(yo: dict = Depends(usuario_actual)):
    conexion = obtener_conexion()
    try:
        filas = conexion.execute(
            "SELECT * FROM productos ORDER BY id"
        ).fetchall()
        return [dict(fila) for fila in filas]
    finally:
        conexion.close()


@app.get(
    "/productos/{producto_id}",
    tags=["productos"],
    responses={**E401, **E404, 422: E422[422]}
)
def consultar_producto(
    producto_id: int,
    yo: dict = Depends(usuario_actual)
):
    return buscar_producto(producto_id)


@app.post(
    "/productos",
    status_code=201,
    tags=["productos"],
    responses={**E401, **E403, **E409, 422: E422[422]}
)
def crear_producto(
    datos: ProductoNuevo,
    response: Response,
    yo: dict = Depends(solo_encargado)
):
    conexion = obtener_conexion()
    try:
        cursor = conexion.execute(
            """
            INSERT INTO productos
                (nombre, precio, stock, codigo_barras)
            VALUES (?, ?, ?, ?)
            """,
            (
                datos.nombre,
                datos.precio,
                datos.stock,
                datos.codigo_barras
            )
        )
        nuevo_id = cursor.lastrowid
        conexion.commit()
    except sqlite3.IntegrityError:
        conexion.rollback()
        raise HTTPException(
            status_code=409,
            detail="Ya existe un producto con ese código de barras"
        )
    finally:
        conexion.close()

    response.headers["Location"] = f"/productos/{nuevo_id}"
    return buscar_producto(nuevo_id)


@app.put(
    "/productos/{producto_id}",
    tags=["productos"],
    responses={**E401, **E403, **E404, **E409, 422: E422[422]}
)
def reemplazar_producto(
    producto_id: int,
    datos: ProductoNuevo,
    yo: dict = Depends(solo_encargado)
):
    buscar_producto(producto_id)
    conexion = obtener_conexion()
    try:
        conexion.execute(
            """
            UPDATE productos
            SET nombre = ?, precio = ?, stock = ?, codigo_barras = ?
            WHERE id = ?
            """,
            (
                datos.nombre,
                datos.precio,
                datos.stock,
                datos.codigo_barras,
                producto_id
            )
        )
        conexion.commit()
    except sqlite3.IntegrityError:
        conexion.rollback()
        raise HTTPException(
            status_code=409,
            detail="Ya existe un producto con ese código de barras"
        )
    finally:
        conexion.close()

    return buscar_producto(producto_id)


@app.delete(
    "/productos/{producto_id}",
    status_code=204,
    tags=["productos"],
    responses={**E401, **E403, **E404, 422: E422[422]}
)
def eliminar_producto(
    producto_id: int,
    yo: dict = Depends(solo_encargado)
):
    buscar_producto(producto_id)
    conexion = obtener_conexion()
    try:
        conexion.execute(
            "DELETE FROM productos WHERE id = ?",
            (producto_id,)
        )
        conexion.commit()
    finally:
        conexion.close()

    return Response(status_code=204)


def buscar_venta_propia(venta_id: int, usuario: str):
    conexion = obtener_conexion()
    try:
        fila = conexion.execute(
            """
            SELECT id, descripcion, total, usuario, fecha
            FROM ventas
            WHERE id = ? AND usuario = ?
            """,
            (venta_id, usuario)
        ).fetchone()

        if fila is None:
            raise HTTPException(
                status_code=404,
                detail=f"No existe la venta {venta_id}"
            )
        return dict(fila)
    finally:
        conexion.close()


@app.post(
    "/ventas",
    status_code=201,
    tags=["ventas propias"],
    responses={**E401, 422: E422[422]}
)
def crear_venta(
    datos: VentaNueva,
    response: Response,
    yo: dict = Depends(usuario_actual)
):
    fecha = datetime.now(timezone.utc).isoformat()
    conexion = obtener_conexion()
    try:
        cursor = conexion.execute(
            """
            INSERT INTO ventas (descripcion, total, usuario, fecha)
            VALUES (?, ?, ?, ?)
            """,
            (
                datos.descripcion,
                datos.total,
                yo["usuario"],  
                fecha
            )
        )
        venta_id = cursor.lastrowid
        conexion.commit()
    finally:
        conexion.close()

    response.headers["Location"] = f"/ventas/{venta_id}"
    return buscar_venta_propia(venta_id, yo["usuario"])


@app.get(
    "/ventas",
    tags=["ventas propias"],
    responses={**E401, 422: E422[422]}
)
def listar_ventas_propias(yo: dict = Depends(usuario_actual)):
    conexion = obtener_conexion()
    try:
        filas = conexion.execute(
            """
            SELECT id, descripcion, total, usuario, fecha
            FROM ventas
            WHERE usuario = ?
            ORDER BY id
            """,
            (yo["usuario"],)
        ).fetchall()
        return [dict(fila) for fila in filas]
    finally:
        conexion.close()


@app.get(
    "/ventas/{venta_id}",
    tags=["ventas propias"],
    responses={**E401, **E404, 422: E422[422]}
)
def consultar_venta(
    venta_id: int,
    yo: dict = Depends(usuario_actual)
):
    return buscar_venta_propia(venta_id, yo["usuario"])


@app.put(
    "/ventas/{venta_id}",
    tags=["ventas propias"],
    responses={**E401, **E404, 422: E422[422]}
)
def reemplazar_venta(
    venta_id: int,
    datos: VentaNueva,
    yo: dict = Depends(usuario_actual)
):
    buscar_venta_propia(venta_id, yo["usuario"])

    conexion = obtener_conexion()
    try:
        conexion.execute(
            """
            UPDATE ventas
            SET descripcion = ?, total = ?
            WHERE id = ? AND usuario = ?
            """,
            (
                datos.descripcion,
                datos.total,
                venta_id,
                yo["usuario"]
            )
        )
        conexion.commit()
    finally:
        conexion.close()

    return buscar_venta_propia(venta_id, yo["usuario"])


@app.delete(
    "/ventas/{venta_id}",
    status_code=204,
    tags=["ventas propias"],
    responses={**E401, **E404, 422: E422[422]}
)
def eliminar_venta(
    venta_id: int,
    yo: dict = Depends(usuario_actual)
):
    buscar_venta_propia(venta_id, yo["usuario"])

    conexion = obtener_conexion()
    try:
        conexion.execute(
            "DELETE FROM ventas WHERE id = ? AND usuario = ?",
            (venta_id, yo["usuario"])
        )
        conexion.commit()
    finally:
        conexion.close()

    return Response(status_code=204)

# -----------Sesión 5 ----------------
IA_URL = os.environ.get("EXTERNO_URL", "https://generativelanguage.googleapis.com")
IA_MODELO = os.environ.get("GEMINI_MODELO", "gemini-flash-lite-latest")
IA_CLAVE = os.environ.get("GEMINI_API_KEY", "")


def preguntar_a_la_ia(instruccion: str) -> dict:
    """Le pregunta algo a Gemini y regresa el JSON que contestó. Si algo sale mal, responde 502/503/504."""
    if not IA_CLAVE and "googleapis.com" in IA_URL:
        raise HTTPException(503, "Falta configurar la variable de entorno GEMINI_API_KEY")
    cuerpo = {"contents": [{"parts": [{"text": instruccion}]}],
              "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    req = urllib.request.Request(f"{IA_URL}/v1beta/models/{IA_MODELO}:generateContent",
                                 data=json.dumps(cuerpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": IA_CLAVE})
    try:                                                         # IDEA 1: su API llama a otra API
        with urllib.request.urlopen(req, timeout=5) as r:        # IDEA 2: máximo 5 segundos esperando
            respuesta = json.loads(r.read())
        return json.loads(respuesta["candidates"][0]["content"]["parts"][0]["text"])
    except TimeoutError:
        raise HTTPException(504, "La IA tardó demasiado en responder. Intenta en un momento.")
    except urllib.error.HTTPError as e:
        raise HTTPException(502, f"La IA no está disponible (respondió {e.code}). Intenta más tarde.")
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            raise HTTPException(504, "La IA tardó demasiado en responder. Intenta en un momento.")
        raise HTTPException(502, "No se pudo conectar con la IA.")
    except (ValueError, KeyError, IndexError, TypeError):
        raise HTTPException(502, "La IA respondió algo que no entendemos.")

# ---------- Su endpoint con IA ----------

INSTRUCCION_IA = ('Eres el encargado de una tienda de abarrotes. Para el producto que te doy, responde SOLO un JSON con la forma {"categoria": "abarrotes" | "bebidas" | "limpieza" | "papeleria" | "otro", "descripcion": "descripción para el ticket, máximo 12 palabras"}.\n'
                  'Producto: ')

class EntradaProductosDescripcion(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=300)


@app.post("/productos/descripcion")
def productos_descripcion(datos: EntradaProductosDescripcion, yo: dict = Depends(usuario_actual)):
    ia = preguntar_a_la_ia(INSTRUCCION_IA + datos.nombre)
    # Nunca confíen en lo que responde la IA: revisen que trae lo que pidieron
    if not isinstance(ia, dict) or ia.get("categoria") not in ("abarrotes", "bebidas", "limpieza", "papeleria", "otro") or not ia.get("descripcion"):
        raise HTTPException(502, "La IA respondió algo inesperado.")
    return {"categoria": ia["categoria"], "descripcion": str(ia.get("descripcion", ""))[:200]}
#-----------------------Termina sesión 5 ---------------------