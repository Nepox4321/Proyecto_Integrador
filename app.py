# -*- coding: utf-8 -*-
"""AutoNova · Aplicación Flask

Sirve los templates Jinja conectados a la base de datos MySQL `autonova`.
- La conexión se configura en config.py (usuario root, host localhost).
- La BD se inicializa al arrancar (db.init_app + create_all con datos semilla).
Ejecutar:  python app.py

Mapa de lectura:
    1) configuración y datos fallback
    2) rutas publicas y checkout
    3) cuenta de usuario
    4) panel administrativo
    5) calculo del semaforo y reglas IoT
    6) API consumida por el ESP32

Las reglas de estados y temporizador estan documentadas en
docs/REGLAS_NEGOCIO.md; el contrato HTTP esta en docs/API_ESP32.md.
"""
import time
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, jsonify)
from sqlalchemy import func, inspect, or_, text
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from models import (db, Usuario, Sucursal, Vehiculo, Reserva, Pago, Venta,
                    ModuloESP32, TelemetriaESP32, ComandoESP32, SemaforoFoco,
                    resumir_transacciones)

app = Flask(__name__)
app.config.from_object(Config)

# Vincular el ORM a Flask: desde aquí db.session usa la configuración MySQL.
db.init_app(app)


@app.after_request
def add_no_cache_headers(resp):
    """Evita que el navegador/proxy cacheen respuestas dinámicas
    (páginas y API), de modo que el panel siempre muestre datos
    actualizados de la base sin necesidad de saltar la caché."""
    resp.headers['Cache-Control'] = ('no-store, no-cache, must-revalidate, '
                                     'max-age=0')
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


# ---------------------------------------------------------------------------
# Datos fallback: se muestran si MySQL está vacío o temporalmente inaccesible.
# ---------------------------------------------------------------------------
SAMPLE_VEHICULOS = [
    {'id': 1, 'marca': 'Mercedes-Benz', 'modelo': 'Clase E 400', 'placa': 'MEC-72-11',
     'categoria': 'elegante', 'tarifa_dia': 128, 'imagen': 'vehiculo1.jpg', 'estado': 'disponible'},
    {'id': 2, 'marca': 'Lamborghini', 'modelo': 'Huracán EVO', 'placa': 'LMB-01-99',
     'categoria': 'deportivo', 'tarifa_dia': 320, 'imagen': 'lambo.jpg', 'estado': 'disponible'},
    {'id': 3, 'marca': 'Porsche', 'modelo': '911 Carrera', 'placa': 'PRS-23-10',
     'categoria': 'deportivo', 'tarifa_dia': 450, 'imagen': 'mercedes.jpg', 'estado': 'alquilado'},
    {'id': 4, 'marca': 'BMW', 'modelo': 'X5 M', 'placa': 'BMW-88-77',
     'categoria': 'suv', 'tarifa_dia': 260, 'imagen': 'vehiculo4.jpg', 'estado': 'disponible'},
    {'id': 5, 'marca': 'Tesla', 'modelo': 'Model S', 'placa': 'TSL-00-EV',
     'categoria': 'electrico', 'tarifa_dia': 340, 'imagen': 'vehiculo5.jpg', 'estado': 'reservada'},
    {'id': 6, 'marca': 'Audi', 'modelo': 'Q7', 'placa': 'ADQ-31-24',
     'categoria': 'suv', 'tarifa_dia': 240, 'imagen': 'vehiculo6.jpg', 'estado': 'disponible'},
]

SAMPLE_MODULOS = [
    {'id': 1, 'nombre': 'Módulo ESP32-001', 'codigo': 'ESP32-AUTONOVA-001', 'estado': 'conectado'},
    {'id': 2, 'nombre': 'Módulo ESP32-002', 'codigo': 'ESP32-AUTONOVA-002', 'estado': 'esperando'},
    {'id': 3, 'nombre': 'Módulo ESP32-003', 'codigo': 'ESP32-AUTONOVA-003', 'estado': 'apagado'},
]

# ---------------------------------------------------------------------------
# Cuenta administradora demo (se crea/actualiza automáticamente al arrancar)
# ---------------------------------------------------------------------------
ADMIN_EMAIL = 'admin@autonova.mx'
ADMIN_PASSWORD = 'admin123'


def _es_hash_valido(hash_str):
    """True si parece un hash de werkzeug (formato metodo$salt$hash)."""
    return bool(hash_str) and '$' in hash_str


def ensure_admin_user():
    """Garantiza la cuenta admin demo y credenciales válidas para admins heredados."""
    try:
        admin = db.session.query(Usuario).filter_by(email=ADMIN_EMAIL).first()
        if admin is None:
            db.session.add(Usuario(
                nombre='Admin', apellidos='AutoNova', email=ADMIN_EMAIL,
                password_hash=generate_password_hash(ADMIN_PASSWORD),
                rol='admin', licencia='ADM-001', es_activo=True))
            db.session.commit()
            print(f'[AutoNova] Cuenta admin creada: {ADMIN_EMAIL} / {ADMIN_PASSWORD}')
        elif not check_password_hash(admin.password_hash or '', ADMIN_PASSWORD):
            # Compatibilidad: actualiza el admin antiguo sin contraseña válida.
            admin.password_hash = generate_password_hash(ADMIN_PASSWORD)
            admin.rol = 'admin'
            admin.es_activo = True
            db.session.commit()
            print('[AutoNova] Contraseña de la cuenta admin actualizada.')

        # Admins heredados del dump original con hash genérico (sin "$")
        # reciben la contraseña demo para que puedan entrar al panel.
        for a in (db.session.query(Usuario)
                  .filter(Usuario.rol == 'admin', Usuario.email != ADMIN_EMAIL)
                  .all()):
            if not _es_hash_valido(a.password_hash):
                a.password_hash = generate_password_hash(ADMIN_PASSWORD)
                a.es_activo = True
                print(f'[AutoNova] Admin heredado {a.email}: '
                      f'contraseña fijada a {ADMIN_PASSWORD}')
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        print(f'[AutoNova] AVISO: no se pudo asegurar la cuenta admin: {exc}')


# ------------------- Variables de contexto globales -------------------
@app.context_processor
def inject_globals():
    """Expone datos de sesión y configuración común a todas las plantillas."""
    return {
        'session_user': session.get('nombre'),
        'session_email': session.get('email'),
        'session_rol': session.get('rol'),
        'esp_endpoint': app.config.get('ESP32_ENDPOINT'),
        'now_ms': lambda: int(time.time() * 1000),
    }


def _asegurar_semaforos():
    """Crea una fila en `semaforo_focos` para cada módulo registrado.

    Se ejecuta al arrancar y garantiza que la página siempre pueda leer
    y cambiar el estado de los focos desde la base, sin depender del Arduino.
    """
    try:
        modulos = db.session.query(ModuloESP32).all()
        for m in modulos:
            row = (db.session.query(SemaforoFoco)
                   .filter_by(modulo_id=m.id).first())
            if row is None:
                db.session.add(SemaforoFoco(modulo_id=m.id,
                                            foco_activo='verde', modo='auto'))
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        print(f'[AutoNova] AVISO: no se pudieron asegurar los semáforos: {exc}')


def _asegurar_columnas_reserva():
    """Añade columnas nuevas de Reserva a instalaciones ya existentes."""
    columnas = {col['name'] for col in inspect(db.engine).get_columns('reservas')}
    if 'inicio_alquiler' not in columnas:
        with db.engine.begin() as conexion:
            conexion.execute(text(
                'ALTER TABLE reservas ADD COLUMN inicio_alquiler DATETIME NULL'))


# ------------------- Inicialización de la base de datos -------------------
def init_database():
    """Crea las tablas si no existen cuando entra en contexto de la app."""
    with app.app_context():
        try:
            # SQLAlchemy crea las tablas declaradas en models.py que falten.
            db.create_all()
            _asegurar_columnas_reserva()
            _asegurar_semaforos()
            print('[AutoNova] Base de datos conectada / tablas aseguradas.')
            ensure_admin_user()
            return True
        except Exception as exc:
            # No frenamos el arranque: las vistas funcionan con datos de ejemplo.
            print(f'[AutoNova] AVISO: no se pudo conectar a la base de datos: {exc}')
            db.session.rollback()
            return False
# ------------------------------- Rutas web --------------------------------
# Cada ruta recibe HTTP, consulta modelos ORM y devuelve una plantilla o JSON.
@app.route('/')
def inicio():
    """Inicio: consulta la tabla vehiculos y muestra los disponibles."""
    vehiculos, total = [], 0
    total_usuarios = 0
    try:
        vehiculos = (db.session.query(Vehiculo)
                     .order_by(Vehiculo.veces_alquilado.desc()).limit(6).all())
        total = db.session.query(func.count(Vehiculo.id)).scalar() or 0
        total_usuarios = (db.session.query(func.count(Usuario.id_usuario)).scalar()) or 0
    except Exception:
        vehiculos, total = [], 0

    destacados = vehiculos if vehiculos else SAMPLE_VEHICULOS
    return render_template('inicio.html',
                           destacados=destacados,
                           total_vehiculos=total or len(SAMPLE_VEHICULOS),
                           total_usuarios=total_usuarios)


@app.route('/doblaje')
def doblaje():
    """Editor local para sincronizar una narracion con un video."""
    return render_template('doblaje.html')


@app.route('/flota')
def catalogo():
    """Catálogo completo de la flota."""
    flota = []
    max_veces = 0
    try:
        flota = db.session.query(Vehiculo).order_by(Vehiculo.marca).all()
        max_veces = max([v.veces_alquilado or 0 for v in flota], default=0)
    except Exception:
        flota = SAMPLE_VEHICULOS
    return render_template('catalogo.html', flota=flota, max_veces=max_veces)


def _usuario_actual():
    """Usuario de la BD si la sesión corresponde a una cuenta real y activa;
    None en cualquier otro caso (sin sesión, cuenta borrada o desactivada)."""
    email = session.get('email')
    if not email:
        return None
    try:
        u = db.session.query(Usuario).filter_by(email=email).first()
    except Exception:
        return None
    if u is None or not u.es_activo:
        return None
    return u


def _destino_post_login():
    """Tras iniciar sesión o registrarse: retoma un alquiler pendiente si lo había."""
    pend = session.pop('reserva_pendiente', None)
    if pend and pend.get('id'):
        return url_for('checkout', id=pend['id'],
                       fecha_inicio=pend.get('fecha_inicio') or None,
                       fecha_fin=pend.get('fecha_fin') or None)
    return url_for('admin') if session.get('rol') == 'admin' else url_for('inicio')


@app.route('/vehiculo/<int:id>')
def vehiculo(id):
    """Muestra el detalle de una unidad de la flota."""
    v = None
    try:
        v = db.session.get(Vehiculo, id)
    except Exception:
        v = None
    return render_template('vehiculo.html', v=v, id=id)


@app.route('/checkout/<int:id>', methods=['GET', 'POST'])
def checkout(id):
    """Checkout del alquiler.

    Exige una cuenta registrada y activa en la BD: si no hay sesión válida,
    guarda lo capturado y envía a login/registro para continuar después.
    La reserva se registra SIEMPRE al usuario de la sesión.
    """
    user = _usuario_actual()
    if user is None:
        if request.method == 'GET':
            f_ini = request.args.get('fecha_inicio')
            f_fin = request.args.get('fecha_fin')
            if f_ini or f_fin:
                session['reserva_pendiente'] = {'id': id, 'fecha_inicio': f_ini,
                                                'fecha_fin': f_fin}
        flash('Necesitas una cuenta para alquilar. Inicia sesión o regístrate '
              'para continuar con tu reserva.', 'error')
        return redirect(url_for('login'))

    v = None
    try:
        v = db.session.get(Vehiculo, id)
    except Exception:
        v = None
    if v is None:
        flash('Vehículo no encontrado en la flota.', 'error')
        return redirect(url_for('catalogo'))

    if request.method == 'POST':
        from datetime import date

        # --- Validación de fechas (como un sitio de renta real) ---
        try:
            f1 = date.fromisoformat(request.form.get('fecha_inicio') or '')
            f2 = date.fromisoformat(request.form.get('fecha_fin') or '')
        except ValueError:
            flash('Selecciona fechas de inicio y fin válidas.', 'error')
            return redirect(url_for('checkout', id=id))
        if f1 < date.today():
            flash('La fecha de inicio no puede ser anterior a hoy.', 'error')
            return redirect(url_for('checkout', id=id))
        if f2 < f1:
            flash('La fecha de fin no puede ser anterior a la de inicio.', 'error')
            return redirect(url_for('checkout', id=id))
        dias = max((f2 - f1).days, 1)
        tarifa = float(v.tarifa_dia) if v.tarifa_dia else 0.0
        total = round(dias * tarifa, 2)

        # --- La reserva se registra a la cuenta con sesión iniciada ---
        try:
            # Completa el perfil registrado si faltaban datos
            if not user.telefono and (request.form.get('telefono') or '').strip():
                user.telefono = request.form.get('telefono').strip()
            if not user.licencia and (request.form.get('licencia') or '').strip():
                user.licencia = request.form.get('licencia').strip()

            reserva = Reserva(
                usuario_id=user.id_usuario,
                vehiculo_id=v.id,
                sucursal_id=v.sucursal_id,
                fecha_inicio=f1,
                fecha_fin=f2,
                tarifa_dia=tarifa,
                total=total,
                tipo='alquiler',
                estado='pendiente',
            )
            db.session.add(reserva)
            v.marcar_reservado()
            v.veces_alquilado = (v.veces_alquilado or 0) + 1
            db.session.commit()
            codigo = reserva.id
        except Exception as exc:
            db.session.rollback()
            print(f'[AutoNova] AVISO: no se pudo guardar la reserva: {exc}')
            flash('No se pudo registrar tu reserva. Intenta de nuevo.', 'error')
            return redirect(url_for('checkout', id=id))

        session.pop('reserva_pendiente', None)
        nombre_completo = f'{user.nombre} {user.apellidos or ""}'.strip()
        session['reserva'] = {
            'nombre': nombre_completo,
            'email': user.email,
            'vehiculo': f'{v.marca} {v.modelo}',
            'fecha_inicio': request.form.get('fecha_inicio'),
            'fecha_fin': request.form.get('fecha_fin'),
            'total': f'{total:.2f}',
            'codigo': reserva.codigo_corto(),
        }
        flash(f'¡Reserva {reserva.codigo_corto()} registrada en la base de '
              f'datos a tu cuenta, {nombre_completo}!', 'ok')
        return redirect(url_for('confirmacion'))

    # GET: checkout con los datos de la cuenta precargados
    session.pop('reserva_pendiente', None)
    return render_template('checkout.html', v=v, id=id, user=user)


@app.route('/confirmacion')
def confirmacion():
    """Muestra los datos de la última reserva confirmada en la sesión."""
    d = session.get('reserva') or {}
    if not d:
        flash('No hay ninguna reserva reciente para mostrar.', 'error')
        return redirect(url_for('inicio'))
    return render_template('confirmacion.html', **d)


# ------------------- Mi Perfil (cuenta del usuario) -------------------
_MESES_ES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun',
             'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
ESTADOS_RENTA_ACTIVA = ('pendiente', 'confirmada', 'en_uso')


def _fmt_fecha(d):
    """Fecha corta en español: '12 sep 2025' (formato del diseño)."""
    if not d:
        return '—'
    return f'{d.day} {_MESES_ES[d.month - 1]} {d.year}'


@app.route('/perfil')
def perfil():
    """Mi Perfil: datos de la cuenta, renta activa e historial de reservas."""
    user = _usuario_actual()
    if user is None:
        flash('Inicia sesión para ver tu perfil y tus reservas.', 'info')
        return redirect(url_for('login'))

    from datetime import date
    hoy = date.today()

    try:
        reservas = (db.session.query(Reserva)
                    .filter_by(usuario_id=user.id_usuario)
                    .order_by(Reserva.fecha_inicio.desc(), Reserva.id.desc())
                    .all())
    except Exception:
        reservas = []

    # Renta activa: la más reciente sin completar/cancelar
    activa = next((r for r in reservas if r.estado in ESTADOS_RENTA_ACTIVA), None)
    historial = [r for r in reservas if r is not activa]

    activa_d = None
    if activa is not None:
        v = activa.vehiculo
        try:
            suc = (db.session.get(Sucursal, activa.sucursal_id)
                   if activa.sucursal_id else None)
        except Exception:
            suc = None
        dias_tot = max((activa.fecha_fin - activa.fecha_inicio).days, 1)
        dias = min(max((hoy - activa.fecha_inicio).days, 0), dias_tot)
        activa_d = {
            'r': activa,
            'codigo': activa.codigo_corto(),
            'titulo': (f'{v.marca} {v.anio}' if v and v.anio
                       else (v.marca if v else 'Vehículo')).upper(),
            'cat': (v.categoria.capitalize() if v and v.categoria else ''),
            'modelo': v.modelo if v else '—',
            'imagen': v.imagen if v else 'vehiculo1.jpg',
            'placa': (v.placa if v else '') or '',
            'recogida': _fmt_fecha(activa.fecha_inicio),
            'devolucion': _fmt_fecha(activa.fecha_fin),
            'lugar': (f'{suc.nombre} · {suc.ciudad}' if suc else 'Por confirmar'),
            'dias_tot': dias_tot,
            'dias': dias,
            'pct': int(round(100.0 * dias / dias_tot)),
            'puede_cancelar': activa.estado in ('pendiente', 'confirmada'),
        }

    hist = []
    for r in historial:
        v = r.vehiculo
        dias = max((r.fecha_fin - r.fecha_inicio).days, 1)
        etiquetas = {'completada': ('Completada', 'ok'),
                     'cancelada': ('Cancelada', 'bad'),
                     'pendiente': ('Activa', 'warn'),
                     'confirmada': ('Confirmada', 'warn'),
                     'en_uso': ('En curso', 'warn')}
        label, clase = etiquetas.get(r.estado, (r.estado or '—', 'warn'))
        hist.append({
            'r': r,
            'codigo': r.codigo_corto(),
            'marca': v.marca if v else '—',
            'modelo': v.modelo if v else '',
            'imagen': v.imagen if v else 'vehiculo1.jpg',
            'periodo': f'{_fmt_fecha(r.fecha_inicio)} → {_fmt_fecha(r.fecha_fin)}',
            'dias': dias,
            'total': float(r.total or 0),
            'estado_label': label,
            'estado_clase': clase,
        })

    no_canceladas = [r for r in reservas if r.estado != 'cancelada']
    stats = {
        'rentas': len(no_canceladas),
        'rating': 4.5 + (user.id_usuario % 6) / 10.0,  # determinista (sin columna en BD)
        'gastado': sum(float(r.total or 0) for r in no_canceladas),
        'miembro': (user.creado_en.strftime('%Y') if user.creado_en
                    else str(hoy.year)),
        'activas': 1 if activa is not None else 0,
        'completadas': sum(1 for r in reservas if r.estado == 'completada'),
    }

    return render_template('perfil.html', user=user, activa=activa_d,
                           historial=hist, stats=stats)


@app.route('/perfil/exportar')
def perfil_exportar():
    """Descarga el historial de reservas del usuario en CSV."""
    user = _usuario_actual()
    if user is None:
        flash('Inicia sesión para ver tu perfil y tus reservas.', 'info')
        return redirect(url_for('login'))

    filas = ['Reserva,Vehiculo,Inicio,Fin,Dias,Tarifa_dia,Total,Estado']
    try:
        rs = (db.session.query(Reserva)
              .filter_by(usuario_id=user.id_usuario)
              .order_by(Reserva.id).all())
    except Exception:
        rs = []
    for r in rs:
        v = r.vehiculo
        dias = (max((r.fecha_fin - r.fecha_inicio).days, 1)
                if r.fecha_inicio and r.fecha_fin else '')
        filas.append(','.join([
            r.codigo_corto(),
            (f'{v.marca} {v.modelo}' if v else ''),
            str(r.fecha_inicio or ''), str(r.fecha_fin or ''),
            str(dias), f'{float(r.tarifa_dia or 0):.2f}',
            f'{float(r.total or 0):.2f}', r.estado or '',
        ]))

    from flask import Response
    return Response('\n'.join(filas), mimetype='text/csv', headers={
        'Content-Disposition':
            'attachment; filename=reservas_autonova.csv'})


@app.route('/perfil/reserva/<int:rid>/cancelar', methods=['POST'])
def perfil_cancelar(rid):
    """Cancela una reserva propia desde Mi Perfil (pendiente/confirmada)."""
    user = _usuario_actual()
    if user is None:
        flash('Inicia sesión para administrar tus reservas.', 'info')
        return redirect(url_for('login'))

    try:
        r = db.session.get(Reserva, rid)
    except Exception:
        r = None
    if r is None or r.usuario_id != user.id_usuario:
        flash('No se encontró la reserva en tu cuenta.', 'error')
        return redirect(url_for('perfil'))
    if r.estado not in ('pendiente', 'confirmada'):
        flash(f'La reserva {r.codigo_corto()} ya no puede cancelarse '
              f'(estado actual: {r.estado}).', 'error')
        return redirect(url_for('perfil'))

    try:
        r.cancelar()
        v = r.vehiculo
        if v is not None and v.estado == 'reservada':
            v.liberar()
        db.session.commit()
        flash(f'Reserva {r.codigo_corto()} cancelada correctamente.', 'ok')
    except Exception:
        db.session.rollback()
        flash('No se pudo cancelar la reserva. Intenta de nuevo.', 'error')
    return redirect(url_for('perfil'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    # Autenticación: consulta el usuario, verifica el hash y crea la sesión.
    """Inicio de sesión: valida contra la tabla `usuarios` (password hasheado)."""
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''

        usuario = None
        try:
            usuario = db.session.query(Usuario).filter_by(email=email).first()
        except Exception:
            usuario = None

        if usuario is None:
            flash('Correo o contraseña incorrectos.', 'error')
            return render_template('login.html'), 401

        # Cuentas heredadas del dump original con hash genérico (sin "$"):
        # el primer login guarda la contraseña que el usuario escriba.
        if not _es_hash_valido(usuario.password_hash):
            if not password:
                flash('Escribe una contraseña para activar tu cuenta.', 'error')
                return render_template('login.html'), 401
            usuario.password_hash = generate_password_hash(password)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
            session['nombre'] = usuario.nombre
            session['email'] = usuario.email
            session['rol'] = usuario.rol or 'cliente'
            flash(f'Cuenta activada: tu contraseña quedó guardada. '
                  f'¡Bienvenido, {usuario.nombre}!', 'ok')
            return redirect(_destino_post_login())

        try:
            password_ok = check_password_hash(usuario.password_hash or '', password)
        except Exception:
            password_ok = False

        if not password_ok:
            flash('Correo o contraseña incorrectos.', 'error')
            return render_template('login.html'), 401
        if not usuario.es_activo:
            flash('Tu cuenta está desactivada. Contacta al administrador.', 'error')
            return render_template('login.html'), 403

        session['nombre'] = usuario.nombre
        session['email'] = usuario.email
        session['rol'] = usuario.rol or 'cliente'
        try:
            usuario.ultimo_acceso = datetime.utcnow()
            db.session.commit()
        except Exception:
            db.session.rollback()

        flash(f'Sesión iniciada para {usuario.nombre}', 'ok')
        return redirect(_destino_post_login())
    return render_template('login.html')


@app.route('/registro', methods=['GET', 'POST'])
def registro():
    # Registro: valida datos del formulario y persiste un nuevo Usuario.
    """Registro: crea un usuario real (rol cliente) en la tabla `usuarios`."""
    if request.method == 'POST':
        nombre = (request.form.get('nombre') or '').strip()
        apellidos = (request.form.get('apellidos') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        telefono = (request.form.get('telefono') or '').strip()
        licencia = (request.form.get('licencia') or '').strip()
        password = request.form.get('password') or ''
        password2 = request.form.get('password2') or ''

        if not all([nombre, apellidos, email, password]):
            flash('Nombre, apellidos, correo y contraseña son obligatorios.', 'error')
            return render_template('registro.html'), 400
        if password != password2:
            flash('Las contraseñas no coinciden.', 'error')
            return render_template('registro.html'), 400

        try:
            if db.session.query(Usuario).filter_by(email=email).first():
                flash('Ya existe una cuenta con ese correo. Inicia sesión.', 'error')
                return redirect(url_for('login'))

            db.session.add(Usuario(
                nombre=nombre, apellidos=apellidos, email=email,
                telefono=telefono or None, licencia=licencia or None,
                password_hash=generate_password_hash(password),
                rol='cliente', es_activo=True))
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash('No se pudo crear la cuenta. Verifica que la base de datos esté activa.', 'error')
            return render_template('registro.html'), 500

        session['nombre'] = f'{nombre} {apellidos}'.strip()
        session['email'] = email
        session['rol'] = 'cliente'
        flash('Cuenta creada. ¡Bienvenido a AutoNova!', 'ok')
        return redirect(_destino_post_login())
    return render_template('registro.html')


@app.route('/logout')
def logout():
    """Cierra la sesión y elimina los datos temporales de checkout."""
    session.pop('nombre', None)
    session.pop('email', None)
    session.pop('rol', None)
    session.pop('reserva', None)
    session.pop('reserva_pendiente', None)
    flash('Has cerrado sesión.', 'info')
    return redirect(url_for('inicio'))


def admin_required(view):
    # Decorador de autorización: solo permite continuar a cuentas admin.
    """Decorador: exige sesión iniciada con rol admin para el panel."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get('email'):
            flash('Inicia sesión con tu cuenta de administrador para entrar al panel.', 'info')
            return redirect(url_for('login'))
        if session.get('rol') != 'admin':
            flash('Acceso restringido: sección solo para administradores.', 'error')
            return redirect(url_for('inicio'))
        return view(*args, **kwargs)
    return wrapped


# -------------------------- Panel administrativo --------------------------
@app.route('/admin')
@admin_required
def admin():
    """Panel de administración: conteos reales de usuarios, vehículos y ESP32."""
    stats = _get_admin_stats()
    try:
        sucursales = db.session.query(Sucursal).order_by(Sucursal.nombre).all()
    except Exception:
        sucursales = []
    return render_template('admin.html', sucursales=sucursales, **stats)


def _get_admin_stats():
    # Las métricas se calculan con consultas ORM y se entregan al dashboard.
    """Recopila KPIs y listados para el dashboard desde la base de datos."""
    try:
        total_usuarios = db.session.query(func.count(Usuario.id_usuario)).scalar() or 0
        total_vehiculos = db.session.query(func.count(Vehiculo.id)).scalar() or 0
        kpi_alquilados = (db.session.query(func.count(Vehiculo.id))
                          .filter(Vehiculo.estado == 'alquilado').scalar() or 0)
        kpi_disponibles = (db.session.query(func.count(Vehiculo.id))
                           .filter(Vehiculo.estado == 'disponible').scalar() or 0)
        kpi_reservadas = (db.session.query(func.count(Vehiculo.id))
                          .filter(Vehiculo.estado == 'reservada').scalar() or 0)

        rows = (db.session.query(ModuloESP32.estado, func.count(ModuloESP32.id))
                .group_by(ModuloESP32.estado).all())
        by_estado = dict(rows)
        conectados = by_estado.get('conectado', 0)
        esperando = by_estado.get('esperando', 0)
        apagados = sum(v for k, v in by_estado.items() if k in ('apagado', 'offline'))

        flota = db.session.query(Vehiculo).order_by(Vehiculo.marca, Vehiculo.modelo).all()
        modulos = db.session.query(ModuloESP32).order_by(ModuloESP32.id).all()
    except Exception:
        (total_usuarios, total_vehiculos, kpi_alquilados, kpi_disponibles,
         kpi_reservadas, conectados, esperando, apagados) = (0, 0, 0, 0, 0, 0, 0, 0)
        flota, modulos = [], []

    # Preparar listado de módulos para el panel (con heartbeat en ms)
    lista_modulos = []
    for m in (modulos if modulos else SAMPLE_MODULOS):
        # Soporta objetos ORM y diccionarios (fallback SAMPLE):
        if isinstance(m, dict):
            mid = m.get('id'); nombre = m.get('nombre'); codigo = m.get('codigo')
            estado = m.get('estado'); clase = m.get('clase', 'warn'); hb = None
        else:
            mid = m.id; nombre = m.nombre; codigo = m.codigo
            estado = m.estado; hb = getattr(m, 'ultimo_heartbeat', None)
            clase = m.clase_estado if hasattr(m, 'clase_estado') else 'warn'
        lista_modulos.append({
            'id': mid,
            'nombre': nombre,
            'codigo': codigo,
            'estado': estado,
            'clase': clase,
            'live_since': int(hb.timestamp() * 1000) if hb else None,
        })

    return {
        'total_usuarios': total_usuarios,
        'total_vehiculos': total_vehiculos,
        'kpi_alquilados': kpi_alquilados,
        'kpi_disponibles': kpi_disponibles,
        'kpi_reservadas': kpi_reservadas,
        'kpi_esp_conectados': conectados,
        'kpi_esp_esperando': esperando,
        'kpi_esp_apagados': apagados,
        'flota': flota if flota else SAMPLE_VEHICULOS,
        'modulos': lista_modulos,
    }


# ------------------- Panel admin: secciones y acciones -------------------
ESTADOS_VEHICULO = ('disponible', 'reservada', 'alquilado', 'mantenimiento', 'baja')
ESTADOS_RESERVA = ('pendiente', 'confirmada', 'en_uso', 'completada', 'cancelada')
HEARTBEAT_LOCK_SECONDS = 30
ALQUILER_SIMULADO_SECONDS = 120


def _sucursales():
    """Lista de sucursales para formularios (vacía si la BD no responde)."""
    try:
        return db.session.query(Sucursal).order_by(Sucursal.nombre).all()
    except Exception:
        return []


@app.route('/admin/vehiculos')
@admin_required
def admin_vehiculos():
    """Gestión completa de la flota."""
    try:
        flota = (db.session.query(Vehiculo)
                 .order_by(Vehiculo.marca, Vehiculo.modelo).all())
    except Exception:
        flota = []
    return render_template('admin_vehiculos.html',
                           flota=flota, sucursales=_sucursales())


@app.route('/admin/reservas')
@admin_required
def admin_reservas():
    """Listado de reservas con cliente y vehículo."""
    try:
        reservas = (db.session.query(Reserva)
                    .order_by(Reserva.creada_en.desc()).all())
    except Exception:
        reservas = []
    return render_template('admin_reservas.html', reservas=reservas)


@app.route('/admin/clientes')
@admin_required
def admin_clientes():
    """Listado de cuentas registradas."""
    try:
        clientes = (db.session.query(Usuario)
                    .order_by(Usuario.creado_en.desc()).all())
    except Exception:
        clientes = []
    return render_template('admin_clientes.html', clientes=clientes)


COMANDOS_ESP32 = ('ping', 'reiniciar', 'encender', 'apagar', 'abrir_cajuela')


def _reiniciar_semaforo_auto(modulo_id):
    """Deja el semáforo del módulo en AUTOMÁTICO con foco verde.

    Se usa al asignar/desasignar un vehículo para que el foco refleje el
    cálculo real según las reservas y NO quede atascado en un foco manual
    (p. ej. rojo) que el admin haya fijado con anterioridad.
    """
    row = db.session.query(SemaforoFoco).filter_by(modulo_id=modulo_id).first()
    if row is None:
        row = SemaforoFoco(modulo_id=modulo_id,
                           foco_activo='verde', modo='auto')
        db.session.add(row)
    row.modo = 'auto'
    row.foco_activo = 'verde'
    row.segundos_restantes = None
    row.fin = None
    row.actualizado_en = datetime.utcnow()


# ------------------------------- Módulos IoT -------------------------------
@app.route('/admin/esp32')
@admin_required
def admin_esp32():
    """Panel de gestión de los módulos ESP32: registro, edición,
    asignación a vehículos, comandos remotos y telemetría."""
    try:
        modulos = db.session.query(ModuloESP32).order_by(ModuloESP32.id).all()
        vehiculos = (db.session.query(Vehiculo)
                     .order_by(Vehiculo.marca, Vehiculo.modelo).all())
        telemetrias = (db.session.query(TelemetriaESP32, ModuloESP32)
                       .join(ModuloESP32,
                             TelemetriaESP32.modulo_id == ModuloESP32.id)
                       .order_by(TelemetriaESP32.leido_en.desc())
                       .limit(20).all())
        comandos = (db.session.query(ComandoESP32, ModuloESP32)
                    .join(ModuloESP32,
                          ComandoESP32.modulo_id == ModuloESP32.id)
                    .order_by(ComandoESP32.creado_en.desc())
                    .limit(15).all())
    except Exception:
        modulos, vehiculos, telemetrias, comandos = [], [], [], []

    lista = []
    for m in (modulos or SAMPLE_MODULOS):
        if isinstance(m, dict):                       # fallback sin BD
            lista.append({'id': m.get('id'), 'nombre': m.get('nombre'),
                          'codigo': m.get('codigo'), 'estado': m.get('estado'),
                          'clase': m.get('clase', 'warn'), 'vehiculo': None,
                          'vehiculo_id': None, 'ip': None, 'firmware': None,
                          'endpoint': None, 'hb_ms': None,
                          'hb_txt': 'Sin señal'})
            continue
        hb_ms = (int(m.ultimo_heartbeat.timestamp() * 1000)
                 if m.ultimo_heartbeat else None)
        try:
            sem = _estado_semaforo(m)
        except Exception:
            sem = None
        lista.append({
            'id': m.id, 'nombre': m.nombre, 'codigo': m.codigo,
            'estado': m.estado, 'clase': m.clase_estado,
            'vehiculo': m.vehiculo, 'vehiculo_id': m.vehiculo_id,
            'ip': m.ip_local, 'firmware': m.firmware,
            'endpoint': m.endpoint_api,
            'semaforo': sem,
            'hb_ms': hb_ms,
            'hb_txt': (m.ultimo_heartbeat.strftime('%d/%m/%Y %H:%M')
                       if m.ultimo_heartbeat else 'Sin señal'),
        })

    kpi_total = len(lista)
    kpi_conectados = sum(1 for m in lista if m['estado'] == 'conectado')
    kpi_esperando = sum(1 for m in lista if m['estado'] == 'esperando')
    kpi_apagados = sum(1 for m in lista if m['estado'] in ('apagado', 'offline'))

    return render_template('admin_esp32.html', modulos=lista,
                           vehiculos=vehiculos, telemetrias=telemetrias,
                           comandos=comandos, comandos_validos=COMANDOS_ESP32,
                           kpi_total=kpi_total,
                           kpi_conectados=kpi_conectados,
                           kpi_esperando=kpi_esperando,
                           kpi_apagados=kpi_apagados)


@app.route('/admin/esp32/nuevo', methods=['POST'])
@admin_required
def admin_esp32_nuevo():
    """Registra un módulo ESP32 nuevo desde el panel."""
    codigo = (request.form.get('codigo') or '').strip().upper()
    nombre = (request.form.get('nombre') or '').strip()
    destino = request.form.get('destino') or url_for('admin_esp32')

    if not all([codigo, nombre]):
        flash('El código y el nombre del módulo son obligatorios.', 'error')
        return redirect(destino)

    try:
        vehiculo_id = (int(request.form['vehiculo_id'])
                       if request.form.get('vehiculo_id') else None)
    except ValueError:
        vehiculo_id = None

    try:
        if (vehiculo_id and db.session.query(ModuloESP32)
                .filter_by(vehiculo_id=vehiculo_id).first()):
            flash('Ese vehículo ya tiene un módulo asignado.', 'error')
            return redirect(destino)
        m = ModuloESP32(
            codigo=codigo, nombre=nombre, vehiculo_id=vehiculo_id,
            estado='esperando',
            firmware=(request.form.get('firmware') or '').strip() or '1.0.0',
            endpoint_api=(request.form.get('endpoint_api') or '').strip()
                         or 'http://192.168.1.105:5000/api')
        db.session.add(m)
        db.session.flush()   # obtiene m.id sin cerrar la transacción
        db.session.add(SemaforoFoco(modulo_id=m.id,
                                    foco_activo='verde', modo='auto'))
        db.session.commit()
        flash(f'Módulo {codigo} registrado. Configura el Arduino con ese ID '
              f'({m.id}) para que envíe sus heartbeats.', 'ok')
    except Exception:
        db.session.rollback()
        flash('No se pudo registrar el módulo: revisa que el código no '
              'exista ya y que la base de datos esté activa.', 'error')
    return redirect(destino)


@app.route('/admin/esp32/<int:mid>/editar', methods=['POST'])
@admin_required
def admin_esp32_editar(mid):
    """Edita los datos de un módulo (nombre, código, vehículo, firmware)."""
    destino = request.form.get('destino') or url_for('admin_esp32')
    try:
        m = db.session.get(ModuloESP32, mid)
        if m is None:
            flash('Módulo no encontrado.', 'error')
            return redirect(destino)

        codigo = (request.form.get('codigo') or '').strip().upper()
        nombre = (request.form.get('nombre') or '').strip()
        if not all([codigo, nombre]):
            flash('El código y el nombre del módulo son obligatorios.', 'error')
            return redirect(destino)

        try:
            vehiculo_id = (int(request.form['vehiculo_id'])
                           if request.form.get('vehiculo_id') else None)
        except ValueError:
            vehiculo_id = None

        if (vehiculo_id and vehiculo_id != m.vehiculo_id
                and db.session.query(ModuloESP32)
                .filter(ModuloESP32.vehiculo_id == vehiculo_id,
                        ModuloESP32.id != mid).first()):
            flash('Ese vehículo ya tiene otro módulo asignado.', 'error')
            return redirect(destino)

        m.codigo = codigo
        m.nombre = nombre
        if m.vehiculo_id != vehiculo_id:
            m.vehiculo_id = vehiculo_id
            _reiniciar_semaforo_auto(m.id)   # evita quedar en foco manual
        m.firmware = ((request.form.get('firmware') or '').strip()
                      or m.firmware)
        m.endpoint_api = ((request.form.get('endpoint_api') or '').strip()
                          or m.endpoint_api)
        db.session.commit()
        flash(f'Módulo {codigo} actualizado.', 'ok')
    except Exception:
        db.session.rollback()
        flash('No se pudo actualizar el módulo.', 'error')
    return redirect(destino)


@app.route('/admin/esp32/<int:mid>/asignar', methods=['POST'])
@admin_required
def admin_esp32_asignar(mid):
    """Asigna (o desasigna) un vehículo al módulo ESP32.

    - `vehiculo_id` vacío  -> desasigna el vehículo actual.
    - Valida que el vehículo no pertenezca a otro módulo (relación 1:1).
    - Al cambiar la asignación el semáforo vuelve a AUTOMÁTICO/verde
      para que refleje el estado real (libre/reserva/alquiler/vencido)
      del vehículo según sus reservas.
    """
    destino = request.form.get('destino') or url_for('admin_esp32')
    try:
        m = db.session.get(ModuloESP32, mid)
        if m is None:
            flash('Módulo no encontrado.', 'error')
            return redirect(destino)

        vehiculo_id = None
        if request.form.get('vehiculo_id'):
            try:
                vehiculo_id = int(request.form['vehiculo_id'])
            except ValueError:
                flash('Vehículo no válido.', 'error')
                return redirect(destino)

        # Relación 1:1 — el vehículo ya no puede estar en otro módulo
        if (vehiculo_id and vehiculo_id != m.vehiculo_id
                and db.session.query(ModuloESP32)
                .filter(ModuloESP32.vehiculo_id == vehiculo_id,
                        ModuloESP32.id != mid).first()):
            flash('Ese vehículo ya tiene otro módulo asignado.', 'error')
            return redirect(destino)

        # Verificar que el vehículo exista
        if vehiculo_id is not None:
            v = db.session.get(Vehiculo, vehiculo_id)
            if v is None:
                flash('Vehículo no encontrado.', 'error')
                return redirect(destino)

        m.vehiculo_id = vehiculo_id
        _reiniciar_semaforo_auto(m.id)   # siempre a automático al asignar
        db.session.commit()

        if vehiculo_id:
            flash(f'{m.codigo} → {v.marca} {v.modelo} ({v.placa}). '
                  f'Semáforo en automático.', 'ok')
        else:
            flash(f'{m.codigo} sin vehículo asignado. Semáforo en automático.',
                  'ok')
    except Exception:
        db.session.rollback()
        flash('No se pudo actualizar el vehículo del módulo.', 'error')
    return redirect(destino)


@app.route('/admin/esp32/<int:mid>/estado', methods=['POST'])
@admin_required
def admin_esp32_estado(mid):
    """Cambia manualmente el estado de un módulo (esperando/conectado/apagado)."""
    nuevo = request.form.get('estado') or ''
    destino = request.form.get('destino') or url_for('admin_esp32')
    if nuevo not in ('esperando', 'conectado', 'apagado'):
        flash('Estado no válido para un módulo ESP32.', 'error')
        return redirect(destino)
    try:
        m = db.session.get(ModuloESP32, mid)
        if m is None:
            flash('Módulo no encontrado.', 'error')
        else:
            m.estado = nuevo
            db.session.commit()
            flash(f'{m.nombre} ahora está "{nuevo}".', 'ok')
    except Exception:
        db.session.rollback()
        flash('No se pudo actualizar el estado del módulo.', 'error')
    return redirect(destino)


@app.route('/admin/esp32/<int:mid>/semaforo', methods=['POST'])
@admin_required
def admin_esp32_semaforo(mid):
    """Cambia el foco del semáforo del módulo desde el panel.

    Escribe en la tabla `semaforo_focos` (fuente de verdad en la base):
      - modo='manual' + foco  -> fija verde/azul/amarillo/rojo. Si es
                                 amarillo, se puede indicar los minutos del
                                 cronómetro (fin = ahora + minutos).
      - modo='auto'           -> vuelve al cálculo automático según las
                                 reservas del vehículo asignado.
    El Arduino (y la página) leen el resultado desde esa tabla.
    """
    destino = request.form.get('destino') or url_for('admin_esp32')
    try:
        m = db.session.get(ModuloESP32, mid)
        if m is None:
            flash('Módulo no encontrado.', 'error')
            return redirect(destino)

        row = (db.session.query(SemaforoFoco)
               .filter_by(modulo_id=mid).first())
        if row is None:
            row = SemaforoFoco(modulo_id=mid, foco_activo='verde', modo='auto')
            db.session.add(row)

        modo = (request.form.get('modo') or '').strip()
        if modo == 'manual':
            foco = (request.form.get('foco') or '').strip()
            if foco not in ('verde', 'azul', 'amarillo', 'rojo'):
                flash('Foco no válido.', 'error')
                return redirect(destino)
            row.modo = 'manual'
            row.foco_activo = foco
            row.segundos_restantes = None
            row.fin = None
            if foco == 'amarillo':
                try:
                    minutos = int(request.form.get('minutos') or 0)
                except ValueError:
                    minutos = 0
                if minutos > 0:
                    # Consistente con la lectura: datetime.now() (hora local),
                    # igual que el cálculo automático de las reservas.
                    row.fin = datetime.now() + timedelta(minutes=minutos)
                    row.segundos_restantes = minutos * 60
            row.actualizado_en = datetime.utcnow()
            db.session.commit()
            flash(f'{m.nombre}: foco {row.foco_activo} fijado (manual).', 'ok')
        else:
            row.modo = 'auto'
            row.foco_activo = 'verde'
            row.segundos_restantes = None
            row.fin = None
            row.actualizado_en = datetime.utcnow()
            db.session.commit()
            flash(f'{m.nombre}: semáforo en automático (según reservas).', 'ok')
    except Exception:
        db.session.rollback()
        flash('No se pudo actualizar el semáforo.', 'error')
    return redirect(destino)


@app.route('/admin/esp32/<int:mid>/eliminar', methods=['POST'])
@admin_required
def admin_esp32_eliminar(mid):
    """Elimina un módulo junto con su telemetría e historial de comandos."""
    destino = request.form.get('destino') or url_for('admin_esp32')
    try:
        m = db.session.get(ModuloESP32, mid)
        if m is None:
            flash('Módulo no encontrado.', 'error')
        else:
            nombre = m.nombre
            db.session.query(SemaforoFoco).filter(
                SemaforoFoco.modulo_id == mid).delete()
            db.session.query(TelemetriaESP32).filter(
                TelemetriaESP32.modulo_id == mid).delete()
            db.session.query(ComandoESP32).filter(
                ComandoESP32.modulo_id == mid).delete()
            db.session.delete(m)
            db.session.commit()
            flash(f'Módulo {nombre} eliminado junto con su telemetría.', 'ok')
    except Exception:
        db.session.rollback()
        flash('No se pudo eliminar el módulo.', 'error')
    return redirect(destino)


@app.route('/admin/esp32/<int:mid>/comando', methods=['POST'])
@admin_required
def admin_esp32_comando(mid):
    """Encola un comando remoto que el Arduino recogerá en su próximo ciclo."""
    comando = request.form.get('comando') or ''
    destino = request.form.get('destino') or url_for('admin_esp32')
    if comando not in COMANDOS_ESP32:
        flash('Comando no válido.', 'error')
        return redirect(destino)
    try:
        m = db.session.get(ModuloESP32, mid)
        if m is None:
            flash('Módulo no encontrado.', 'error')
        else:
            pendientes = (db.session.query(func.count(ComandoESP32.id))
                          .filter(ComandoESP32.modulo_id == mid,
                                  ComandoESP32.estado == 'pendiente')
                          .scalar() or 0)
            if pendientes >= 5:
                flash(f'{m.nombre} ya tiene 5 comandos pendientes. Espera a '
                      'que el Arduino los recoja.', 'error')
            else:
                db.session.add(ComandoESP32(modulo_id=mid, comando=comando))
                db.session.commit()
                flash(f'Comando "{comando}" encolado para {m.nombre}: el '
                      'Arduino lo ejecutará en su próximo ciclo.', 'ok')
    except Exception:
        db.session.rollback()
        flash('No se pudo encolar el comando.', 'error')
    return redirect(destino)


@app.route('/admin/esp32/<int:mid>/telemetria')
@admin_required
def admin_esp32_telemetria(mid):
    """Historial de telemetría y comandos de un módulo concreto."""
    try:
        m = db.session.get(ModuloESP32, mid)
    except Exception:
        m = None
    if m is None:
        flash('Módulo no encontrado o base de datos inactiva.', 'error')
        return redirect(url_for('admin_esp32'))

    try:
        lecturas = (db.session.query(TelemetriaESP32)
                    .filter(TelemetriaESP32.modulo_id == mid)
                    .order_by(TelemetriaESP32.leido_en.desc())
                    .limit(100).all())
        comandos = (db.session.query(ComandoESP32)
                    .filter(ComandoESP32.modulo_id == mid)
                    .order_by(ComandoESP32.creado_en.desc())
                    .limit(30).all())
        total_lecturas = (db.session.query(func.count(TelemetriaESP32.id))
                          .filter(TelemetriaESP32.modulo_id == mid)
                          .scalar() or 0)
    except Exception:
        lecturas, comandos, total_lecturas = [], [], 0

    return render_template('admin_esp32_detalle.html', m=m, lecturas=lecturas,
                           comandos=comandos, total_lecturas=total_lecturas,
                           comandos_validos=COMANDOS_ESP32)


@app.route('/admin/reportes')
@admin_required
def admin_reportes():
    """Reportes básicos: ingresos, estados y ranking de la flota."""
    datos = {'ingresos': 0.0, 'total_reservas': 0, 'activas': 0,
             'tarifa_promedio': 0.0, 'por_estado': [], 'por_categoria': [],
             'top_flota': [], 'transacciones': []}
    try:
        ingresos = (db.session.query(func.coalesce(func.sum(Reserva.total), 0))
                    .filter(Reserva.estado != 'cancelada').scalar()) or 0
        total_reservas = (db.session.query(func.count(Reserva.id)).scalar()) or 0
        activas = (db.session.query(func.count(Reserva.id))
                   .filter(Reserva.estado.in_(['pendiente', 'confirmada', 'en_uso']))
                   .scalar()) or 0
        tarifa_promedio = (db.session.query(
            func.coalesce(func.avg(Vehiculo.tarifa_dia), 0)).scalar()) or 0
        por_estado = (db.session.query(Reserva.estado, func.count(Reserva.id))
                      .group_by(Reserva.estado).all())
        por_categoria = (db.session.query(Vehiculo.categoria, func.count(Vehiculo.id))
                         .group_by(Vehiculo.categoria).all())
        top_flota = (db.session.query(Vehiculo)
                     .order_by(Vehiculo.veces_alquilado.desc()).limit(5).all())
        # Transacciones recientes (Reservas + Ventas) — bloque POLIMÓRFICO:
        # `resumen()` se invoca igual sobre objetos de distinta clase y cada
        # una aporta su propia implementación (Reserva/Venta → Transaccion).
        recientes = (db.session.query(Reserva)
                     .order_by(Reserva.creada_en.desc()).limit(5).all())
        ventas = (db.session.query(Venta)
                  .order_by(Venta.fecha_en.desc()).limit(5).all())
        transacciones = sorted(recientes + ventas,
                               key=lambda t: (getattr(t, 'fecha_en', None)
                                              or getattr(t, 'creada_en', None)
                                              or datetime.min),
                               reverse=True)[:8]
        datos.update({
            'ingresos': float(ingresos),
            'total_reservas': total_reservas,
            'activas': activas,
            'tarifa_promedio': round(float(tarifa_promedio), 2),
            'por_estado': por_estado,
            'por_categoria': por_categoria,
            'top_flota': top_flota,
            'transacciones': resumir_transacciones(transacciones),
        })
    except Exception:
        pass
    return render_template('admin_reportes.html', **datos)


@app.route('/admin/vehiculos/nuevo', methods=['POST'])
@admin_required
def admin_vehiculo_nuevo():
    """Da de alta un vehículo nuevo desde el panel."""
    marca = (request.form.get('marca') or '').strip()
    modelo = (request.form.get('modelo') or '').strip()
    placa = (request.form.get('placa') or '').strip().upper()
    tarifa = request.form.get('tarifa_dia') or ''
    destino = request.form.get('destino') or url_for('admin_vehiculos')

    if not all([marca, modelo, placa, tarifa]):
        flash('Marca, modelo, placa y tarifa son obligatorios.', 'error')
        return redirect(destino)

    try:
        v = Vehiculo(
            marca=marca, modelo=modelo, placa=placa,
            categoria=request.form.get('categoria') or 'sedan',
            anio=int(request.form['anio']) if request.form.get('anio') else None,
            motor=(request.form.get('motor') or '').strip() or None,
            transmision=request.form.get('transmision') or 'automatica',
            combustible=(request.form.get('combustible') or 'Gasolina').strip(),
            kilometraje=int(request.form.get('kilometraje') or 0),
            tarifa_dia=float(tarifa),
            precio_venta=(float(request.form['precio_venta'])
                          if request.form.get('precio_venta') else None),
            descripcion=(request.form.get('descripcion') or '').strip() or None,
            imagen_url=(request.form.get('imagen_url') or '').strip() or None,
            estado=request.form.get('estado') or 'disponible',
            sucursal_id=(int(request.form['sucursal_id'])
                         if request.form.get('sucursal_id') else None),
        )
        db.session.add(v)
        db.session.commit()
        flash(f'Vehículo {marca} {modelo} agregado a la flota.', 'ok')
    except ValueError:
        db.session.rollback()
        flash('Año, tarifa, precio o kilometraje inválidos.', 'error')
    except Exception:
        db.session.rollback()
        flash('No se pudo guardar: revisa que la placa no exista ya.', 'error')
    return redirect(destino)


@app.route('/admin/vehiculos/<int:vid>/estado', methods=['POST'])
@admin_required
def admin_vehiculo_estado(vid):
    """Cambia el estado de un vehículo (baja, reactivar, mantenimiento…)."""
    nuevo = request.form.get('estado') or ''
    destino = request.form.get('destino') or url_for('admin_vehiculos')
    if nuevo not in ESTADOS_VEHICULO:
        flash('Estado no válido.', 'error')
        return redirect(destino)
    try:
        v = db.session.get(Vehiculo, vid)
        if v is None:
            flash('Vehículo no encontrado.', 'error')
        else:
            v.estado = nuevo
            db.session.commit()
            flash(f'{v.marca} {v.modelo} ahora está "{nuevo}".', 'ok')
    except Exception:
        db.session.rollback()
        flash('No se pudo actualizar el estado.', 'error')
    return redirect(destino)


@app.route('/admin/vehiculos/<int:vid>/eliminar', methods=['POST'])
@admin_required
def admin_vehiculo_eliminar(vid):
    """Elimina definitivamente un vehículo de la flota."""
    destino = request.form.get('destino') or url_for('admin_vehiculos')
    try:
        v = db.session.get(Vehiculo, vid)
        if v is None:
            flash('Vehículo no encontrado.', 'error')
        else:
            nombre = f'{v.marca} {v.modelo}'
            db.session.delete(v)
            db.session.commit()
            flash(f'{nombre} eliminado de la flota.', 'ok')
    except Exception:
        db.session.rollback()
        flash('No se pudo eliminar: tiene reservas o módulos asociados. '
              'Usa "Baja" en su lugar.', 'error')
    return redirect(destino)


@app.route('/admin/reservas/<int:rid>/estado', methods=['POST'])
@admin_required
def admin_reserva_estado(rid):
    """Actualiza el estado de una reserva y sincroniza el vehículo."""
    nuevo = request.form.get('estado') or ''
    if nuevo not in ESTADOS_RESERVA:
        flash('Estado no válido.', 'error')
        return redirect(url_for('admin_reservas'))
    try:
        r = db.session.get(Reserva, rid)
        if r is None:
            flash('Reserva no encontrada.', 'error')
        else:
            if nuevo == 'en_uso' and r.estado != 'en_uso':
                otra = (db.session.query(Reserva)
                        .filter(Reserva.id != r.id,
                                Reserva.estado == 'en_uso').first())
                if otra is not None and not otra.ha_vencido(ALQUILER_SIMULADO_SECONDS):
                    flash(f'Ya existe un alquiler activo ({otra.codigo_corto()}).', 'error')
                    return redirect(url_for('admin_reservas'))
                if otra is not None:
                    otra.estado = 'completada'
                    if otra.vehiculo:
                        otra.vehiculo.liberar()
                r.iniciar()
            r.estado = nuevo
            v = r.vehiculo
            if v is not None:
                if nuevo in ('confirmada', 'en_uso'):
                    v.iniciar_alquiler()
                elif nuevo in ('cancelada', 'completada'):
                    v.liberar()
                elif nuevo == 'pendiente':
                    v.marcar_reservado()
            db.session.commit()
            flash(f'Reserva #{r.id} actualizada a "{nuevo}".', 'ok')
    except Exception:
        db.session.rollback()
        flash('No se pudo actualizar la reserva.', 'error')
    return redirect(url_for('admin_reservas'))


@app.route('/admin/clientes/<int:uid>/toggle', methods=['POST'])
@admin_required
def admin_cliente_toggle(uid):
    """Activa / desactiva la cuenta de un cliente."""
    try:
        u = db.session.get(Usuario, uid)
        if u is None:
            flash('Cuenta no encontrada.', 'error')
        elif u.rol == 'admin':
            flash('No puedes desactivar una cuenta admin.', 'error')
        else:
            u.es_activo = not u.es_activo
            db.session.commit()
            flash(f'Cuenta de {u.nombre} '
                  f'{"activada" if u.es_activo else "desactivada"}.', 'ok')
    except Exception:
        db.session.rollback()
        flash('No se pudo actualizar la cuenta.', 'error')
    return redirect(url_for('admin_clientes'))


@app.route('/admin/usuarios/nuevo', methods=['POST'])
@admin_required
def admin_usuario_nuevo():
    """Crea una cuenta nueva (cliente/staff/admin) desde el panel."""
    nombre = (request.form.get('nombre') or '').strip()
    apellidos = (request.form.get('apellidos') or '').strip()
    email = (request.form.get('email') or '').strip().lower()
    telefono = (request.form.get('telefono') or '').strip()
    licencia = (request.form.get('licencia') or '').strip()
    password = request.form.get('password') or ''
    rol = request.form.get('rol') or 'cliente'
    destino = request.form.get('destino') or url_for('admin_clientes')

    if rol not in ('cliente', 'staff', 'admin'):
        rol = 'cliente'
    if not all([nombre, email, password]):
        flash('Nombre, correo y contraseña son obligatorios.', 'error')
        return redirect(destino)
    if len(password) < 6:
        flash('La contraseña debe tener al menos 6 caracteres.', 'error')
        return redirect(destino)

    try:
        if db.session.query(Usuario).filter_by(email=email).first():
            flash('Ya existe una cuenta con ese correo.', 'error')
            return redirect(destino)

        db.session.add(Usuario(
            nombre=nombre, apellidos=apellidos or None, email=email,
            telefono=telefono or None, licencia=licencia or None,
            password_hash=generate_password_hash(password),
            rol=rol, es_activo=True))
        db.session.commit()
        flash(f'Cuenta creada: {email} (rol {rol}).', 'ok')
    except Exception:
        db.session.rollback()
        flash('No se pudo crear la cuenta. Verifica que la base de datos esté activa.',
              'error')
    return redirect(destino)


@app.route('/admin/usuarios/<int:uid>/eliminar', methods=['POST'])
@admin_required
def admin_usuario_eliminar(uid):
    """Elimina definitivamente una cuenta de usuario del panel."""
    destino = request.form.get('destino') or url_for('admin_clientes')
    try:
        u = db.session.get(Usuario, uid)
        if u is None:
            flash('Cuenta no encontrada.', 'error')
        elif u.rol == 'admin':
            flash('No puedes eliminar una cuenta admin.', 'error')
        elif (u.email or '').lower() == (session.get('email') or '').lower():
            flash('No puedes eliminar la cuenta con la que iniciaste sesión.', 'error')
        else:
            tiene_reservas = (db.session.query(func.count(Reserva.id))
                              .filter(Reserva.usuario_id == uid).scalar() or 0)
            tiene_ventas = (db.session.query(func.count(Venta.id))
                            .filter(Venta.usuario_id == uid).scalar() or 0)
            tiene_modulos = (db.session.query(func.count(ModuloESP32.id))
                             .filter(ModuloESP32.usuario_id == uid).scalar() or 0)
            if tiene_reservas or tiene_ventas or tiene_modulos:
                flash('No se puede eliminar: la cuenta tiene reservas, ventas o '
                      'módulos asociados. Usa "Desactivar" en su lugar.', 'error')
            else:
                nombre = f'{u.nombre} {u.apellidos or ""}'.strip()
                email = u.email
                db.session.delete(u)
                db.session.commit()
                flash(f'Cuenta de {nombre} ({email}) eliminada.', 'ok')
    except Exception:
        db.session.rollback()
        flash('No se pudo eliminar la cuenta.', 'error')
    return redirect(destino)


# ------------------------- API en tiempo real (ESP32) -------------------------
def _buscar_modulo_por_ref(modulo_ref):
    """Localiza un módulo por id numérico o por código (ESP32-AUTONOVA-001).

    El código es estable aunque se eliminen/creen módulos, por lo que es
    el identificador recomendado en el firmware del Arduino.
    """
    ref = (modulo_ref or '').strip()
    if ref.isdigit():
        return db.session.get(ModuloESP32, int(ref))
    return db.session.query(ModuloESP32).filter(
        ModuloESP32.codigo == ref.upper()).first()


def _estado_semaforo(modulo):
    """Semáforo físico que debe mostrar el módulo ESP32.

    La fuente de verdad es la tabla `semaforo_focos` (leída por la página
    y por el Arduino a través de la API, nunca calculada "al vuelo" por el
    firmware):

      - modo 'manual' -> devuelve el foco que fijó el admin desde el panel
                         (verde/azul/amarillo/rojo + cronómetro si amarillo).
      - modo 'auto'   -> calcula según las reservas del vehículo asignado y
                         guarda el resultado en la tabla para que la página
                         siempre lea el estado desde la base:

      verde    -> sin reserva activa (o módulo sin vehículo asignado)
      azul     -> reserva por confirmar (pendiente) o confirmada sin iniciar
      amarillo -> alquiler EN CURSO: luces amarillas + cronómetro con los
                  segundos_restantes antes de que venza el alquiler
      rojo     -> el tiempo de alquiler YA TERMINÓ; el módulo mantiene el foco
                  rojo encendido hasta que el admin cambie el estado de la
                  reserva en /admin/reservas (completada/cancelada/…)
    """
    base = {'luz': 'verde', 'tipo': 'libre', 'reserva_id': None,
            'reserva_estado': None, 'segundos_restantes': None,
            'fin': None, 'detalle': 'Sin reservas activas'}

    # --- Fila de la tabla semaforo_focos (fuente de verdad en BD) ---
    try:
        row = db.session.query(SemaforoFoco).filter_by(
            modulo_id=modulo.id).first()
        if row is None:
            row = SemaforoFoco(modulo_id=modulo.id, foco_activo='verde',
                               modo='auto')
            db.session.add(row)
            db.session.commit()
    except Exception:
        row = None

    # Un alquiler iniciado tiene prioridad sobre el modo manual: el temporizador
    # debe seguir visible aunque el foco manual anterior haya quedado guardado.
    reserva_en_uso = None
    try:
        vehiculo_modulo = modulo.vehiculo
        if vehiculo_modulo is not None:
            reserva_en_uso = (db.session.query(Reserva)
                              .filter(Reserva.vehiculo_id == vehiculo_modulo.id,
                                      Reserva.estado == 'en_uso')
                              .order_by(Reserva.inicio_alquiler.desc()).first())
    except Exception:
        reserva_en_uso = None

    # Modo MANUAL: el admin fijó el foco desde el panel
    if row is not None and row.modo == 'manual' and reserva_en_uso is None:
        base['luz'] = row.foco_activo
        base['tipo'] = 'manual'
        base['reserva_id'] = None
        base['reserva_estado'] = None
        base['segundos_restantes'] = None
        base['fin'] = None
        if row.foco_activo == 'amarillo' and row.fin:
            restante = int((row.fin - datetime.now()).total_seconds())
            base['segundos_restantes'] = max(restante, 0)
            base['fin'] = row.fin.isoformat()
            base['detalle'] = 'Foco amarillo (manual)'
        else:
            base['detalle'] = f'Foco {row.foco_activo} (manual)'
        return base

    # Modo AUTO: se calcula según las reservas del vehículo asignado
    try:
        vehiculo = modulo.vehiculo
    except Exception:
        vehiculo = None
    if vehiculo is None:
        base['detalle'] = 'Módulo sin vehículo asignado'
        return base

    try:
        activas = (db.session.query(Reserva)
                   .filter(Reserva.vehiculo_id == vehiculo.id,
                           Reserva.estado.in_(['pendiente', 'confirmada',
                                               'en_uso']),
                           or_(Reserva.tipo.is_(None), Reserva.tipo != 'venta'))
                   .order_by(Reserva.creada_en.desc()).all())
        # Prioridad: alquiler en curso > pendiente > confirmada
        activas.sort(key=lambda rr: (0 if rr.estado == 'en_uso'
                                     else (1 if rr.estado == 'pendiente'
                                           else 2)))
    except Exception:
        activas = []

    if not activas:
        return base

    r = activas[0]
    base['reserva_id'] = r.id
    base['reserva_estado'] = r.estado

    if r.estado == 'en_uso':
        if r.inicio_alquiler:
            fin = r.inicio_alquiler + timedelta(seconds=ALQUILER_SIMULADO_SECONDS)
            restante = r.segundos_restantes(ALQUILER_SIMULADO_SECONDS)
            base['fin'] = fin.isoformat()
            base['segundos_restantes'] = max(restante, 0)
            if restante > 0:
                base['luz'] = 'amarillo'
                base['tipo'] = 'en_uso'
                base['detalle'] = f'AN-{r.id:04d} en curso'
            else:
                base['luz'] = 'rojo'
                base['tipo'] = 'vencido'
                base['detalle'] = f'AN-{r.id:04d} vencida'
                r.estado = 'completada'
                if vehiculo:
                    vehiculo.liberar()
                if row is not None:
                    row.foco_activo = 'verde'
                    row.modo = 'auto'
                db.session.commit()
                # La primera respuesta posterior al vencimiento debe ser roja
                # para que el ESP32 pueda activar LED y buzzer. La siguiente
                # consulta ya encontrara la reserva completada y devolvera verde.
        else:
            base['luz'] = 'amarillo'
            base['tipo'] = 'en_uso'
            base['detalle'] = f'AN-{r.id:04d} en curso'
    elif r.estado in ('pendiente', 'confirmada'):
        base['luz'] = 'azul'
        base['tipo'] = 'reserva'
        base['detalle'] = (f'AN-{r.id:04d} por confirmar'
                           if r.estado == 'pendiente'
                           else f'AN-{r.id:04d} confirmada')

    # Guardar el resultado en la tabla para que la página lo lea desde la BD
    if row is not None:
        try:
            row.foco_activo = base['luz']
            row.segundos_restantes = base.get('segundos_restantes')
            row.fin = (datetime.fromisoformat(base['fin'])
                       if base.get('fin') else None)
            row.actualizado_en = datetime.utcnow()
            db.session.commit()
        except Exception:
            db.session.rollback()
    return base


# ------------------------------- API ESP32 ---------------------------------
# Estas rutas traducen JSON del hardware a objetos ORM y respuestas JSON.
@app.route('/api/esp', methods=['GET'])
def api_esp_list():
    """Devuelve el estado actual de todos los módulos ESP32 (para polling)."""
    datos = {}
    try:
        modulos = db.session.query(ModuloESP32).order_by(ModuloESP32.id).all()
        for m in modulos:
            datos[m.codigo] = {
                'id': m.id,
                'nombre': m.nombre,
                'estado': m.estado,
                'ultimo_heartbeat': m.ultimo_heartbeat.isoformat() if m.ultimo_heartbeat else None,
                'ip': m.ip_local,
                'firmware': m.firmware,
                'semaforo': _estado_semaforo(m),
            }
    except Exception as exc:
        return jsonify({'error': str(exc)}), 503
    return jsonify(datos)


@app.route('/api/esp/<int:modulo_id>/status', methods=['GET'])
def api_esp_status(modulo_id):
    """Estado individual de un módulo."""
    try:
        m = db.session.get(ModuloESP32, modulo_id)
        if not m:
            return jsonify({'error': 'Módulo no encontrado'}), 404
        return jsonify({
            'id': m.id,
            'codigo': m.codigo,
            'nombre': m.nombre,
            'estado': m.estado,
            'ultimo_heartbeat': m.ultimo_heartbeat.isoformat() if m.ultimo_heartbeat else None,
            'ip': m.ip_local,
            'firmware': m.firmware,
        })
    except Exception as exc:
        return jsonify({'error': str(exc)}), 503


def _bloqueo_modulo_actual(modulo):
    """Devuelve el módulo que mantiene el único canal ESP32 activo."""
    ahora = datetime.utcnow()
    conectados = (db.session.query(ModuloESP32)
                  .filter(ModuloESP32.id != modulo.id,
                          ModuloESP32.estado == 'conectado')
                  .all())
    for otro in conectados:
        if not otro.ultimo_heartbeat:
            otro.estado = 'apagado'
            continue
        edad = (ahora - otro.ultimo_heartbeat).total_seconds()
        if edad > HEARTBEAT_LOCK_SECONDS:
            otro.estado = 'apagado'
            continue
        semaforo = _estado_semaforo(otro)
        if semaforo.get('luz') == 'amarillo' and semaforo.get('segundos_restantes', 0) > 0:
            return otro
        otro.estado = 'apagado'
    return None


@app.route('/api/esp/<modulo_ref>/heartbeat', methods=['POST'])
def api_esp_heartbeat(modulo_ref):
    """Actualiza el estado del módulo en tiempo real (lo llaman los ESP32).

    `<modulo_ref>` acepta el id numérico (7) o el código del módulo
    (ESP32-AUTONOVA-001, recomendado: sobrevive a altas/bajas en el panel).

    JSON opcional: {"lat":.., "lng":.., "velocidad":.., "bateria":..,
                    "motor":"on|off", "rssi":..}  → se guarda en telemetria_esp32.
    """
    try:
        m = _buscar_modulo_por_ref(modulo_ref)
        if not m:
            print(f'[ESP32] Heartbeat de "{modulo_ref}" rechazado: módulo no '
                  'existe en la BD. Regístralo en el panel /admin/esp32.')
            return jsonify({'error': 'Módulo no encontrado'}), 404

        payload = request.get_json(silent=True) or {}
        bloqueo = _bloqueo_modulo_actual(m)
        if bloqueo is not None:
            db.session.commit()
            return jsonify({
                'error': 'Ya hay otro módulo conectado con un alquiler activo.',
                'modulo_activo': bloqueo.codigo,
            }), 409

        m.estado = payload.get('estado', 'conectado')
        m.ultimo_heartbeat = datetime.utcnow()
        # IP del módulo: la manda el ESP32 en el JSON o se detecta de la conexión
        m.ip_local = (payload.get('ip') or request.remote_addr
                      or m.ip_local)
        print(f'[ESP32] Heartbeat módulo {m.id} ({m.codigo}) desde '
              f'{m.ip_local} · estado={m.estado}')

        # Guardar lectura de telemetría en tiempo real
        tele = TelemetriaESP32(
            modulo_id=m.id,
            lat=payload.get('lat'),
            lng=payload.get('lng'),
            velocidad=payload.get('velocidad'),
            bateria=payload.get('bateria'),
            motor=payload.get('motor'),
            rssi=payload.get('rssi'),
        )
        db.session.add(tele)
        db.session.commit()
        return jsonify({'ok': True, 'estado': m.estado,
                        'ultimo_heartbeat': m.ultimo_heartbeat.isoformat(),
                        'semaforo': _estado_semaforo(m)})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500


@app.route('/api/esp/<modulo_ref>/estado', methods=['GET'])
def api_esp_estado(modulo_ref):
    """Estado del semáforo que debe mostrar el módulo (luces + cronómetro).

    Lo consulta el firmware cuando el heartbeat no trae el campo `semaforo`
    (o para verificar la asignación manualmente en el navegador):
        GET http://<servidor>:5000/api/esp/<codigo>/estado
    Devuelve: {"luz": "verde|azul|amarillo|rojo", "detalle": "...",
               "reserva_id": ..., "segundos_restantes": ...|null,
               "fin": "...|null"}
    """
    try:
        m = _buscar_modulo_por_ref(modulo_ref)
        if not m:
            return jsonify({'error': 'Módulo no encontrado'}), 404
        return jsonify(_estado_semaforo(m))
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500


@app.route('/api/esp/<modulo_ref>/comando', methods=['GET'])
def api_esp_comando(modulo_ref):
    """El ESP32 consulta este endpoint para obtener su comando pendiente.

    `<modulo_ref>` acepta el id numérico o el código del módulo (recomendado).
    Devuelve el comando más antiguo en estado 'pendiente' y lo marca como
    'entregado'. Sin comandos pendientes responde {"comando": null}.
    """
    try:
        m = _buscar_modulo_por_ref(modulo_ref)
        if not m:
            return jsonify({'error': 'Módulo no encontrado'}), 404
        cmd = (db.session.query(ComandoESP32)
               .filter(ComandoESP32.modulo_id == m.id,
                       ComandoESP32.estado == 'pendiente')
               .order_by(ComandoESP32.creado_en.asc())
               .first())
        if not cmd:
            return jsonify({'comando': None})
        cmd.estado = 'entregado'
        cmd.entregado_en = datetime.utcnow()
        db.session.commit()
        return jsonify({'comando': cmd.comando, 'id': cmd.id,
                        'creado_en': cmd.creado_en.isoformat()
                        if cmd.creado_en else None})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500


if __name__ == '__main__':
    init_database()
    app.run(host='0.0.0.0', port=5000, debug=True)