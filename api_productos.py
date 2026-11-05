# api_productos.py — Control de inventario de una tienda
# Basado en la estructura de la plantilla api_equipos.py de clase.
# Datos almacenados en memoria; se reinician al detener el servidor.

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

app = FastAPI(title="Control de inventario de una tienda", version="1.0")


# 1. Reglas definidas para los productos (el ID lo crea la API).
class ProductoNuevo(BaseModel):
    nombre: str = Field(..., min_length=1, examples=["Sabritas 50g"])
    precio: float = Field(..., gt=0, allow_inf_nan=False, examples=[21.0])
    stock: int = Field(..., ge=0, examples=[15])
    codigo_barras: str = Field(..., min_length=1, examples=["7501234567890"])


# 2. Almacenamiento en memoria.
productos = {}
siguiente_id = 1


# 3. Formato uniforme de errores.
def error(codigo: int, mensaje: str, detalles=None):
    return JSONResponse(
        status_code=codigo,
        content={"error": mensaje, "detalles": detalles or []},
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
    if producto_id not in productos:
        raise HTTPException(404, f"No existe el producto {producto_id}")
    return productos[producto_id]


def codigo_repetido(codigo_barras: str, excepto: int = 0):
    return any(
        p["codigo_barras"] == codigo_barras and p["id"] != excepto
        for p in productos.values()
    )


# 4. Los cinco endpoints solicitados.
@app.get("/productos", tags=["productos"])
def listar_productos():
    return list(productos.values())


@app.get("/productos/{producto_id}", tags=["productos"])
def consultar_producto(producto_id: int):
    return buscar_producto(producto_id)


@app.post("/productos", status_code=201, tags=["productos"])
def crear_producto(datos: ProductoNuevo, response: Response):
    global siguiente_id
    if codigo_repetido(datos.codigo_barras):
        raise HTTPException(409, "Ya existe un producto con ese código de barras")
    nuevo = {"id": siguiente_id, **datos.model_dump()}
    productos[siguiente_id] = nuevo
    siguiente_id += 1
    response.headers["Location"] = f"/productos/{nuevo['id']}"
    return nuevo


@app.put("/productos/{producto_id}", tags=["productos"])
def reemplazar_producto(producto_id: int, datos: ProductoNuevo):
    buscar_producto(producto_id)
    if codigo_repetido(datos.codigo_barras, excepto=producto_id):
        raise HTTPException(409, "Ya existe un producto con ese código de barras")
    productos[producto_id] = {"id": producto_id, **datos.model_dump()}
    return productos[producto_id]


@app.delete("/productos/{producto_id}", status_code=204, tags=["productos"])
def eliminar_producto(producto_id: int):
    buscar_producto(producto_id)
    del productos[producto_id]
    return Response(status_code=204)
