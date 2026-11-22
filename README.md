# MiniPoS

MiniPoS es una aplicación de inventario y ventas. El encargado puede administrar productos y los cajeros pueden consultar el inventario y gestionar sus propias ventas. La API está hecha con FastAPI y guarda los datos en SQLite.

## Cómo iniciar la API

Abre PowerShell en la carpeta de MiniPoS e instala las dependencias.

```powershell
python -m pip install fastapi uvicorn PyJWT bcrypt python-dotenv
```

Si todavía no tienes un `.env`, copia `.env.example` como `.env`. Genera un valor para `JWT_SECRETO` con este comando y pégalo en el archivo.

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Conserva los orígenes de ejemplo para el frontend local. Completa `GEMINI_API_KEY` si vas a consultar Gemini directamente. Guarda los valores reales en tu `.env` local.

Desde la carpeta de MiniPoS, inicia la API.

```powershell
python -m uvicorn api_productos:app --host 127.0.0.1 --port 8000 --env-file .env
```

Uvicorn carga la configuración de `.env` al arrancar. Puedes consultar las rutas y hacer peticiones en [Swagger](http://127.0.0.1:8000/docs).

Para abrir el frontend, deja la API corriendo y ejecuta este comando en otra terminal desde la misma carpeta.

```powershell
python -m http.server 5500 --bind 127.0.0.1 --directory front
```

Abre [MiniPoS](http://127.0.0.1:5500) e inicia sesión con una cuenta de demostración. Las credenciales de práctica están en la sección `auth` de `prueba.json`.

## Variables de entorno

El archivo `.env.example` muestra qué variables admite MiniPoS. Para ejecutarlo localmente, guarda los valores reales en `.env`. Los campos de secretos en `.env.example` se dejan vacíos.

| Variable | Para qué sirve |
|---|---|
| `JWT_SECRETO` | Obligatoria. La API la usa para firmar y verificar los tokens JWT. |
| `CORS_ORIGENES` | Obligatoria. Lista de orígenes permitidos, separados por comas. La plantilla incluye `http://127.0.0.1:5500` y `http://localhost:5500`. |
| `EXTERNO_URL` | Dirección del servicio externo. Por defecto apunta a Gemini. Para las pruebas apunta al simulador local en `http://127.0.0.1:9000`. |
| `GEMINI_MODELO` | Modelo que usa la API para solicitar una descripción de producto. |
| `GEMINI_API_KEY` | Clave necesaria para consultar Gemini directamente. El simulador local funciona sin ella. |

## Ejemplo de uso

1. Abre [Swagger](http://127.0.0.1:8000/docs).
2. Inicia sesión como encargado con `POST /login`. Copia el `access_token` y pégalo en **Authorize**.
3. En `POST /productos`, envía este ejemplo con un código de barras que todavía no exista.

   ```json
   {
     "nombre": "Producto de prueba",
     "precio": 25,
     "stock": 10,
     "codigo_barras": "9900000000001"
   }
   ```

4. La API devuelve `201 Created`. Si envías el mismo JSON otra vez, devuelve `409 Conflict` porque el código de barras ya existe.
5. Ejecuta `GET /productos` para ver el producto en el inventario.

## Pruebas automáticas

1. Detén Uvicorn, cambia temporalmente esta línea en `.env` y vuelve a iniciar la API con el comando de «Cómo iniciar la API».

   ```dotenv
   EXTERNO_URL=http://127.0.0.1:9000
   ```

2. Con la API corriendo, abre otra terminal en la carpeta de MiniPoS y ejecuta:

   ```powershell
   python probar_api.py
   ```

3. Cuando termine la primera ronda, reinicia Uvicorn con la misma configuración y vuelve a ejecutar `python probar_api.py`. La segunda ronda comprueba que el producto de prueba siga en SQLite después del reinicio.

4. Para volver a usar Gemini, restaura esta línea en `.env` y reinicia Uvicorn.

   ```dotenv
   EXTERNO_URL=https://generativelanguage.googleapis.com
   ```

Después del último ajuste de CORS, las pruebas automáticas pasaron 28 de 28 con el simulador, incluida la verificación de persistencia tras reiniciar la API. El resultado está en reporte_U3S6_20206742.txt.

## REST y SOAP en mi proyecto

MiniPoS usa una API REST para que la página pueda consultar y actualizar el inventario mediante HTTP y JSON. Si en el futuro necesitáramos emitir facturas y el proveedor de timbrado ofreciera un servicio SOAP, el backend enviaría los datos de la venta en un mensaje XML, leería la respuesta del proveedor y guardaría el identificador del comprobante junto con la venta.

## Anatomía de mi API

Anatomía de mi API · lista de revisión (42 de 43)

0 · Cliente (2/2)
  [x] Mi proyecto tiene un cliente que consume la API: una página, una app o un script.
  [x] Puedo hacer una acción en el cliente y mostrar la petición y la respuesta en la pestaña Red (F12).
  En la presentación: Abran su front y hagan una acción en vivo. Con F12 → Red, muestren la petición que salió y la respuesta que llegó.

1 · Petición HTTP (3/3)
  [x] Mis rutas nombran cosas (/tareas, /tareas/7), no acciones (/crearTarea).
  [x] Cada operación usa el método correcto: GET lee, POST crea, PUT o PATCH modifica, DELETE borra.
  [x] Tengo la ficha de endpoints: método, ruta, qué recibe y qué responde.
  En la presentación: Muestren su ficha de endpoints o /docs y expliquen en una frase qué hace cada ruta.

2 · CORS (3/3)
  [x] Configuré CORS con una lista de orígenes, no con *.
  [x] Authorization y Content-Type están en los encabezados permitidos.
  [x] CORS va antes de revisar el token.
  En la presentación: Abran su front desde su origen (por ejemplo, el puerto 5500) con F12 abierto: la consola sin errores de CORS.

3 · Autenticación (3/3)
  [x] Las contraseñas se guardan con hash (bcrypt o password_hash).
  [x] El login regresa un token JWT con vencimiento.
  [x] Sin token, o con un token alterado, la API responde 401.
  En la presentación: Hagan una petición a una ruta protegida sin token (401) y luego con token (200).

4 · Autorización (2/2)
  [x] Hay al menos dos roles y una acción que un rol no puede hacer (403).
  [x] Las consultas de recursos propios filtran por el usuario del token (WHERE id = ? AND usuario = ?).
  En la presentación: Con el usuario A pidan un recurso del usuario B: debe responder 404. Con un rol sin permiso intenten borrar: 403.

5 · Validación (3/3)
  [x] Valido campos obligatorios, tipo, formato y rango.
  [x] Un dato inválido responde 422 y dice qué campo falló.
  [x] Un duplicado o una regla rota responde 409.
  En la presentación: Manden un dato inválido desde su front y muestren que el error aparece en el campo correcto.

6 · Endpoint / controlador (2/2)
  [x] Tengo el CRUD completo de mi recurso principal.
  [x] Cada operación responde con su código: 200, 201, 204 o 404.
  En la presentación: Recorran el CRUD de su recurso principal en /docs, Postman o su front.

7 · Servicio / lógica de negocio (2/2)
  [x] Identifico al menos una regla de negocio propia de mi proyecto.
  [x] La regla está en una función aparte, no revuelta con el manejo de HTTP.
  En la presentación: Expliquen su regla de negocio y muestren el caso en que dice que no (409).

7b · Integraciones externas (5/5)
  [x] Mi API consume al menos un servicio externo.
  [x] La llamada tiene un tiempo máximo de espera (timeout).
  [x] Si el servicio falla o tarda, responde 502 o 504 con un mensaje claro.
  [x] La clave del servicio está en una variable de entorno.
  [x] Puedo explicar en qué caso se usaría SOAP en lugar de REST (por ejemplo, el SAT).
  En la presentación: Muestren la integración funcionando y luego la falla controlada: sin clave (503) o con el servicio caído (502 o 504).

8 · Persistencia (2/2)
  [x] Los datos se guardan en una base de datos y sobreviven al reinicio.
  [x] Todas mis consultas usan parámetros (?), ninguna pega datos al texto del SQL.
  En la presentación: Reinicien la API en vivo y muestren que los datos siguen ahí. Enseñen una de sus consultas con ?.

9 · Respuesta HTTP (2/2)
  [x] Todos mis errores salen en JSON con el mismo formato: {"error": ..., "detalles": [...]}.
  [x] Ningún error muestra trazas, rutas de archivos ni SQL.
  En la presentación: Provoquen dos errores distintos y muestren que ambos llegan con el mismo formato JSON.

Configuración base (3/3)
  [x] Secretos y claves (JWT, IA, base de datos) se leen de variables de entorno, no están escritos en el código.
  [x] En mi repositorio de GitHub no hay ninguna clave.
  [x] Mi README dice qué variables hay que configurar.
  En la presentación: Muestren dónde lee su código las variables de entorno y busquen en vivo en su repositorio que no haya ninguna clave.

Pruebas automáticas (2/2)
  [x] Tengo pruebas automáticas (probar_api.py, una colección de Postman o similar).
  [x] Las pruebas pasan antes de entregar.
  En la presentación: Corran sus pruebas en vivo y comenten el resultado.

Documentación (5/6)
  [x] Mi README explica qué es, cómo correrla en pocos pasos, qué variables configurar y cómo probarla.
  [x] Mi API publica su contrato (OpenAPI en /docs u openapi.yaml).
  [x] Tengo .env.example con las variables de entorno, sin valores secretos.
  [x] Tengo docs/arquitectura.md con el diagrama C4 de contenedores: página, API, base de datos y servicio externo.
  [x] Tengo CHANGELOG.md con lo que trae la versión v1.0.0.
  [ ] Recomendado: 2 decisiones explicadas (ADR) en docs/decisiones/ y el catálogo de errores en docs/errores.md.
  En la presentación: Abran su repositorio en GitHub: el README y el diagrama de arquitectura. Con el diagrama expliquen qué parte de su sistema está distribuida y cómo se comunican las piezas.

Timeout e idempotencia (2/2)
  [x] Sé qué operaciones de mi API se pueden repetir sin riesgo y cuáles no.
  [x] Si reintento llamadas externas, solo es ante fallas pasajeras (429, 5xx o timeout).
  En la presentación: Expliquen qué pasaría en su proyecto si el usuario le da doble clic a "Guardar".

Seguridad en capas (1/1)
  [x] Puedo decir qué riesgo del OWASP API Top 10 evita cada capa de mi API.
  En la presentación: Cierren la presentación con la tabla “riesgo → cómo lo evita mi API”.

C:\Users\omard\Documents\Codex\2026-11-21\new-chat\work\MiniPoS-revision-equipo

## Reflexiones del equipo

<!-- Aquí va la reflexión de cada compañero. -->

### Omar

Aprendí que una prueba puede necesitar más de una ejecución. La primera vez obtuve 27 de 28 porque faltaba comprobar la persistencia. Después de reiniciar la API y volver a correr las pruebas, obtuve 28 de 28 y confirmé que SQLite conservó los datos.

También entendí por qué conviene separar una regla de negocio del manejo de HTTP. El alta y la edición ahora comparten la lógica que detecta códigos de barras duplicados, y las rutas devuelven `409` cuando esa regla se incumple.

Lo que más me costó fue entender por qué la prueba de persistencia quedaba pendiente al principio. Si MiniPoS se usara en una empresa, automatizaría el reinicio de la API y la segunda ronda para comprobar la persistencia con cada cambio.