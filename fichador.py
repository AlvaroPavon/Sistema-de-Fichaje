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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS registro_fichajes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_empleado TEXT NOT NULL,
            fecha_hora TEXT NOT NULL,
            tipo_fichaje TEXT NOT NULL,
            dispositivo_valido TEXT NOT NULL
        )
    ''')
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
    tipo_fichaje = datos.get('tipo')

    if token_recibido != TOKEN_SECRETO_EMPRESA:
        return jsonify({"error": "Dispositivo no autorizado."}), 403

    if tipo_fichaje not in ["ENTRADA", "SALIDA"]:
        return jsonify({"error": "Tipo de fichaje no válido."}), 400

    conexion = conectar_bd()
    cursor = conexion.cursor()
    cursor.execute("SELECT nombre FROM empleados WHERE id_empleado = ? AND activo = 1", (id_empleado,))
    empleado = cursor.fetchone()

    if not empleado:
        conexion.close()
        return jsonify({"error": "ID no encontrado o empleado no activo."}), 404

    # --- NUEVA LÓGICA DE PROTECCIÓN DE ESTADO ---
    # Buscamos cuál fue el ÚLTIMO fichaje de esta persona
    cursor.execute("SELECT tipo_fichaje FROM registro_fichajes WHERE id_empleado = ? ORDER BY fecha_hora DESC LIMIT 1", (id_empleado,))
    ultimo_fichaje = cursor.fetchone()

    if tipo_fichaje == "ENTRADA":
        # Si quiere entrar, su último registro no puede ser otra ENTRADA
        if ultimo_fichaje and ultimo_fichaje[0] == "ENTRADA":
            conexion.close()
            return jsonify({"error": "Ya tienes un turno abierto. Registra tu salida primero."}), 400
            
    elif tipo_fichaje == "SALIDA":
        # Si quiere salir, su último registro DEBE ser obligatoriamente una ENTRADA
        if not ultimo_fichaje or ultimo_fichaje[0] == "SALIDA":
            conexion.close()
            return jsonify({"error": "No tienes ningún turno abierto. Registra tu entrada primero."}), 400
    # --------------------------------------------

    fecha_hora_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO registro_fichajes (id_empleado, fecha_hora, tipo_fichaje, dispositivo_valido) VALUES (?, ?, ?, ?)",
        (id_empleado, fecha_hora_actual, tipo_fichaje, "SI")
    )
    conexion.commit()
    conexion.close()

    accion = "Entrada registrada" if tipo_fichaje == "ENTRADA" else "Salida registrada"
    return jsonify({"mensaje": f"¡Hola {empleado[0]}! {accion} correctamente."}), 200

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
    cursor.execute('''
        SELECT f.id_empleado, e.nombre, e.apellidos, f.fecha_hora, f.tipo_fichaje, e.activo 
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
                error = "Error al generar ID."
            
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
    cursor.execute("UPDATE empleados SET activo = 0 WHERE id_empleado = ?", (id_emp,))
    conexion.commit()
    conexion.close()
    return redirect(url_for('gestionar_empleados'))

@app.route('/empleado/<id_emp>')
def detalle_empleado(id_emp):
    if not session.get('admin_logeado'):
        return redirect(url_for('login'))
        
    conexion = conectar_bd()
    cursor = conexion.cursor()
    cursor.execute("SELECT nombre, apellidos, activo FROM empleados WHERE id_empleado = ?", (id_emp,))
    empleado = cursor.fetchone()
    
    if not empleado:
        conexion.close()
        return redirect(url_for('gestionar_empleados')) 
        
    cursor.execute("SELECT fecha_hora, tipo_fichaje FROM registro_fichajes WHERE id_empleado = ? ORDER BY fecha_hora ASC", (id_emp,))
    registros = cursor.fetchall()
    conexion.close()
    
    historial = []
    entrada_tmp = None
    
    for fecha_hora, tipo in registros:
        if tipo == 'ENTRADA':
            entrada_tmp = fecha_hora
        elif tipo == 'SALIDA':
            if entrada_tmp:
                fmt = "%Y-%m-%d %H:%M:%S"
                t1 = datetime.strptime(entrada_tmp, fmt)
                t2 = datetime.strptime(fecha_hora, fmt)
                segundos = (t2 - t1).total_seconds()
                
                horas = int(segundos // 3600)
                minutos = int((segundos % 3600) // 60)
                segs = int(segundos % 60)
                
                historial.append({
                    'fecha': t1.strftime("%d/%m/%Y"),
                    'entrada': t1.strftime("%H:%M:%S"),
                    'salida': t2.strftime("%H:%M:%S"),
                    'total': f"{horas:02d}h {minutos:02d}m {segs:02d}s"
                })
                entrada_tmp = None 
                
    if entrada_tmp:
        t1 = datetime.strptime(entrada_tmp, "%Y-%m-%d %H:%M:%S")
        historial.append({
            'fecha': t1.strftime("%d/%m/%Y"),
            'entrada': t1.strftime("%H:%M:%S"),
            'salida': 'Trabajando...',
            'total': '---'
        })
        
    historial.reverse()
    return render_template('detalle_empleado.html', empleado=empleado, id_emp=id_emp, historial=historial)

# --- RUTAS DEL CALENDARIO ---
@app.route('/calendario')
def calendario():
    if not session.get('admin_logeado'):
        return redirect(url_for('login'))
    return render_template('calendario.html')

@app.route('/api/eventos')
def api_eventos():
    if not session.get('admin_logeado'):
        return jsonify([])

    conexion = conectar_bd()
    cursor = conexion.cursor()
    cursor.execute('''
        SELECT f.id_empleado, e.nombre, f.tipo_fichaje, f.fecha_hora 
        FROM registro_fichajes f
        LEFT JOIN empleados e ON f.id_empleado = e.id_empleado
        ORDER BY f.fecha_hora ASC
    ''')
    registros = cursor.fetchall()
    conexion.close()

    eventos = []
    estado_empleados = {} 
    totales_diarios = {} 
    colores = ['#3498db', '#e74c3c', '#2ecc71', '#9b59b6', '#f39c12', '#1abc9c', '#e67e22', '#34495e']

    for emp_id, nombre, tipo, fecha in registros:
        nombre_mostrar = nombre if nombre else "Desconocido"
        hash_id = sum(ord(c) for c in emp_id)
        color = colores[hash_id % len(colores)]
        
        if tipo == 'ENTRADA':
            estado_empleados[emp_id] = {'nombre': nombre_mostrar, 'entrada': fecha, 'color': color}
        elif tipo == 'SALIDA':
            if emp_id in estado_empleados:
                info_entrada = estado_empleados[emp_id]
                start = info_entrada['entrada']
                end = fecha
                
                eventos.append({
                    "title": f"{nombre_mostrar}",
                    "start": start.replace(" ", "T"),
                    "end": end.replace(" ", "T"),
                    "color": info_entrada['color']
                })
                
                fmt = "%Y-%m-%d %H:%M:%S"
                t1 = datetime.strptime(start, fmt)
                t2 = datetime.strptime(end, fmt)
                segundos_turno = (t2 - t1).total_seconds()
                
                dia_str = start.split(" ")[0] 
                if dia_str not in totales_diarios:
                    totales_diarios[dia_str] = {}
                if emp_id not in totales_diarios[dia_str]:
                    totales_diarios[dia_str][emp_id] = {'nombre': nombre_mostrar, 'color': color, 'segundos': 0}
                    
                totales_diarios[dia_str][emp_id]['segundos'] += segundos_turno
                del estado_empleados[emp_id]
                
    for emp_id, info in estado_empleados.items():
        eventos.append({
            "title": f"{info['nombre']} (Trabajando...)",
            "start": info['entrada'].replace(" ", "T"),
            "color": info['color']
        })

    for dia, empleados_dia in totales_diarios.items():
        for emp_id, datos in empleados_dia.items():
            segundos_totales = int(datos['segundos'])
            horas = segundos_totales // 3600
            minutos = (segundos_totales % 3600) // 60
            segundos = segundos_totales % 60
            tiempo_formateado = f"{horas:02d}h {minutos:02d}m {segundos:02d}s"
            
            eventos.append({
                "title": f"⏱️ Total {datos['nombre']}: {tiempo_formateado}",
                "start": dia, 
                "color": datos['color'],
                "allDay": True 
            })

    return jsonify(eventos)

@app.route('/logout')
def logout():
    session.pop('admin_logeado', None)
    return redirect(url_for('login'))

# --- EXPORTAR / IMPORTAR ---
@app.route('/exportar')
def exportar():
    if not session.get('admin_logeado'):
        return redirect(url_for('login'))

    conexion = conectar_bd()
    query = '''
        SELECT f.id_empleado AS [ID Empleado], 
               CASE WHEN e.activo = 0 THEN e.nombre || ' (ELIMINADO)' ELSE e.nombre END AS [Nombre],
               e.apellidos AS [Apellidos], 
               f.tipo_fichaje AS [Tipo],
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
            tipo = str(fila.iloc[2]).upper() if len(fila.columns) > 2 else "DESCONOCIDO"
            cursor.execute(
                "INSERT INTO registro_fichajes (id_empleado, fecha_hora, tipo_fichaje, dispositivo_valido) VALUES (?, ?, ?, ?)",
                (id_emp, fecha, tipo, "IMPORTADO_EXCEL")
            )
        conexion.commit()
        conexion.close()
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    crear_tabla()
    app.run(host='0.0.0.0', port=5000, debug=True)