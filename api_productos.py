from pathlib import Path
import sqlite3

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

app = FastAPI(
    title="Control de inventario de una tienda",
    version="2.0"
)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "productos.db"


def obtener_conexion():
    conexion = sqlite3.connect(DB_PATH)
    conexion.row_factory = sqlite3.Row
    return conexion



def inicializar_bd():
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
        conexion.commit()
    finally:
        conexion.close()


inicializar_bd()



class ProductoNuevo(BaseModel):
    nombre: str = Field(
        ...,
        min_length=1,
        examples=["Sabritas 50g"]
    )

    precio: float = Field(
        ...,
        gt=0,
        allow_inf_nan=False,
        examples=[21.0]
    )

    stock: int = Field(
        ...,
        ge=0,
        examples=[15]
    )

    codigo_barras: str = Field(
        ...,
        min_length=1,
        examples=["7501234567890"]
    )



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



def buscar_producto(producto_id: int):
    conexion = obtener_conexion()

    try:
        cursor = conexion.execute(
            "SELECT * FROM productos WHERE id = ?",
            (producto_id,)
        )

        producto = cursor.fetchone()

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
        cursor = conexion.execute(
            """
            SELECT id FROM productos
            WHERE codigo_barras = ? AND id != ?
            """,
            (codigo_barras, excepto)
        )

        return cursor.fetchone() is not None

    finally:
        conexion.close()



RESPUESTAS = {
    404: {"description": "Producto no encontrado"},
    409: {"description": "Conflicto: código de barras duplicado"},
    422: {"description": "Datos de entrada no válidos"}
}



@app.get(
    "/productos",
    tags=["productos"],
    responses={422: RESPUESTAS[422]}
)
def listar_productos():
    conexion = obtener_conexion()

    try:
        cursor = conexion.execute(
            "SELECT * FROM productos ORDER BY id"
        )

        return [dict(fila) for fila in cursor.fetchall()]

    finally:
        conexion.close()



@app.get(
    "/productos/{producto_id}",
    tags=["productos"],
    responses={
        404: RESPUESTAS[404],
        422: RESPUESTAS[422]
    }
)
def consultar_producto(producto_id: int):
    return buscar_producto(producto_id)



@app.post(
    "/productos",
    status_code=201,
    tags=["productos"],
    responses={
        409: RESPUESTAS[409],
        422: RESPUESTAS[422]
    }
)
def crear_producto(datos: ProductoNuevo, response: Response):

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
    responses={
        404: RESPUESTAS[404],
        409: RESPUESTAS[409],
        422: RESPUESTAS[422]
    }
)
def reemplazar_producto(producto_id: int, datos: ProductoNuevo):

    
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
    responses={
        404: RESPUESTAS[404],
        422: RESPUESTAS[422]
    }
)
def eliminar_producto(producto_id: int):

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
