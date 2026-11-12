
import sqlite3
import bcrypt

conexion = sqlite3.connect("productos.db")

conexion.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    usuario TEXT PRIMARY KEY,
    clave_hash TEXT NOT NULL,
    rol TEXT NOT NULL
)
""")

usuarios = [
    ("admin", "admin123", "administrador"),
    ("alex", "alex12345", "alumno"),
    ("juan", "juan12345", "alumno")
]

for usuario, clave, rol in usuarios:
    clave_hash = bcrypt.hashpw(
        clave.encode(),
        bcrypt.gensalt(rounds=12)
    ).decode()

    conexion.execute("""
        INSERT OR IGNORE INTO usuarios (usuario, clave_hash, rol)
        VALUES (?, ?, ?)
    """, (usuario, clave_hash, rol))

conexion.commit()

resultados = conexion.execute("""
    SELECT usuario, rol FROM usuarios
""").fetchall()

print("Usuarios registrados:")
for usuario, rol in resultados:
    print(f"Usuario: {usuario} | Rol: {rol}")

conexion.close()

print("\nProceso terminado correctamente.")
