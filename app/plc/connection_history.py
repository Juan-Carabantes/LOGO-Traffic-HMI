import sqlite3
from pathlib import Path


class ConnectionHistory:
    """Historial SQLite de las IP usadas para conectar con el Logo y su frecuencia de uso."""

    def __init__(self, database_path: Path):
        """Prepara la base de datos y crea la tabla si no existe."""
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_table()

    def _connect(self):
        """Abre una conexión nueva con la base de datos."""
        return sqlite3.connect(self.database_path)

    def _create_table(self):
        """Crea la tabla connection_history si todavía no existe."""
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS connection_history (
                    ip TEXT PRIMARY KEY,
                    usage_count INTEGER NOT NULL DEFAULT 0,
                    last_used TEXT NOT NULL
                )
                """
            )

    def record_connection(self, ip, timestamp):
        """Registra una conexión: agrega la IP o suma uno a su contador y actualiza la fecha."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO connection_history (ip, usage_count, last_used)
                VALUES (?, 1, ?)
                ON CONFLICT(ip) DO UPDATE SET
                    usage_count = usage_count + 1,
                    last_used = excluded.last_used
                """,
                (ip, timestamp),
            )

