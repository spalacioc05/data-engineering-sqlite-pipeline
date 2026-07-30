# Justificación de la solución

## 1. Contexto y objetivo

La prueba técnica parte de un archivo CSV con 10.000 registros de personajes y un script inicial defectuoso que intenta cargar la información directamente en una base de datos SQLite.

El objetivo del desarrollo es:

1. Corregir y reorganizar el pipeline recibido.
2. Construir una base de datos transaccional en SQLite.
3. Generar, a partir de la base transaccional, un modelo estrella orientado a análisis.
4. Documentar las decisiones, dificultades, supuestos y validaciones realizadas.

La solución se desarrollará como un proceso batch local, utilizando Python y SQLite, priorizando claridad, trazabilidad, validaciones y facilidad de ejecución.

## 2. Diagnóstico inicial del código recibido

Antes de modificar el pipeline se ejecutó el archivo original para conocer su estado real.

La ejecución produjo el siguiente error:

```text
NameError: name 'csv_path' is not defined
```

Durante la inspección inicial se identificaron los siguientes problemas:

- La variable `csv_path` no está definida.
- El script intenta leer la columna `state`, pero el dataset contiene la columna `estado`.
- La sentencia SQL utiliza `INSERT INT` en lugar de `INSERT INTO`.
- La base de datos generada se llama `base_datos.db`, pero los entregables solicitan `db_transaccional.db` y `db_estrella.db`.
- Se crea una única tabla genérica llamada `tabla`.
- Todos los campos son almacenados como texto.
- No existen claves primarias, claves foráneas, restricciones ni índices.
- No se construye un modelo transaccional.
- No se construye un modelo estrella.
- No hay validaciones de calidad de datos.
- No existe manejo de errores, rollback ni logging.
- No se conserva evidencia de las transformaciones realizadas.
- El proceso no garantiza idempotencia.

La única práctica rescatable del script original es el uso de parámetros en la sentencia `execute`, lo cual evita construir consultas SQL mediante concatenación directa de cadenas.

## 3. Perfilado y calidad de los datos

Se creó el script `profile_dataset.py` para inspeccionar el dataset sin modificarlo y generar un informe reproducible en `results/data_profile.json`.

### 3.1 Estructura del archivo

El archivo contiene:

- 10.000 registros.
- 8 columnas.
- 8.000 identificadores distintos.

Columnas identificadas:

- `id`
- `nombre`
- `estado`
- `especie`
- `origen`
- `ubicacion`
- `episodios`
- `fecha_creacion`

### 3.2 Identificadores y duplicados

Se encontraron:

- 1.766 identificadores repetidos.
- 2.000 filas adicionales asociadas a identificadores repetidos.
- 1.011 filas adicionales que son duplicados exactos.
- 928 identificadores repetidos con registros diferentes.

La existencia de registros diferentes para un mismo identificador indica que algunas filas podrían representar cambios o nuevas observaciones del mismo personaje. Sin embargo, el dataset no incluye una fecha de actualización ni una columna de versión que permita determinar cuál registro es el más reciente.

Por esta razón, no se eliminarán silenciosamente los registros repetidos ni se asumirá que la última fila representa el estado vigente. La solución conservará trazabilidad sobre las observaciones recibidas.

### 3.3 Valores vacíos o equivalentes a nulo

Cantidad de valores vacíos:

- `estado`: 747
- `origen`: 1.211
- `fecha_creacion`: 2.268

Cantidad de valores considerados equivalentes a nulo según los marcadores detectados:

- `estado`: 3.867
- `especie`: 976
- `origen`: 2.478
- `ubicacion`: 2.938
- `fecha_creacion`: 2.268

Entre los marcadores encontrados están:

- Cadena vacía.
- `N/A`
- `NULL`
- `None`
- `---`
- `???`

### 3.4 Variaciones e inconsistencias de texto

Se detectaron múltiples variaciones de mayúsculas, minúsculas, espacios y caracteres añadidos en columnas como `nombre`, `estado` y `especie`.

También se identificaron patrones asociados con problemas de texto:

- 658 apariciones del patrón `Ã`.
- 362 apariciones del patrón `â€`.
- 1.270 apariciones de `&amp;`.
- 311 apariciones de entidades numéricas HTML como `&#39;`.

Estas observaciones indican que será necesario:

- Eliminar espacios externos.
- Homogeneizar categorías.
- Decodificar entidades HTML.
- Corregir únicamente los casos de texto dañado que puedan repararse de forma controlada.
- Conservar el valor original en la capa de trazabilidad.

### 3.5 Episodios

La columna `episodios` utiliza cuatro formatos diferentes:

- Separados por coma: 2.454 filas.
- Separados por barra vertical: 2.536 filas.
- Episodio único: 1.679 filas.
- Lista con sintaxis de Python: 3.331 filas.

Se identificaron 45 códigos de episodio distintos y todos los tokens válidos cumplen el patrón:

```text
SddEdd
```

Ejemplo:

```text
S01E01
```

También existen filas con episodios repetidos dentro del mismo campo. Por esta razón, la información será normalizada y modelada como una relación muchos a muchos entre personajes y episodios.

### 3.6 Fechas

La columna `fecha_creacion` contiene:

- Fechas ISO.
- Timestamps ISO.
- Fechas con formato `DD/MM/YYYY`.
- Fechas con formato `MM-DD-YYYY`.
- Valores vacíos.
- Valores explícitamente inválidos.

Los valores inválidos no serán reemplazados por fechas inventadas. Se conservará el valor original y la fecha normalizada será `NULL` cuando no sea posible interpretarla con una regla documentada.

## 4. Diseño de la base transaccional

Pendiente de completar durante la implementación.

La base transaccional deberá:

- Conservar las 10.000 filas originales en una capa de staging o trazabilidad.
- Evitar pérdida de información.
- Normalizar entidades y relaciones.
- Utilizar claves primarias y foráneas.
- Separar personajes, episodios, catálogos y observaciones.
- Registrar métricas básicas de ejecución del pipeline.
- Permitir reconstruir el origen de cada registro transformado.

## 5. Diseño del modelo estrella

Pendiente de completar durante la implementación.

El modelo estrella se construirá exclusivamente a partir de `db_transaccional.db`.

Antes de implementarlo se definirá de forma explícita el grano de la tabla de hechos. La propuesta inicial es que una fila represente una relación única entre un personaje y un episodio.

## 6. Transformaciones realizadas

Pendiente de completar durante la implementación.

Las transformaciones previstas incluyen:

- Normalización de espacios.
- Homogeneización de categorías.
- Conversión controlada de marcadores de ausencia a `NULL`.
- Decodificación de entidades HTML.
- Reparación controlada de texto cuando sea posible.
- Parseo de episodios desde sus distintos formatos.
- Eliminación de episodios repetidos dentro de una misma observación.
- Conversión de fechas válidas a un formato estándar.
- Conservación del valor original para fines de trazabilidad.

## 7. Validaciones efectuadas

Hasta el momento se realizaron las siguientes validaciones:

- Verificación de existencia del archivo CSV.
- Validación del encabezado esperado.
- Conteo de filas y columnas.
- Conteo de valores vacíos.
- Conteo de valores equivalentes a nulo.
- Conteo de valores distintos.
- Identificación de duplicados exactos.
- Identificación de identificadores repetidos.
- Identificación de registros repetidos con diferencias.
- Detección de formatos de episodios.
- Validación del patrón de códigos de episodio.
- Clasificación de formatos de fecha.
- Detección de patrones de texto posiblemente dañados.

El informe generado se conserva en:

```text
results/data_profile.json
```

## 8. Supuestos y dificultades

### 8.1 Identificadores repetidos

No se asume que la última fila sea la versión vigente de un personaje, porque el dataset no contiene una fecha de actualización ni un número de versión.

### 8.2 Valores desconocidos y valores nulos

Se distinguirá, cuando sea posible, entre:

- Un valor conocido como `Unknown`.
- Un marcador de ausencia como `NULL`, `N/A`, `None`, `---` o una cadena vacía.

### 8.3 Fechas ambiguas

Se aplicarán reglas de interpretación según el separador y los patrones encontrados en el dataset. Los supuestos utilizados quedarán documentados y las fechas que no puedan interpretarse de forma segura se conservarán como nulas en la versión normalizada.

### 8.4 Texto dañado

No se eliminarán caracteres de manera indiscriminada. Las correcciones se aplicarán únicamente cuando exista una regla clara y reproducible.

## 9. Mejoras para una versión productiva

Con más tiempo y en un entorno productivo se considerarían las siguientes mejoras:

- Pruebas unitarias y de integración.
- Registro estructurado de errores y métricas.
- Archivo de configuración externo.
- Reglas de calidad parametrizables.
- Ejecuciones incrementales.
- Control formal de esquemas.
- Gestión de secretos si existieran fuentes externas.
- Automatización mediante integración continua.
- Observabilidad y alertas.
- Catálogo de datos y linaje más detallado.
- Estrategia de recuperación ante fallos.
- Separación entre ambientes de desarrollo, pruebas y producción.
