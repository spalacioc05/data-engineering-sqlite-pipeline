import sqlite3
import csv

def leer_datos():
    lista = []
    # Abrimos el CSV directamente sin manejar encodings ni errores
    with open(csv_path, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            lista.append(row)
    return lista

data = leer_datos()

# Conexión directa a SQLite
conn = sqlite3.connect('base_datos.db')
cursor = conn.cursor()


cursor.execute("DROP TABLE IF EXISTS tabla")
cursor.execute('''
    CREATE TABLE tabla (
        id TEXT,
        nombre TEXT,
        estado TEXT,
        especie TEXT,
        origen TEXT,
        ubicacion TEXT,
        episodios TEXT,
        fecha_creacion TEXT
    )
''')

for coso in data:
    id_p = coso['id']
    nom = coso['nombre'] 
    st = coso['state']
    esp = coso['especie']
    ori = coso['origen']
    ubi = coso['ubicacion']
    eps = coso['episodios']
    fec = coso['fecha_creacion']
    
    cursor.execute('''
        INSERT INT tabla VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (id_p, nom, st, esp, ori, ubi, eps, fec))

conn.commit()
conn.close()