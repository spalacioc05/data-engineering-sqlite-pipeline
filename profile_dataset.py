from __future__ import annotations

import ast
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "dataset.csv"
RESULTS_DIR = BASE_DIR / "results"
PROFILE_PATH = RESULTS_DIR / "data_profile.json"

EXPECTED_COLUMNS = [
    "id",
    "nombre",
    "estado",
    "especie",
    "origen",
    "ubicacion",
    "episodios",
    "fecha_creacion",
]

NULL_MARKERS = {
    "",
    "n/a",
    "null",
    "none",
    "---",
    "???",
}

EPISODE_PATTERN = re.compile(r"^S\d{2}E\d{2}$")


def is_null_like(value: str) -> bool:
    """Indica si un valor representa un dato ausente."""
    return value.strip().lower() in NULL_MARKERS


def parse_episode_values(raw_value: str) -> tuple[list[str], str]:
    """
    Extrae episodios sin modificar el archivo original.

    Retorna:
        - Lista de episodios encontrados.
        - Formato detectado.
    """
    value = raw_value.strip()

    if not value:
        return [], "empty"

    if value.startswith("[") and value.endswith("]"):
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed], "python_list"
        except (ValueError, SyntaxError):
            return [], "invalid_python_list"

    if "|" in value:
        return [item.strip() for item in value.split("|")], "pipe"

    if "," in value:
        return [item.strip() for item in value.split(",")], "comma"

    return [value], "single"


def classify_date(raw_value: str) -> str:
    """
    Clasifica el formato de una fecha sin alterar el dato original.

    Convenciones detectadas:
    - YYYY-MM-DD
    - Timestamp ISO
    - DD/MM/YYYY
    - MM-DD-YYYY
    """
    value = raw_value.strip()

    if not value:
        return "empty"

    if value in {"NOT_A_DATE", "INVALID_DATE_2026"}:
        return "explicit_invalid"

    formats = [
        ("%Y-%m-%d", "iso_date"),
        ("%d/%m/%Y", "day_month_year"),
        ("%m-%d-%Y", "month_day_year"),
    ]

    for date_format, label in formats:
        try:
            datetime.strptime(value, date_format)
            return label
        except ValueError:
            pass

    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return "iso_timestamp"
    except ValueError:
        return "unrecognized"


def count_text_anomalies(rows: list[dict[str, str]]) -> dict[str, int]:
    """Cuenta patrones frecuentes de texto dañado o codificado."""
    patterns = {
        "possible_mojibake_A_tilde": "Ã",
        "possible_mojibake_quote": "â€",
        "html_ampersand": "&amp;",
        "html_numeric_entity": "&#",
    }

    results = {name: 0 for name in patterns}

    for row in rows:
        for value in row.values():
            for name, pattern in patterns.items():
                if pattern in value:
                    results[name] += 1

    return results


def profile_dataset() -> dict[str, Any]:
    """Lee el CSV y genera métricas de estructura y calidad."""
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {CSV_PATH}")

    with CSV_PATH.open(mode="r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)

        if reader.fieldnames != EXPECTED_COLUMNS:
            raise ValueError(
                "El encabezado del CSV no coincide con el esperado.\n"
                f"Esperado: {EXPECTED_COLUMNS}\n"
                f"Recibido: {reader.fieldnames}"
            )

        rows = list(reader)

    row_count = len(rows)

    blank_counts: dict[str, int] = {}
    null_like_counts: dict[str, int] = {}
    distinct_counts: dict[str, int] = {}
    top_values: dict[str, list[dict[str, Any]]] = {}

    for column in EXPECTED_COLUMNS:
        values = [row[column] for row in rows]

        blank_counts[column] = sum(not value.strip() for value in values)
        null_like_counts[column] = sum(is_null_like(value) for value in values)
        distinct_counts[column] = len(set(values))

        frequencies = Counter(values)
        top_values[column] = [
            {"value": value, "count": count}
            for value, count in frequencies.most_common(20)
        ]

    # Duplicados exactos
    row_keys = [
        tuple(row[column] for column in EXPECTED_COLUMNS)
        for row in rows
    ]
    row_frequencies = Counter(row_keys)

    exact_duplicate_extra_rows = sum(
        count - 1
        for count in row_frequencies.values()
        if count > 1
    )

    # Análisis de identificadores
    id_frequencies = Counter(row["id"].strip() for row in rows)
    repeated_ids = {
        record_id: count
        for record_id, count in id_frequencies.items()
        if count > 1
    }

    rows_by_id: dict[str, list[dict[str, str]]] = defaultdict(list)

    for row in rows:
        rows_by_id[row["id"].strip()].append(row)

    conflicting_repeated_ids = 0

    for records in rows_by_id.values():
        if len(records) <= 1:
            continue

        distinct_records = {
            tuple(record[column] for column in EXPECTED_COLUMNS)
            for record in records
        }

        if len(distinct_records) > 1:
            conflicting_repeated_ids += 1

    # Episodios
    episode_format_counts: Counter[str] = Counter()
    episode_code_counts: Counter[str] = Counter()

    invalid_episode_tokens: list[dict[str, Any]] = []
    rows_with_repeated_episodes = 0

    for row_number, row in enumerate(rows, start=2):
        episodes, detected_format = parse_episode_values(row["episodios"])
        episode_format_counts[detected_format] += 1

        if len(episodes) != len(set(episodes)):
            rows_with_repeated_episodes += 1

        for episode in episodes:
            if EPISODE_PATTERN.fullmatch(episode):
                episode_code_counts[episode] += 1
            else:
                invalid_episode_tokens.append(
                    {
                        "csv_row": row_number,
                        "id": row["id"],
                        "value": episode,
                    }
                )

    # Fechas
    date_format_counts = Counter(
        classify_date(row["fecha_creacion"])
        for row in rows
    )

    profile: dict[str, Any] = {
        "source_file": CSV_PATH.name,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "structure": {
            "row_count": row_count,
            "column_count": len(EXPECTED_COLUMNS),
            "columns": EXPECTED_COLUMNS,
        },
        "quality": {
            "blank_counts": blank_counts,
            "null_like_counts": null_like_counts,
            "distinct_counts": distinct_counts,
            "exact_duplicate_extra_rows": exact_duplicate_extra_rows,
            "distinct_ids": len(id_frequencies),
            "repeated_id_count": len(repeated_ids),
            "extra_rows_from_repeated_ids": sum(
                count - 1 for count in repeated_ids.values()
            ),
            "conflicting_repeated_id_count": conflicting_repeated_ids,
            "text_anomalies": count_text_anomalies(rows),
        },
        "episodes": {
            "format_counts": dict(episode_format_counts),
            "distinct_valid_episode_codes": len(episode_code_counts),
            "valid_episode_codes": sorted(episode_code_counts),
            "rows_with_repeated_episodes": rows_with_repeated_episodes,
            "invalid_token_count": len(invalid_episode_tokens),
            "invalid_tokens_sample": invalid_episode_tokens[:20],
        },
        "dates": {
            "format_counts": dict(date_format_counts),
        },
        "top_values": top_values,
    }

    return profile


def main() -> None:
    """Punto de entrada del script."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    profile = profile_dataset()

    with PROFILE_PATH.open(mode="w", encoding="utf-8") as output_file:
        json.dump(
            profile,
            output_file,
            ensure_ascii=False,
            indent=2,
        )

    structure = profile["structure"]
    quality = profile["quality"]
    episodes = profile["episodes"]

    print("Perfilado completado correctamente.")
    print(f"Filas leídas: {structure['row_count']}")
    print(f"Columnas: {structure['column_count']}")
    print(f"IDs distintos: {quality['distinct_ids']}")
    print(f"IDs repetidos: {quality['repeated_id_count']}")
    print(
        "Duplicados exactos adicionales: "
        f"{quality['exact_duplicate_extra_rows']}"
    )
    print(
        "IDs repetidos con registros diferentes: "
        f"{quality['conflicting_repeated_id_count']}"
    )
    print(
        "Códigos de episodio distintos: "
        f"{episodes['distinct_valid_episode_codes']}"
    )
    print(f"Informe generado en: {PROFILE_PATH}")


if __name__ == "__main__":
    main()