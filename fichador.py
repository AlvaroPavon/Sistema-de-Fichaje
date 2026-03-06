from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_file
import sqlite3
from datetime import datetime
import pandas as pd
import io

app = Flask(__name__)

app.secret_key = 'super_clave_secreta_para_sesiones'
TOKEN_SECRETO_EMPRESA = "Kiosco_Secreto_2026_XYZ" 
ADMIN_USUARIO = "admin"
ADMIN_PASS = "1234"

def conectar_bd():
    return sqlite3.connect('fichajes_nube.db')

def crear_tabla():
    conexion = conectar_bd()
    cursor = conexion.cursor()
    # 1. Tabla original de fichajes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS registro_fichajes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_empleado TEXT NOT NULL,
            fecha_hora TEXT NOT NULL,
            dispositivo_valido TEXT NOT NULL
        )
    ''')
    # 2. NUEVA tabla de empleados
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS empleados (
            id_empleado TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            apellidos TEXT NOT NULL
        )
    ''')
    conexion.commit()
    conexion.close()

@app.route('/')
def inicio():
    return render_template('index.html')

@app.route('/fichar', methods=['POST'])
def fichar():
    datos = request.json
    id_empleado = datos.get('id_empleado')
    token_recibido = datos.get('token')

    if token_recibido != TOKEN_SECRETO_EMPRESA:
        return jsonify({"error": "Dispositivo no autorizado."}), 403

    if not id_empleado:
        return jsonify({"error": "Falta el ID de empleado."}), 400

    fecha_hora_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conexion = conectar_bd()
    cursor = conexion.cursor()
    cursor.execute(
        "INSERT INTO registro_fichajes (id_empleado, fecha_hora, dispositivo_valido) VALUES (?, ?, ?)",
        (id_empleado, fecha_hora_actual, "SI")
    )
    conexion.commit()
    conexion.close()

    return jsonify({"mensaje": "Fichaje registrado con éxito."}), 200

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form.get('usuario') == ADMIN_USUARIO and request.form.get('password') == ADMIN_PASS:
            session['admin_logeado'] = True
            return redirect(url_for('dashboard'))
        else:
            error = "Usuario o contraseña incorrectos."
    return render_template('login.html', error=error)

@app.route('/dashboard')
def dashboard():
    if not session.get('admin_logeado'):
        return redirect(url_for('login'))
        
    conexion = conectar_bd()
    cursor = conexion.cursor()
    
    # 3. Consulta SQL avanzada con LEFT JOIN para unir las dos tablas
    cursor.execute('''
        SELECT f.id_empleado, e.nombre, e.apellidos, f.fecha_hora, f.dispositivo_valido 
        FROM registro_fichajes f
        LEFT JOIN empleados e ON f.id_empleado = e.id_empleado
        ORDER BY f.fecha_hora DESC
    ''')
    fichajes = cursor.fetchall()
    conexion.close()
    
    return render_template('dashboard.html', fichajes=fichajes)

# 4. NUEVA RUTA: Panel para añadir empleados
@app.route('/empleados', methods=['GET', 'POST'])
def gestionar_empleados():
    if not session.get('admin_logeado'):
        return redirect(url_for('login'))
        
    conexion = conectar_bd()
    cursor = conexion.cursor()
    error = None
    mensaje = None
    
    # Si el administrador envía el formulario para añadir un trabajador
    if request.method == 'POST':
        id_emp = request.form.get('id_empleado')
        nombre = request.form.get('nombre')
        apellidos = request.form.get('apellidos')
        
        try:
            cursor.execute("INSERT INTO empleados (id_empleado, nombre, apellidos) VALUES (?, ?, ?)", (id_emp, nombre, apellidos))
            conexion.commit()
            mensaje = "Empleado añadido correctamente."
        except sqlite3.IntegrityError:
            error = "Ese ID de empleado ya existe."
            
    # Sacamos la lista de empleados para mostrarla en pantalla
    cursor.execute("SELECT id_empleado, nombre, apellidos FROM empleados")
    lista_empleados = cursor.fetchall()
    conexion.close()
    
    return render_template('empleados.html', empleados=lista_empleados, error=error, mensaje=mensaje)

@app.route('/logout')
def logout():
    session.pop('admin_logeado', None)
    return redirect(url_for('login'))

@app.route('/exportar')
def exportar():
    if not session.get('admin_logeado'):
        return redirect(url_for('login'))

    conexion = conectar_bd()
    # Actualizamos la exportación para que también incluya los nombres
    df = pd.read_sql_query('''
        SELECT f.id_empleado, e.nombre, e.apellidos, f.fecha_hora, f.dispositivo_valido 
        FROM registro_fichajes f
        LEFT JOIN empleados e ON f.id_empleado = e.id_empleado
    ''', conexion)
    conexion.close()

    salida = io.BytesIO()
    with pd.ExcelWriter(salida, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Fichajes')
    
    salida.seek(0)
    return send_file(salida, download_name="fichajes_completos.xlsx", as_attachment=True)

@app.route('/importar', methods=['POST'])
def importar():
    if not session.get('admin_logeado'):
        return redirect(url_for('login'))

    archivo = request.files.get('archivo_excel')
    if archivo and archivo.filename.endswith('.xlsx'):
        df = pd.read_excel(archivo)
        conexion = conectar_bd()
        cursor = conexion.cursor()
        for index, fila in df.iterrows():
            id_emp = str(fila.iloc[0])
            fecha = str(fila.iloc[1])
            cursor.execute(
                "INSERT INTO registro_fichajes (id_empleado, fecha_hora, dispositivo_valido) VALUES (?, ?, ?)",
                (id_emp, fecha, "IMPORTADO_EXCEL")
            )
        conexion.commit()
        conexion.close()
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    crear_tabla()
    app.run(host='0.0.0.0', port=5000, debug=True)