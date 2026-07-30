import ast
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


RUTA_BASE = Path(__file__).resolve().parent
RUTA_CSV = RUTA_BASE / "dataset.csv"
CARPETA_RESULTADOS = RUTA_BASE / "resultados"
RUTA_PERFIL = CARPETA_RESULTADOS / "perfil_datos.json"

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

MARCADORES_NULOS = {
    "",
    "n/a",
    "null",
    "none",
    "---",
    "???",
}

PATRON_EPISODIO = re.compile(r"^S\d{2}E\d{2}$")


def es_valor_nulo(valor):
    """Indica si el texto representa un dato ausente."""
    return valor.strip().lower() in MARCADORES_NULOS


def extraer_episodios(valor_original):
    """Extrae los episodios y devuelve también el formato detectado."""
    valor = valor_original.strip()

    if not valor:
        return [], "vacio"

    if valor.startswith("[") and valor.endswith("]"):
        try:
            lista = ast.literal_eval(valor)
            if isinstance(lista, list):
                return [str(item).strip() for item in lista], "lista_python"
        except (ValueError, SyntaxError):
            return [], "lista_python_invalida"

    if "|" in valor:
        return [item.strip() for item in valor.split("|")], "separados_por_barra"

    if "," in valor:
        return [item.strip() for item in valor.split(",")], "separados_por_coma"

    return [valor], "individual"


def clasificar_fecha(valor_original):
    """Clasifica el formato de la fecha sin modificar el dato original."""
    valor = valor_original.strip()

    if not valor:
        return "vacia"

    if valor in {"NOT_A_DATE", "INVALID_DATE_2026"}:
        return "invalida_explicita"

    formatos = [
        ("%Y-%m-%d", "fecha_iso"),
        ("%d/%m/%Y", "dia_mes_anio"),
        ("%m-%d-%Y", "mes_dia_anio"),
    ]

    for formato, nombre_formato in formatos:
        try:
            datetime.strptime(valor, formato)
            return nombre_formato
        except ValueError:
            continue

    try:
        datetime.fromisoformat(valor.replace("Z", "+00:00"))
        return "timestamp_iso"
    except ValueError:
        return "no_reconocida"


def contar_anomalias_texto(filas):
    """Cuenta patrones frecuentes de texto dañado o codificado."""
    patrones = {
        "posible_codificacion_con_A_tilde": "Ã",
        "posible_codificacion_de_comillas": "â€",
        "entidad_html_ampersand": "&amp;",
        "entidad_html_numerica": "&#",
    }

    conteos = {nombre: 0 for nombre in patrones}

    for fila in filas:
        for valor in fila.values():
            for nombre, patron in patrones.items():
                if patron in valor:
                    conteos[nombre] += 1

    return conteos


def generar_perfil():
    """Lee el CSV y genera métricas básicas de estructura y calidad."""
    if not RUTA_CSV.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {RUTA_CSV}")

    with RUTA_CSV.open(mode="r", encoding="utf-8", newline="") as archivo_csv:
        lector = csv.DictReader(archivo_csv)

        if lector.fieldnames != COLUMNAS_ESPERADAS:
            raise ValueError(
                "El encabezado del CSV no coincide con el esperado.\n"
                f"Esperado: {COLUMNAS_ESPERADAS}\n"
                f"Recibido: {lector.fieldnames}"
            )

        filas = list(lector)

    vacios_por_columna = {}
    nulos_por_columna = {}
    distintos_por_columna = {}
    valores_frecuentes = {}

    for columna in COLUMNAS_ESPERADAS:
        valores = [fila[columna] for fila in filas]
        frecuencias = Counter(valores)

        vacios_por_columna[columna] = sum(
            1 for valor in valores if not valor.strip()
        )
        nulos_por_columna[columna] = sum(
            1 for valor in valores if es_valor_nulo(valor)
        )
        distintos_por_columna[columna] = len(set(valores))
        valores_frecuentes[columna] = [
            {"valor": valor, "cantidad": cantidad}
            for valor, cantidad in frecuencias.most_common(20)
        ]

    # Duplicados exactos
    registros_completos = [
        tuple(fila[columna] for columna in COLUMNAS_ESPERADAS)
        for fila in filas
    ]
    frecuencias_registros = Counter(registros_completos)

    duplicados_exactos_adicionales = sum(
        cantidad - 1
        for cantidad in frecuencias_registros.values()
        if cantidad > 1
    )

    # Identificadores repetidos
    frecuencias_id = Counter(fila["id"].strip() for fila in filas)
    ids_repetidos = {
        identificador: cantidad
        for identificador, cantidad in frecuencias_id.items()
        if cantidad > 1
    }

    filas_por_id = defaultdict(list)
    for fila in filas:
        filas_por_id[fila["id"].strip()].append(fila)

    ids_repetidos_con_diferencias = 0

    for registros in filas_por_id.values():
        if len(registros) <= 1:
            continue

        versiones = {
            tuple(registro[columna] for columna in COLUMNAS_ESPERADAS)
            for registro in registros
        }

        if len(versiones) > 1:
            ids_repetidos_con_diferencias += 1

    # Episodios
    formatos_episodios = Counter()
    codigos_episodios = Counter()
    tokens_invalidos = []
    filas_con_episodios_repetidos = 0

    for numero_fila, fila in enumerate(filas, start=2):
        episodios, formato = extraer_episodios(fila["episodios"])
        formatos_episodios[formato] += 1

        if len(episodios) != len(set(episodios)):
            filas_con_episodios_repetidos += 1

        for episodio in episodios:
            if PATRON_EPISODIO.fullmatch(episodio):
                codigos_episodios[episodio] += 1
            else:
                tokens_invalidos.append(
                    {
                        "numero_fila_csv": numero_fila,
                        "id": fila["id"],
                        "valor": episodio,
                    }
                )

    formatos_fechas = Counter(
        clasificar_fecha(fila["fecha_creacion"])
        for fila in filas
    )

    return {
        "archivo_origen": RUTA_CSV.name,
        "fecha_generacion": datetime.now().isoformat(timespec="seconds"),
        "estructura": {
            "cantidad_filas": len(filas),
            "cantidad_columnas": len(COLUMNAS_ESPERADAS),
            "columnas": COLUMNAS_ESPERADAS,
        },
        "calidad": {
            "vacios_por_columna": vacios_por_columna,
            "nulos_equivalentes_por_columna": nulos_por_columna,
            "valores_distintos_por_columna": distintos_por_columna,
            "duplicados_exactos_adicionales": duplicados_exactos_adicionales,
            "ids_distintos": len(frecuencias_id),
            "cantidad_ids_repetidos": len(ids_repetidos),
            "filas_adicionales_por_ids_repetidos": sum(
                cantidad - 1 for cantidad in ids_repetidos.values()
            ),
            "ids_repetidos_con_diferencias": ids_repetidos_con_diferencias,
            "anomalias_texto": contar_anomalias_texto(filas),
        },
        "episodios": {
            "formatos_detectados": dict(formatos_episodios),
            "cantidad_codigos_validos_distintos": len(codigos_episodios),
            "codigos_validos": sorted(codigos_episodios),
            "filas_con_episodios_repetidos": filas_con_episodios_repetidos,
            "cantidad_tokens_invalidos": len(tokens_invalidos),
            "muestra_tokens_invalidos": tokens_invalidos[:20],
        },
        "fechas": {
            "formatos_detectados": dict(formatos_fechas),
        },
        "valores_frecuentes": valores_frecuentes,
    }


def main():
    CARPETA_RESULTADOS.mkdir(parents=True, exist_ok=True)

    perfil = generar_perfil()

    with RUTA_PERFIL.open(mode="w", encoding="utf-8") as archivo_salida:
        json.dump(perfil, archivo_salida, ensure_ascii=False, indent=2)

    estructura = perfil["estructura"]
    calidad = perfil["calidad"]
    episodios = perfil["episodios"]

    print("Perfilado completado correctamente.")
    print(f"Filas leídas: {estructura['cantidad_filas']}")
    print(f"Columnas: {estructura['cantidad_columnas']}")
    print(f"IDs distintos: {calidad['ids_distintos']}")
    print(f"IDs repetidos: {calidad['cantidad_ids_repetidos']}")
    print(
        "Duplicados exactos adicionales: "
        f"{calidad['duplicados_exactos_adicionales']}"
    )
    print(
        "IDs repetidos con registros diferentes: "
        f"{calidad['ids_repetidos_con_diferencias']}"
    )
    print(
        "Códigos de episodio distintos: "
        f"{episodios['cantidad_codigos_validos_distintos']}"
    )
    print(f"Informe generado en: {RUTA_PERFIL}")


if __name__ == "__main__":
    main()