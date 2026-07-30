import ast
import csv
import hashlib
import html
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path


RUTA_BASE = Path(__file__).resolve().parent
RUTA_CSV = RUTA_BASE / "dataset.csv"
RUTA_DB_TRANSACCIONAL = RUTA_BASE / "db_transaccional.db"
RUTA_DB_ESTRELLA = RUTA_BASE / "db_estrella.db"

COLUMNAS_ESPERADAS = [
    "id",
    "nombre",
    "estado",
    "especie",
    "origen",
    "ubicacion",
    "episodios",
    "fecha_creacion",
]

MARCADORES_NULOS = {"", "n/a", "null", "none", "---", "???"}
PATRON_EPISODIO = re.compile(r"^S\d{2}E\d{2}$")
SUFIJOS_RUIDO = ["#VALUE!", "N/A", "!!", "Ã±", "Ã¡", "â€", "'"]

NOMBRES_VALIDOS = {
    "rick sanchez": "Rick Sanchez",
    "morty smith": "Morty Smith",
    "summer smith": "Summer Smith",
    "beth smith": "Beth Smith",
    "jerry smith": "Jerry Smith",
    "birdperson": "Birdperson",
    "squanchy": "Squanchy",
    "evil morty": "Evil Morty",
    "pickle rick": "Pickle Rick",
    "meeseeks": "Meeseeks",
}

ESPECIES_VALIDAS = {
    "human": "Human",
    "alien": "Alien",
    "robot": "Robot",
    "cronenberg": "Cronenberg",
    "mythological creature": "Mythological Creature",
    "unkn0wn": "Unknown",
    "unknown": "Unknown",
}


def limpiar_texto(valor):
    """Quita espacios sobrantes y decodifica entidades HTML."""
    texto = html.unescape(valor or "")
    return re.sub(r"\s+", " ", texto).strip()


def quitar_ruido_final(texto):
    """Elimina sufijos de contaminación detectados en el perfilado."""
    resultado = texto
    hubo_cambio = True

    while hubo_cambio:
        hubo_cambio = False
        for sufijo in SUFIJOS_RUIDO:
            if resultado.endswith(sufijo):
                resultado = resultado[:-len(sufijo)].strip()
                hubo_cambio = True

    return resultado


def normalizar_nombre(valor):
    texto = quitar_ruido_final(limpiar_texto(valor))
    return NOMBRES_VALIDOS.get(texto.lower(), texto.title())


def normalizar_estado(valor):
    texto = limpiar_texto(valor).lower()

    if texto in MARCADORES_NULOS:
        return None

    equivalencias = {
        "alive": "Alive",
        "dead": "Dead",
        "unknown": "Unknown",
    }
    return equivalencias.get(texto)


def normalizar_especie(valor):
    texto = quitar_ruido_final(limpiar_texto(valor)).lower()

    if texto in MARCADORES_NULOS:
        return None

    return ESPECIES_VALIDAS.get(texto)


def normalizar_origen(valor):
    texto = limpiar_texto(valor)

    if texto.lower() in MARCADORES_NULOS:
        return None

    equivalencias = {
        "signus 5": "Signus 5",
        "citadel of ricks & mortys": "Citadel of Ricks & Mortys",
        "unknown": "Unknown",
        "abadango": "Abadango",
        "earth (c-137)": "Earth (C-137)",
        "earth (replacement dimension)": "Earth (Replacement Dimension)",
    }
    return equivalencias.get(texto.lower(), texto)


def normalizar_ubicacion(valor):
    texto = limpiar_texto(valor)

    if texto.lower() in MARCADORES_NULOS:
        return None

    equivalencias = {
        "anatomy park": "Anatomy Park",
        "planet squanch": "Planet Squanch",
        "earth (c-137)": "Earth (C-137)",
        "gazorpazorp": "Gazorpazorp",
        "citadel of ricks": "Citadel of Ricks",
    }
    return equivalencias.get(texto.lower(), texto)


def normalizar_fecha(valor):
    """Convierte las fechas válidas a YYYY-MM-DD."""
    texto = limpiar_texto(valor)

    if not texto or texto in {"NOT_A_DATE", "INVALID_DATE_2026"}:
        return None

    formatos = [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m-%d-%Y",
    ]

    for formato in formatos:
        try:
            return datetime.strptime(texto, formato).date().isoformat()
        except ValueError:
            continue

    return None


def extraer_episodios(valor):
    """Convierte los formatos encontrados en una lista sin repetidos."""
    texto = limpiar_texto(valor)

    if texto.startswith("[") and texto.endswith("]"):
        try:
            episodios = ast.literal_eval(texto)
        except (ValueError, SyntaxError):
            episodios = []
    elif "|" in texto:
        episodios = texto.split("|")
    elif "," in texto:
        episodios = texto.split(",")
    elif texto:
        episodios = [texto]
    else:
        episodios = []

    resultado = []
    vistos = set()

    for episodio in episodios:
        codigo = str(episodio).strip()
        if PATRON_EPISODIO.fullmatch(codigo) and codigo not in vistos:
            resultado.append(codigo)
            vistos.add(codigo)

    return resultado


def calcular_hash(fila):
    contenido = json.dumps(
        [fila[columna] for columna in COLUMNAS_ESPERADAS],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


def leer_dataset():
    if not RUTA_CSV.exists():
        raise FileNotFoundError(f"No se encontró {RUTA_CSV.name}")

    with RUTA_CSV.open("r", encoding="utf-8", newline="") as archivo:
        lector = csv.DictReader(archivo)

        if lector.fieldnames != COLUMNAS_ESPERADAS:
            raise ValueError(
                "Las columnas del CSV no coinciden con las esperadas."
            )

        return list(lector)


def crear_esquema_transaccional(conexion):
    conexion.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE tbl_carga (
            id_carga INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_archivo TEXT NOT NULL,
            fecha_inicio TEXT NOT NULL,
            fecha_fin TEXT,
            filas_leidas INTEGER NOT NULL DEFAULT 0,
            filas_procesadas INTEGER NOT NULL DEFAULT 0,
            estado TEXT NOT NULL,
            observaciones TEXT
        );

        CREATE TABLE tbl_registro_raw (
            id_registro_raw INTEGER PRIMARY KEY AUTOINCREMENT,
            id_carga INTEGER NOT NULL,
            numero_fila INTEGER NOT NULL,
            id_personaje_origen INTEGER NOT NULL,
            nombre_original TEXT NOT NULL,
            estado_original TEXT,
            especie_original TEXT,
            origen_original TEXT,
            ubicacion_original TEXT,
            episodios_original TEXT,
            fecha_creacion_original TEXT,
            hash_registro TEXT NOT NULL,
            es_duplicado_exacto INTEGER NOT NULL DEFAULT 0
                CHECK (es_duplicado_exacto IN (0, 1)),
            UNIQUE (id_carga, numero_fila),
            FOREIGN KEY (id_carga) REFERENCES tbl_carga(id_carga)
        );

        CREATE TABLE tbl_especie (
            id_especie INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE
        );

        CREATE TABLE tbl_origen (
            id_origen INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE
        );

        CREATE TABLE tbl_estado (
            id_estado INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE
        );

        CREATE TABLE tbl_ubicacion (
            id_ubicacion INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE
        );

        CREATE TABLE tbl_personaje (
            id_personaje INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL,
            id_especie INTEGER,
            id_origen INTEGER,
            fecha_creacion TEXT,
            FOREIGN KEY (id_especie) REFERENCES tbl_especie(id_especie),
            FOREIGN KEY (id_origen) REFERENCES tbl_origen(id_origen)
        );

        CREATE TABLE tbl_personaje_observacion (
            id_observacion INTEGER PRIMARY KEY AUTOINCREMENT,
            id_personaje INTEGER NOT NULL,
            id_registro_raw INTEGER NOT NULL UNIQUE,
            id_estado INTEGER,
            id_ubicacion INTEGER,
            tiene_advertencias INTEGER NOT NULL DEFAULT 0
                CHECK (tiene_advertencias IN (0, 1)),
            detalle_advertencias TEXT,
            FOREIGN KEY (id_personaje)
                REFERENCES tbl_personaje(id_personaje),
            FOREIGN KEY (id_registro_raw)
                REFERENCES tbl_registro_raw(id_registro_raw),
            FOREIGN KEY (id_estado)
                REFERENCES tbl_estado(id_estado),
            FOREIGN KEY (id_ubicacion)
                REFERENCES tbl_ubicacion(id_ubicacion)
        );

        CREATE TABLE tbl_episodio (
            id_episodio INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL UNIQUE,
            temporada INTEGER NOT NULL,
            numero INTEGER NOT NULL
        );

        CREATE TABLE tbl_observacion_episodio (
            id_observacion INTEGER NOT NULL,
            id_episodio INTEGER NOT NULL,
            PRIMARY KEY (id_observacion, id_episodio),
            FOREIGN KEY (id_observacion)
                REFERENCES tbl_personaje_observacion(id_observacion),
            FOREIGN KEY (id_episodio)
                REFERENCES tbl_episodio(id_episodio)
        );

        CREATE INDEX idx_raw_personaje
            ON tbl_registro_raw(id_personaje_origen);
        CREATE INDEX idx_raw_hash
            ON tbl_registro_raw(hash_registro);
        CREATE INDEX idx_observacion_personaje
            ON tbl_personaje_observacion(id_personaje);
        CREATE INDEX idx_observacion_estado
            ON tbl_personaje_observacion(id_estado);
        CREATE INDEX idx_observacion_ubicacion
            ON tbl_personaje_observacion(id_ubicacion);
        CREATE INDEX idx_observacion_episodio
            ON tbl_observacion_episodio(id_episodio);
        """
    )


def obtener_id_catalogo(conexion, tabla, columna_id, valor, cache):
    if valor is None:
        return None

    if valor in cache:
        return cache[valor]

    conexion.execute(
        f"INSERT OR IGNORE INTO {tabla} (nombre) VALUES (?)",
        (valor,),
    )
    id_catalogo = conexion.execute(
        f"SELECT {columna_id} FROM {tabla} WHERE nombre = ?",
        (valor,),
    ).fetchone()[0]

    cache[valor] = id_catalogo
    return id_catalogo


def detectar_advertencias(fila, datos, es_duplicado):
    advertencias = []

    if es_duplicado:
        advertencias.append("duplicado_exacto")

    for campo in ["estado", "especie", "origen", "ubicacion"]:
        if datos[campo] is None:
            advertencias.append(f"{campo}_sin_valor")

    if datos["fecha_creacion"] is None and limpiar_texto(
        fila["fecha_creacion"]
    ):
        advertencias.append("fecha_invalida")

    return advertencias


def cargar_base_transaccional(conexion, filas):
    fecha_inicio = datetime.now().isoformat(timespec="seconds")

    cursor = conexion.execute(
        """
        INSERT INTO tbl_carga (
            nombre_archivo,
            fecha_inicio,
            filas_leidas,
            filas_procesadas,
            estado
        )
        VALUES (?, ?, ?, 0, ?)
        """,
        (RUTA_CSV.name, fecha_inicio, len(filas), "EN_PROCESO"),
    )
    id_carga = cursor.lastrowid

    cache_especies = {}
    cache_origenes = {}
    cache_estados = {}
    cache_ubicaciones = {}
    cache_episodios = {}
    hashes_vistos = set()

    for numero_fila, fila in enumerate(filas, start=2):
        hash_registro = calcular_hash(fila)
        es_duplicado = int(hash_registro in hashes_vistos)
        hashes_vistos.add(hash_registro)

        cursor_raw = conexion.execute(
            """
            INSERT INTO tbl_registro_raw (
                id_carga,
                numero_fila,
                id_personaje_origen,
                nombre_original,
                estado_original,
                especie_original,
                origen_original,
                ubicacion_original,
                episodios_original,
                fecha_creacion_original,
                hash_registro,
                es_duplicado_exacto
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                id_carga,
                numero_fila,
                int(fila["id"].strip()),
                fila["nombre"],
                fila["estado"],
                fila["especie"],
                fila["origen"],
                fila["ubicacion"],
                fila["episodios"],
                fila["fecha_creacion"],
                hash_registro,
                es_duplicado,
            ),
        )
        id_registro_raw = cursor_raw.lastrowid

        datos = {
            "id_personaje": int(fila["id"].strip()),
            "nombre": normalizar_nombre(fila["nombre"]),
            "estado": normalizar_estado(fila["estado"]),
            "especie": normalizar_especie(fila["especie"]),
            "origen": normalizar_origen(fila["origen"]),
            "ubicacion": normalizar_ubicacion(fila["ubicacion"]),
            "fecha_creacion": normalizar_fecha(fila["fecha_creacion"]),
        }

        id_especie = obtener_id_catalogo(
            conexion,
            "tbl_especie",
            "id_especie",
            datos["especie"],
            cache_especies,
        )
        id_origen = obtener_id_catalogo(
            conexion,
            "tbl_origen",
            "id_origen",
            datos["origen"],
            cache_origenes,
        )
        id_estado = obtener_id_catalogo(
            conexion,
            "tbl_estado",
            "id_estado",
            datos["estado"],
            cache_estados,
        )
        id_ubicacion = obtener_id_catalogo(
            conexion,
            "tbl_ubicacion",
            "id_ubicacion",
            datos["ubicacion"],
            cache_ubicaciones,
        )

        conexion.execute(
            """
            INSERT OR IGNORE INTO tbl_personaje (
                id_personaje,
                nombre,
                id_especie,
                id_origen,
                fecha_creacion
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                datos["id_personaje"],
                datos["nombre"],
                id_especie,
                id_origen,
                datos["fecha_creacion"],
            ),
        )

        advertencias = detectar_advertencias(
            fila,
            datos,
            es_duplicado,
        )

        cursor_observacion = conexion.execute(
            """
            INSERT INTO tbl_personaje_observacion (
                id_personaje,
                id_registro_raw,
                id_estado,
                id_ubicacion,
                tiene_advertencias,
                detalle_advertencias
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                datos["id_personaje"],
                id_registro_raw,
                id_estado,
                id_ubicacion,
                int(bool(advertencias)),
                ", ".join(advertencias) if advertencias else None,
            ),
        )
        id_observacion = cursor_observacion.lastrowid

        for codigo in extraer_episodios(fila["episodios"]):
            if codigo not in cache_episodios:
                conexion.execute(
                    """
                    INSERT OR IGNORE INTO tbl_episodio (
                        codigo,
                        temporada,
                        numero
                    )
                    VALUES (?, ?, ?)
                    """,
                    (codigo, int(codigo[1:3]), int(codigo[4:6])),
                )
                cache_episodios[codigo] = conexion.execute(
                    """
                    SELECT id_episodio
                    FROM tbl_episodio
                    WHERE codigo = ?
                    """,
                    (codigo,),
                ).fetchone()[0]

            conexion.execute(
                """
                INSERT OR IGNORE INTO tbl_observacion_episodio (
                    id_observacion,
                    id_episodio
                )
                VALUES (?, ?)
                """,
                (id_observacion, cache_episodios[codigo]),
            )

    conexion.execute(
        """
        UPDATE tbl_carga
        SET fecha_fin = ?,
            filas_procesadas = ?,
            estado = ?,
            observaciones = ?
        WHERE id_carga = ?
        """,
        (
            datetime.now().isoformat(timespec="seconds"),
            len(filas),
            "COMPLETADA",
            "Carga finalizada correctamente.",
            id_carga,
        ),
    )


def validar_base_transaccional(conexion, cantidad_filas):
    conteos = {
        "cargas": conexion.execute(
            "SELECT COUNT(*) FROM tbl_carga"
        ).fetchone()[0],
        "raw": conexion.execute(
            "SELECT COUNT(*) FROM tbl_registro_raw"
        ).fetchone()[0],
        "personajes": conexion.execute(
            "SELECT COUNT(*) FROM tbl_personaje"
        ).fetchone()[0],
        "observaciones": conexion.execute(
            "SELECT COUNT(*) FROM tbl_personaje_observacion"
        ).fetchone()[0],
        "episodios": conexion.execute(
            "SELECT COUNT(*) FROM tbl_episodio"
        ).fetchone()[0],
        "relaciones": conexion.execute(
            "SELECT COUNT(*) FROM tbl_observacion_episodio"
        ).fetchone()[0],
        "duplicados": conexion.execute(
            """
            SELECT COUNT(*)
            FROM tbl_registro_raw
            WHERE es_duplicado_exacto = 1
            """
        ).fetchone()[0],
    }

    if conteos["raw"] != cantidad_filas:
        raise ValueError("No se conservaron todas las filas en la capa raw.")

    if conteos["observaciones"] != cantidad_filas:
        raise ValueError("No se crearon todas las observaciones.")

    if conexion.execute("PRAGMA foreign_key_check").fetchall():
        raise ValueError("La base transaccional tiene claves foráneas inválidas.")

    if conexion.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ValueError("La base transaccional no superó la integridad.")

    return conteos


def construir_base_transaccional(filas):
    ruta_temporal = RUTA_DB_TRANSACCIONAL.with_suffix(".tmp.db")
    ruta_temporal.unlink(missing_ok=True)

    conexion = None

    try:
        conexion = sqlite3.connect(ruta_temporal)
        conexion.execute("PRAGMA foreign_keys = ON")
        crear_esquema_transaccional(conexion)
        cargar_base_transaccional(conexion, filas)
        conteos = validar_base_transaccional(conexion, len(filas))
        conexion.commit()

    except Exception:
        if conexion is not None:
            conexion.rollback()
        raise

    finally:
        if conexion is not None:
            conexion.close()

    RUTA_DB_TRANSACCIONAL.unlink(missing_ok=True)
    ruta_temporal.replace(RUTA_DB_TRANSACCIONAL)
    return conteos


def crear_esquema_estrella(conexion):
    conexion.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE tbl_dim_personaje (
            id_dim_personaje INTEGER PRIMARY KEY AUTOINCREMENT,
            id_personaje_origen INTEGER NOT NULL UNIQUE,
            nombre TEXT NOT NULL,
            especie TEXT,
            origen TEXT,
            fecha_creacion TEXT
        );

        CREATE TABLE tbl_dim_episodio (
            id_dim_episodio INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL UNIQUE,
            temporada INTEGER NOT NULL,
            numero INTEGER NOT NULL
        );

        CREATE TABLE tbl_dim_estado (
            id_dim_estado INTEGER PRIMARY KEY AUTOINCREMENT,
            estado TEXT NOT NULL UNIQUE
        );

        CREATE TABLE tbl_dim_ubicacion (
            id_dim_ubicacion INTEGER PRIMARY KEY AUTOINCREMENT,
            ubicacion TEXT NOT NULL UNIQUE
        );

        CREATE TABLE tbl_hecho_aparicion (
            id_aparicion INTEGER PRIMARY KEY AUTOINCREMENT,
            id_dim_personaje INTEGER NOT NULL,
            id_dim_episodio INTEGER NOT NULL,
            id_dim_estado INTEGER,
            id_dim_ubicacion INTEGER,
            id_observacion_origen INTEGER NOT NULL,
            cantidad INTEGER NOT NULL DEFAULT 1,
            UNIQUE (id_observacion_origen, id_dim_episodio),
            FOREIGN KEY (id_dim_personaje)
                REFERENCES tbl_dim_personaje(id_dim_personaje),
            FOREIGN KEY (id_dim_episodio)
                REFERENCES tbl_dim_episodio(id_dim_episodio),
            FOREIGN KEY (id_dim_estado)
                REFERENCES tbl_dim_estado(id_dim_estado),
            FOREIGN KEY (id_dim_ubicacion)
                REFERENCES tbl_dim_ubicacion(id_dim_ubicacion)
        );

        CREATE INDEX idx_hecho_personaje
            ON tbl_hecho_aparicion(id_dim_personaje);
        CREATE INDEX idx_hecho_episodio
            ON tbl_hecho_aparicion(id_dim_episodio);
        CREATE INDEX idx_hecho_estado
            ON tbl_hecho_aparicion(id_dim_estado);
        CREATE INDEX idx_hecho_ubicacion
            ON tbl_hecho_aparicion(id_dim_ubicacion);
        """
    )


def cargar_modelo_estrella(conexion_estrella, conexion_transaccional):
    personajes = conexion_transaccional.execute(
        """
        SELECT
            p.id_personaje,
            p.nombre,
            e.nombre AS especie,
            o.nombre AS origen,
            p.fecha_creacion
        FROM tbl_personaje p
        LEFT JOIN tbl_especie e
            ON e.id_especie = p.id_especie
        LEFT JOIN tbl_origen o
            ON o.id_origen = p.id_origen
        ORDER BY p.id_personaje
        """
    ).fetchall()

    conexion_estrella.executemany(
        """
        INSERT INTO tbl_dim_personaje (
            id_personaje_origen,
            nombre,
            especie,
            origen,
            fecha_creacion
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        personajes,
    )

    episodios = conexion_transaccional.execute(
        """
        SELECT codigo, temporada, numero
        FROM tbl_episodio
        ORDER BY id_episodio
        """
    ).fetchall()

    conexion_estrella.executemany(
        """
        INSERT INTO tbl_dim_episodio (
            codigo,
            temporada,
            numero
        )
        VALUES (?, ?, ?)
        """,
        episodios,
    )

    estados = conexion_transaccional.execute(
        """
        SELECT nombre
        FROM tbl_estado
        ORDER BY nombre
        """
    ).fetchall()

    ubicaciones = conexion_transaccional.execute(
        """
        SELECT nombre
        FROM tbl_ubicacion
        ORDER BY nombre
        """
    ).fetchall()

    conexion_estrella.executemany(
        "INSERT INTO tbl_dim_estado (estado) VALUES (?)",
        estados,
    )
    conexion_estrella.executemany(
        "INSERT INTO tbl_dim_ubicacion (ubicacion) VALUES (?)",
        ubicaciones,
    )

    mapa_personajes = {
        id_origen: id_dimension
        for id_dimension, id_origen in conexion_estrella.execute(
            """
            SELECT id_dim_personaje, id_personaje_origen
            FROM tbl_dim_personaje
            """
        )
    }
    mapa_episodios = {
        codigo: id_dimension
        for id_dimension, codigo in conexion_estrella.execute(
            """
            SELECT id_dim_episodio, codigo
            FROM tbl_dim_episodio
            """
        )
    }
    mapa_estados = {
        estado: id_dimension
        for id_dimension, estado in conexion_estrella.execute(
            """
            SELECT id_dim_estado, estado
            FROM tbl_dim_estado
            """
        )
    }
    mapa_ubicaciones = {
        ubicacion: id_dimension
        for id_dimension, ubicacion in conexion_estrella.execute(
            """
            SELECT id_dim_ubicacion, ubicacion
            FROM tbl_dim_ubicacion
            """
        )
    }

    filas_hecho = conexion_transaccional.execute(
        """
        SELECT
            po.id_observacion,
            po.id_personaje,
            ep.codigo,
            es.nombre AS estado,
            ub.nombre AS ubicacion
        FROM tbl_personaje_observacion po
        INNER JOIN tbl_registro_raw rr
            ON rr.id_registro_raw = po.id_registro_raw
        INNER JOIN tbl_observacion_episodio oe
            ON oe.id_observacion = po.id_observacion
        INNER JOIN tbl_episodio ep
            ON ep.id_episodio = oe.id_episodio
        LEFT JOIN tbl_estado es
            ON es.id_estado = po.id_estado
        LEFT JOIN tbl_ubicacion ub
            ON ub.id_ubicacion = po.id_ubicacion
        WHERE rr.es_duplicado_exacto = 0
        """
    ).fetchall()

    hechos = [
        (
            mapa_personajes[id_personaje],
            mapa_episodios[codigo],
            mapa_estados.get(estado),
            mapa_ubicaciones.get(ubicacion),
            id_observacion,
            1,
        )
        for id_observacion, id_personaje, codigo, estado, ubicacion
        in filas_hecho
    ]

    conexion_estrella.executemany(
        """
        INSERT INTO tbl_hecho_aparicion (
            id_dim_personaje,
            id_dim_episodio,
            id_dim_estado,
            id_dim_ubicacion,
            id_observacion_origen,
            cantidad
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        hechos,
    )

    return len(hechos)


def validar_base_estrella(conexion, hechos_esperados):
    conteos = {
        "dim_personaje": conexion.execute(
            "SELECT COUNT(*) FROM tbl_dim_personaje"
        ).fetchone()[0],
        "dim_episodio": conexion.execute(
            "SELECT COUNT(*) FROM tbl_dim_episodio"
        ).fetchone()[0],
        "dim_estado": conexion.execute(
            "SELECT COUNT(*) FROM tbl_dim_estado"
        ).fetchone()[0],
        "dim_ubicacion": conexion.execute(
            "SELECT COUNT(*) FROM tbl_dim_ubicacion"
        ).fetchone()[0],
        "hechos": conexion.execute(
            "SELECT COUNT(*) FROM tbl_hecho_aparicion"
        ).fetchone()[0],
    }

    if conteos["hechos"] != hechos_esperados:
        raise ValueError("El total de hechos no coincide con el origen.")

    if conexion.execute("PRAGMA foreign_key_check").fetchall():
        raise ValueError("El modelo estrella tiene claves foráneas inválidas.")

    if conexion.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ValueError("El modelo estrella no superó la integridad.")

    return conteos


def construir_modelo_estrella():
    ruta_temporal = RUTA_DB_ESTRELLA.with_suffix(".tmp.db")
    ruta_temporal.unlink(missing_ok=True)

    conexion_transaccional = None
    conexion_estrella = None

    try:
        conexion_transaccional = sqlite3.connect(RUTA_DB_TRANSACCIONAL)
        conexion_estrella = sqlite3.connect(ruta_temporal)
        conexion_estrella.execute("PRAGMA foreign_keys = ON")

        crear_esquema_estrella(conexion_estrella)
        hechos = cargar_modelo_estrella(
            conexion_estrella,
            conexion_transaccional,
        )
        conteos = validar_base_estrella(
            conexion_estrella,
            hechos,
        )
        conexion_estrella.commit()

    except Exception:
        if conexion_estrella is not None:
            conexion_estrella.rollback()
        raise

    finally:
        if conexion_transaccional is not None:
            conexion_transaccional.close()
        if conexion_estrella is not None:
            conexion_estrella.close()

    RUTA_DB_ESTRELLA.unlink(missing_ok=True)
    ruta_temporal.replace(RUTA_DB_ESTRELLA)
    return conteos


def main():
    try:
        print("1. Leyendo y transformando el dataset...")
        filas = leer_dataset()

        print("2. Construyendo la base transaccional...")
        conteos_transaccional = construir_base_transaccional(filas)

        print("3. Construyendo el modelo estrella desde la base transaccional...")
        conteos_estrella = construir_modelo_estrella()

        print("\nProceso completado correctamente.")
        print(f"Filas leídas: {len(filas)}")
        print(f"Registros raw: {conteos_transaccional['raw']}")
        print(f"Personajes: {conteos_transaccional['personajes']}")
        print(f"Observaciones: {conteos_transaccional['observaciones']}")
        print(f"Episodios: {conteos_transaccional['episodios']}")
        print(f"Relaciones transaccionales: {conteos_transaccional['relaciones']}")
        print(f"Duplicados exactos: {conteos_transaccional['duplicados']}")
        print(f"Filas en la tabla de hechos: {conteos_estrella['hechos']}")
        print(f"Generado: {RUTA_DB_TRANSACCIONAL.name}")
        print(f"Generado: {RUTA_DB_ESTRELLA.name}")

    except Exception as error:
        print(f"\nEl pipeline terminó con error: {error}")
        raise


if __name__ == "__main__":
    main()