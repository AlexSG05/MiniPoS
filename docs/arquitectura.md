# Arquitectura de MiniPoS

## Diagrama C4 de contenedores

```mermaid
flowchart LR
    subgraph MiniPoS
        Web["Página web · HTML y JavaScript<br/>Muestra el inventario y envía peticiones"]
        API["API REST · FastAPI<br/>Valida datos y controla el acceso"]
        DB[("Base de datos · SQLite<br/>Guarda productos, usuarios y ventas")]
    end

    Gemini["Gemini · Servicio externo<br/>Sugiere descripciones de productos"]

    Web -->|"HTTP y JSON"| API
    API -->|"Consultas SQL al archivo local"| DB
    API -->|"HTTPS y JSON"| Gemini
```

La página se sirve en el puerto `5500` y se comunica con la API en el puerto `8000`. FastAPI consulta el archivo local `productos.db`. Para las pruebas, `EXTERNO_URL` permite usar el simulador en el puerto `9000` en lugar de llamar a Gemini.