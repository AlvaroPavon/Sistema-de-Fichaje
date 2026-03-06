from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_file
import sqlite3
from datetime import datetime
import pandas as pd
import io
import random

app = Flask(__name__)

# --- CONFIGURACIÓN ---
app.secret_key = 'super_clave_secreta_para_sesiones'
TOKEN_SECRETO_EMPRESA = "Kiosco_Secreto_2026_XYZ" 
ADMIN_USUARIO = "admin"
ADMIN_PASS = "1234"

def conectar_bd():
    return sqlite3.connect('fichajes_nube.db')

def crear_tabla():
    conexion = conectar_bd()
    cursor = conexion.cursor()
    # Tabla de fichajes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS registro_fichajes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_empleado TEXT NOT NULL,
            fecha_hora TEXT NOT NULL,
            dispositivo_valido TEXT NOT NULL
        )
    ''')
    # Tabla de empleados con columna ACTIVO (1=si, 0=no)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS empleados (
            id_empleado TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            apellidos TEXT NOT NULL,
            activo INTEGER DEFAULT 1
        )
    ''')
    conexion.commit()
    conexion.close()

# --- RUTAS DEL KIOSCO ---
@app.route('/')
def inicio():
    return render_template('index.html')

@app.route('/fichar', methods=['POST'])
def fichar():
    datos = request.json
    id_empleado = datos.get('id_empleado').strip().upper()
    token_recibido = datos.get('token')

    if token_recibido != TOKEN_SECRETO_EMPRESA:
        return jsonify({"error": "Dispositivo no autorizado."}), 403

    conexion = conectar_bd()
    cursor = conexion.cursor()
    # Solo pueden fichar empleados que existan Y estén activos
    cursor.execute("SELECT nombre FROM empleados WHERE id_empleado = ? AND activo = 1", (id_empleado,))
    empleado = cursor.fetchone()

    if not empleado:
        conexion.close()
        return jsonify({"error": "ID no encontrado o empleado no activo."}), 404

    fecha_hora_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO registro_fichajes (id_empleado, fecha_hora, dispositivo_valido) VALUES (?, ?, ?)",
        (id_empleado, fecha_hora_actual, "SI")
    )
    conexion.commit()
    conexion.close()

    return jsonify({"mensaje": f"¡Hola {empleado[0]}! Fichaje registrado."}), 200

# --- RUTAS DEL PANEL ---
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
    # Obtenemos nombre, apellidos y si está activo
    cursor.execute('''
        SELECT f.id_empleado, e.nombre, e.apellidos, f.fecha_hora, e.activo 
        FROM registro_fichajes f
        LEFT JOIN empleados e ON f.id_empleado = e.id_empleado
        ORDER BY f.fecha_hora DESC
    ''')
    fichajes = cursor.fetchall()
    conexion.close()
    
    return render_template('dashboard.html', fichajes=fichajes)

@app.route('/empleados', methods=['GET', 'POST'])
def gestionar_empleados():
    if not session.get('admin_logeado'):
        return redirect(url_for('login'))
        
    conexion = conectar_bd()
    cursor = conexion.cursor()
    error = None
    mensaje = None
    
    if request.method == 'POST':
        nombre = request.form.get('nombre').strip()
        apellidos = request.form.get('apellidos').strip()
        
        if nombre and apellidos:
            prefijo = (nombre[0] + apellidos[0]).upper()
            id_generado = f"{prefijo}{random.randint(100, 999)}"
            try:
                cursor.execute("INSERT INTO empleados (id_empleado, nombre, apellidos, activo) VALUES (?, ?, ?, 1)", 
                               (id_generado, nombre, apellidos))
                conexion.commit()
                mensaje = f"Añadido: {nombre}. ID asignado: {id_generado}"
            except sqlite3.IntegrityError:
                error = "Error al generar ID. Inténtalo de nuevo."
            
    # Solo mostramos en la gestión a los empleados que siguen activos
    cursor.execute("SELECT id_empleado, nombre, apellidos FROM empleados WHERE activo = 1")
    lista_empleados = cursor.fetchall()
    conexion.close()
    return render_template('empleados.html', empleados=lista_empleados, error=error, mensaje=mensaje)

@app.route('/eliminar_empleado/<id_emp>')
def eliminar_empleado(id_emp):
    if not session.get('admin_logeado'):
        return redirect(url_for('login'))
    conexion = conectar_bd()
    cursor = conexion.cursor()
    # BORRADO LÓGICO: Ponemos activo = 0 en lugar de DELETE
    cursor.execute("UPDATE empleados SET activo = 0 WHERE id_empleado = ?", (id_emp,))
    conexion.commit()
    conexion.close()
    return redirect(url_for('gestionar_empleados'))

@app.route('/logout')
def logout():
    session.pop('admin_logeado', None)
    return redirect(url_for('login'))

# --- EXPORTAR EXCEL CON ADVERTENCIA ---
@app.route('/exportar')
def exportar():
    if not session.get('admin_logeado'):
        return redirect(url_for('login'))

    conexion = conectar_bd()
    # SQL para traer los datos y poner (ELIMINADO) si activo es 0
    query = '''
        SELECT f.id_empleado AS [ID Empleado], 
               CASE WHEN e.activo = 0 THEN e.nombre || ' (ELIMINADO)' ELSE e.nombre END AS [Nombre],
               e.apellidos AS [Apellidos], 
               f.fecha_hora AS [Fecha y Hora]
        FROM registro_fichajes f
        LEFT JOIN empleados e ON f.id_empleado = e.id_empleado
        ORDER BY f.fecha_hora ASC
    '''
    df = pd.read_sql_query(query, conexion)
    conexion.close()

    salida = io.BytesIO()
    with pd.ExcelWriter(salida, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte de Fichajes')
    
    salida.seek(0)
    return send_file(salida, download_name="reporte_fichajes_completo.xlsx", as_attachment=True)

if __name__ == '__main__':
    crear_tabla()
    app.run(host='0.0.0.0', port=5000, debug=True)