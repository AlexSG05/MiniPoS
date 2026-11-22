# Historial de cambios

## v1.0.0

- Inventario de productos y registro de ventas con FastAPI y SQLite.
- Inicio de sesión con JWT, permisos por rol y acceso a las ventas propias.
- El alta y la edición de productos comparten la regla que rechaza códigos de barras duplicados con HTTP 409.
- El secreto JWT se configura mediante una variable de entorno.
- Integración con Gemini para sugerir descripciones de productos y simulador local para las pruebas.
- Documentación de arranque, ejemplos de uso y diagrama de arquitectura.
- Se comprobaron 28 de 28 pruebas automáticas, incluida la persistencia tras reiniciar la API.