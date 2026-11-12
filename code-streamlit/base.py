import sqlite3
from pathlib import Path

RACINE = Path(__file__).parent.parent
BASE = RACINE / "data.db"


def ouvrir_base():
    """Ouvre la base et la crée au premier lancement. Inutile de modifier cette fonction."""
    neuve = not BASE.exists()
    conn = sqlite3.connect(BASE, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if neuve:
        conn.executescript((RACINE / "base.sql").read_text(encoding="utf-8"))
    else:
        try:
            conn.execute("ALTER TABLE depenses ADD COLUMN categorie TEXT NOT NULL DEFAULT 'Autre'")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    return conn
