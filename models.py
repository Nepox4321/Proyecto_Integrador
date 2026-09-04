# -*- coding: utf-8 -*-
"""Modelos ORM (SQLAlchemy) de AutoNova.

ALINEADO con el esquema real de la base `autonova`
(dump MySQL 8.0.46 proporcionado por el usuario):

  modulos_esp32 · pagos · reservas · sucursales ·
  telemetria_esp32 · usuarios · vehiculos · ventas

La instancia `db` se define aquí y se vincula a la app con db.init_app().
"""
from datetime import datetime
from abc import ABCMeta, abstractmethod
from enum import Enum
from typing import Literal, overload

from sqlalchemy import Numeric, SmallInteger, Text
from sqlalchemy.dialects.mysql import INTEGER
from flask_sqlalchemy import SQLAlchemy
from flask_sqlalchemy.model import DefaultMeta

db = SQLAlchemy()


class TipoTransaccion(str, Enum):
    """Tipos de transaccion soportados por el dominio."""
    ALQUILER = 'alquiler'
    VENTA = 'venta'


class EstadoVehiculo(str, Enum):
    """Estados validos de una unidad de la flota."""
    DISPONIBLE = 'disponible'
    RESERVADA = 'reservada'
    ALQUILADO = 'alquilado'
    MANTENIMIENTO = 'mantenimiento'
    BAJA = 'baja'


class ComandoESP32Enum(str, Enum):
    """Comandos que el panel puede enviar a un modulo ESP32."""
    PING = 'ping'
    REINICIAR = 'reiniciar'
    ENCENDER = 'encender'
    APAGAR = 'apagar'
    ABRIR_CAJUELA = 'abrir_cajuela'


class ModoSemaforo(str, Enum):
    """Modo de control del semaforo del vehiculo."""
    AUTO = 'auto'
    MANUAL = 'manual'


class DomainMeta(DefaultMeta, ABCMeta):
    """Combina el mapeo declarativo de SQLAlchemy con ABCMeta."""


class DomainModel(db.Model, metaclass=DomainMeta):
    """Base ORM para jerarquías con contratos abstractos formales."""
    __abstract__ = True


class Usuario(db.Model):
    """Clientes / administradores que usan la plataforma."""
    __tablename__ = 'usuarios'

    id_usuario = db.Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(120), nullable=False)
    apellidos = db.Column(db.String(120))
    email = db.Column(db.String(150), unique=True, nullable=False)
    telefono = db.Column(db.String(20))
    password_hash = db.Column(db.String(255), nullable=False)
    licencia = db.Column(db.String(30))
    rol = db.Column(db.Enum('cliente', 'admin', 'staff'),
                   nullable=False, default='cliente')
    avatar_url = db.Column(db.String(255))
    es_activo = db.Column(db.Boolean, default=True)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    ultimo_acceso = db.Column(db.DateTime)

    def __repr__(self):
        return f'<Usuario {self.email}>'


class Sucursal(db.Model):
    """Puntos físicos de entrega/recepción."""
    __tablename__ = 'sucursales'

    id = db.Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(120), nullable=False)
    ciudad = db.Column(db.String(80), nullable=False)
    direccion = db.Column(db.String(180))
    telefono = db.Column(db.String(20))
    email = db.Column(db.String(150))
    lat = db.Column(Numeric(10, 7))
    lng = db.Column(Numeric(10, 7))

    def __repr__(self):
        return f'<Sucursal {self.nombre}>'


class Vehiculo(db.Model):
    """Unidad de la flota."""
    __tablename__ = 'vehiculos'

    id = db.Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    marca = db.Column(db.String(60), nullable=False)
    modelo = db.Column(db.String(120), nullable=False)
    anio = db.Column(SmallInteger)
    placa = db.Column(db.String(12), unique=True, nullable=False)
    categoria = db.Column(db.Enum('sedan', 'suv', 'deportivo', 'elegante',
                                  'electrico', 'convertible'),
                          nullable=False, default='sedan')
    motor = db.Column(db.String(60))
    transmision = db.Column(db.Enum('manual', 'automatica'), default='automatica')
    combustible = db.Column(db.String(30), default='Gasolina')
    kilometraje = db.Column(db.Integer, default=0)
    tarifa_dia = db.Column(Numeric(10, 2), nullable=False)
    tarifa_mes = db.Column(Numeric(10, 2))
    precio_venta = db.Column(Numeric(12, 2))
    descripcion = db.Column(Text)
    imagen_url = db.Column(db.String(255))
    estado = db.Column(db.Enum('disponible', 'reservada', 'alquilado',
                               'mantenimiento', 'baja'),
                       nullable=False, default='disponible')
    sucursal_id = db.Column(INTEGER(unsigned=True), db.ForeignKey('sucursales.id'))
    disponible_desde = db.Column(db.Date)
    veces_alquilado = db.Column(db.Integer, default=0)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)

    sucursal = db.relationship('Sucursal', backref='vehiculos')

    @property
    def imagen(self):
        return self.imagen_url or 'vehiculo1.jpg'

    @property
    def tarifa(self):
        try:
            return int(self.tarifa_dia)
        except (TypeError, ValueError):
            return 0

    def marcar_reservado(self):
        """Marca la unidad como reservada si todavía está disponible."""
        if self.estado == 'disponible':
            self.estado = 'reservada'

    def iniciar_alquiler(self):
        """Cambia la unidad al estado protegido de alquiler activo."""
        self.estado = 'alquilado'

    def liberar(self):
        """Devuelve la unidad a la flota disponible."""
        self.estado = 'disponible'

    def __repr__(self):
        return f'<Vehiculo {self.marca} {self.modelo}>'
class Transaccion(DomainModel):
    """Clase base ABSTRACTA para las transacciones del negocio (HERENCIA).

    `Reserva` (alquiler) y `Venta` (compra/venta) heredan de aquí las
    claves foráneas hacia `usuarios` y `vehiculos`, y comparten un contrato
    POLIMÓRFICO: cada subclase implementa `tipo_transaccion()`, `importe()`
    y `resumen()`, de modo que el resto del sistema puede tratar cualquier
    transacción de forma uniforme (principio de sustitución de Liskov).

    Al ser abstracta (`__abstract__ = True`) NO crea tabla propia: sus
    columnas se copian a las tablas hijas `reservas` y `ventas`, por lo que
    el esquema físico de la base de datos permanece exactamente igual.
    """
    __abstract__ = True

    id = db.Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    usuario_id = db.Column(INTEGER(unsigned=True), db.ForeignKey('usuarios.id_usuario'),
                           nullable=False)
    vehiculo_id = db.Column(INTEGER(unsigned=True), db.ForeignKey('vehiculos.id'),
                            nullable=False)

    # ---- Contrato polimórfico (cada subclase lo implementa) ----
    @abstractmethod
    def tipo_transaccion(self):
        """Tipo de transacción: 'alquiler' (Reserva) o 'venta' (Venta)."""
        raise NotImplementedError('Las subclases deben indicar su tipo.')

    @abstractmethod
    def importe(self):
        """Importe total de la transacción."""
        raise NotImplementedError('Las subclases deben exponer su importe.')

    def es_alquiler(self):
        """True si la transacción es un alquiler (despacho polimórfico)."""
        return self.tipo_transaccion() == TipoTransaccion.ALQUILER.value

    @abstractmethod
    def resumen(self):
        """Representación común para reportes y confirmaciones."""
        raise NotImplementedError

    @overload
    def codigo_corto(self) -> str:
        ...

    @overload
    def codigo_corto(self, incluir_prefijo: Literal[True]) -> str:
        ...

    @overload
    def codigo_corto(self, incluir_prefijo: Literal[False]) -> str:
        ...

    def codigo_corto(self, incluir_prefijo=True):
        """Devuelve el codigo completo o solo su consecutivo numerico.

        Las sobrecargas documentan las dos formas validas de llamar al metodo;
        la implementacion unica conserva el despacho polimorfico del prefijo.
        """
        consecutivo = f'{self.id:04d}'
        if not incluir_prefijo:
            return consecutivo
        prefijo = 'AN' if self.es_alquiler() else 'VTA'
        return f'{prefijo}-{consecutivo}'


class Reserva(Transaccion):
    """Reservas / alquileres de vehículos (hereda de `Transaccion`)."""
    __tablename__ = 'reservas'

    sucursal_id = db.Column(INTEGER(unsigned=True), db.ForeignKey('sucursales.id'))
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin = db.Column(db.Date, nullable=False)
    tarifa_dia = db.Column(Numeric(10, 2), nullable=False)
    total = db.Column(Numeric(10, 2))
    tipo = db.Column(db.Enum('alquiler', 'venta'), default='alquiler')
    estado = db.Column(db.Enum('pendiente', 'confirmada', 'en_uso',
                               'completada', 'cancelada'),
                       nullable=False, default='pendiente')
    creada_en = db.Column(db.DateTime, default=datetime.utcnow)
    inicio_alquiler = db.Column(db.DateTime)

    vehiculo = db.relationship('Vehiculo', backref='reservas')
    usuario = db.relationship('Usuario', backref='reservas')

    # ---- Implementación polimórfica del contrato de `Transaccion` ----
    def tipo_transaccion(self):
        return 'alquiler'

    def esta_activa(self):
        """Indica si la reserva participa en el ciclo activo de alquiler."""
        return self.estado in ('pendiente', 'confirmada', 'en_uso')

    def iniciar(self):
        """Inicia el alquiler asociado a la reserva."""
        self.estado = 'en_uso'
        self.inicio_alquiler = datetime.utcnow()

    def segundos_restantes(self, duracion=120):
        """Calcula el tiempo simulado restante desde el inicio registrado."""
        if self.estado != 'en_uso' or not self.inicio_alquiler:
            return None
        return max(int(duracion -
                       (datetime.utcnow() - self.inicio_alquiler).total_seconds()), 0)

    def ha_vencido(self, duracion=120):
        """Indica si el alquiler activo ya consumio su tiempo simulado."""
        restante = self.segundos_restantes(duracion)
        return restante is not None and restante <= 0

    def cancelar(self):
        """Cancela la reserva desde un estado todavía activo."""
        if self.estado not in ('pendiente', 'confirmada'):
            raise ValueError('La reserva no puede cancelarse en su estado actual.')
        self.estado = 'cancelada'

    def importe(self):
        return float(self.total or 0)

    def resumen(self):
        """Resumen estandarizado de la transacción para listados/reportes."""
        v = self.vehiculo
        dias = (max((self.fecha_fin - self.fecha_inicio).days, 1)
            if self.fecha_fin and self.fecha_inicio else 0)
        return {
            'codigo': self.codigo_corto(),
            'tipo': self.tipo_transaccion(),
            'usuario': (f'{self.usuario.nombre} {self.usuario.apellidos or ""}'
                        .strip() if self.usuario else '—'),
            'vehiculo': f'{v.marca} {v.modelo}' if v else '—',
            'dias': dias,
            'periodo': (f'{self.fecha_inicio} → {self.fecha_fin}'
                        if self.fecha_inicio and self.fecha_fin else '—'),
            'importe': self.importe(),
            'estado': self.estado,
        }

    def __repr__(self):
        return f'<Reserva {self.id} veh {self.vehiculo_id}>'


class Pago(db.Model):
    """Pagos asociados a una reserva."""
    __tablename__ = 'pagos'

    id = db.Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    reserva_id = db.Column(INTEGER(unsigned=True), db.ForeignKey('reservas.id'),
                           nullable=False)
    monto = db.Column(Numeric(10, 2), nullable=False)
    metodo = db.Column(db.Enum('tarjeta', 'transferencia', 'oxxo', 'efectivo'))
    estado = db.Column(db.Enum('pendiente', 'pagado', 'rechazado',
                               'reembolsado'), default='pendiente')
    referencia = db.Column(db.String(120))
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Pago {self.id} {self.estado}>'


class Venta(Transaccion):
    """Ventas directas de vehículos (hereda de `Transaccion`)."""
    __tablename__ = 'ventas'

    reserva_id = db.Column(INTEGER(unsigned=True), db.ForeignKey('reservas.id'), unique=True)
    precio_final = db.Column(Numeric(12, 2), nullable=False)
    estado = db.Column(db.Enum('cotizada', 'pagada', 'entregada'))
    fecha_en = db.Column(db.DateTime, default=datetime.utcnow)

    vehiculo = db.relationship('Vehiculo', backref='ventas')
    usuario = db.relationship('Usuario', backref='ventas')

    # ---- Implementación polimórfica del contrato de `Transaccion` ----
    def tipo_transaccion(self):
        return 'venta'

    def importe(self):
        return float(self.precio_final or 0)

    def resumen(self):
        """Resumen estandarizado de la transacción para listados/reportes."""
        v = self.vehiculo
        return {
            'codigo': self.codigo_corto(),
            'tipo': self.tipo_transaccion(),
            'usuario': (f'{self.usuario.nombre} {self.usuario.apellidos or ""}'
                        .strip() if self.usuario else '—'),
            'vehiculo': f'{v.marca} {v.modelo}' if v else '—',
            'dias': None,
            'periodo': (f'Vendido el {self.fecha_en}'
                        if self.fecha_en else '—'),
            'importe': self.importe(),
            'estado': self.estado,
        }

    def __repr__(self):
        return f'<Venta {self.id} ${self.precio_final}>'


def resumir_transacciones(transacciones):
    """Aplica el mismo contrato a reservas y ventas sin conocer su clase.

    Cada objeto ejecuta su propia implementación de `resumen()`, demostrando
    polimorfismo por despacho dinámico.
    """
    return [transaccion.resumen() for transaccion in transacciones]


class ModuloESP32(db.Model):
    """Módulos IoT instalados en los vehículos (telemetría en vivo)."""
    __tablename__ = 'modulos_esp32'

    id = db.Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    codigo = db.Column(db.String(60), unique=True, nullable=False)
    nombre = db.Column(db.String(60), nullable=False)
    vehiculo_id = db.Column(INTEGER(unsigned=True), db.ForeignKey('vehiculos.id'), unique=True)
    usuario_id = db.Column(INTEGER(unsigned=True), db.ForeignKey('usuarios.id_usuario'))
    estado = db.Column(db.Enum('esperando', 'conectado', 'apagado'),
                       nullable=False, default='esperando')
    endpoint_api = db.Column(db.String(255),
                             default='http://192.168.1.105:5000/api')
    ultimo_heartbeat = db.Column(db.DateTime)
    ip_local = db.Column(db.String(45))
    firmware = db.Column(db.String(30), default='1.0.0')
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)

    vehiculo = db.relationship('Vehiculo', backref='modulo')

    @property
    def clase_estado(self):
        return {'conectado': 'ok', 'esperando': 'warn',
                'apagado': 'off', 'offline': 'off'}.get(self.estado, 'warn')

    def __repr__(self):
        return f'<ModuloESP32 {self.codigo}>'


class EntidadModuloESP32(DomainModel):
    """Clase base ABSTRACTA para entidades asociadas a un módulo ESP32
    (HERENCIA).

    `TelemetriaESP32`, `ComandoESP32` y `SemaforoFoco` heredan de aquí el
    identificador (INTEGER unsigned) y la clave foránea `modulo_id` que las
    vincula con `modulos_esp32`. Al ser abstracta no crea tabla propia: sus
    columnas se copian a cada tabla hija, por lo que el esquema físico no
    cambia.
    """
    __abstract__ = True

    id = db.Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    modulo_id = db.Column(INTEGER(unsigned=True),
                          db.ForeignKey('modulos_esp32.id'),
                          nullable=False)

    @abstractmethod
    def etiqueta_corta(self):
        """Etiqueta descriptiva de la entidad (despacho polimórfico)."""
        raise NotImplementedError('Cada subclase indica su etiqueta.')


class TelemetriaESP32(EntidadModuloESP32):
    """Lecturas de telemetría enviadas por los módulos ESP32."""
    __tablename__ = 'telemetria_esp32'

    lat = db.Column(Numeric(10, 7))
    lng = db.Column(Numeric(10, 7))
    velocidad = db.Column(SmallInteger)
    bateria = db.Column(db.SmallInteger)   # tinyint en MySQL → SmallInteger en SA
    motor = db.Column(db.Enum('on', 'off'))
    rssi = db.Column(SmallInteger)
    leido_en = db.Column(db.DateTime, default=datetime.utcnow)

    modulo = db.relationship('ModuloESP32', backref='telemetrias')

    def etiqueta_corta(self):
        return f'Telemetría #{self.id}'

    def __repr__(self):
        return f'<TelemetriaESP32 mod {self.modulo_id}>'


class ComandoESP32(EntidadModuloESP32):
    """Comandos encolados desde el panel admin hacia los módulos ESP32.

    El panel encola (estado='pendiente') y el Arduino las recoge con
    GET /api/esp/<id>/comando, que marca la fila como 'entregado'.
    """
    __tablename__ = 'comandos_esp32'

    comando = db.Column(db.Enum('ping', 'reiniciar', 'encender',
                                'apagar', 'abrir_cajuela'),
                        nullable=False)
    estado = db.Column(db.Enum('pendiente', 'entregado'),
                       nullable=False, default='pendiente')
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    entregado_en = db.Column(db.DateTime)

    modulo = db.relationship('ModuloESP32', backref='comandos')

    def etiqueta_corta(self):
        return f'Comando {self.comando}'

    def __repr__(self):
        return f'<ComandoESP32 {self.comando} mod {self.modulo_id}>'


class SemaforoFoco(EntidadModuloESP32):
    """Estado físico de los focos del semáforo del módulo (fuente en BD).

    Permite que el panel admin LEA el foco activo directamente de la base
    (sin depender del Arduino) y lo CAMBIE manualmente desde la página:

      - modo = 'auto'   -> el servidor calcula el foco según las reservas
                           del vehículo asignado (comportamiento anterior).
      - modo = 'manual' -> el admin fija el foco (verde/azul/amarillo/rojo);
                           para 'amarillo' puede indicar los minutos del
                           cronómetro (fin = ahora + minutos).
    """
    __tablename__ = 'semaforo_focos'

    # Re-declaración de `modulo_id` (heredado): añade UNIQUE (1 fila/módulo)
    modulo_id = db.Column(INTEGER(unsigned=True),
                          db.ForeignKey('modulos_esp32.id'),
                          unique=True, nullable=False)
    foco_activo = db.Column(db.Enum('verde', 'azul', 'amarillo', 'rojo'),
                            nullable=False, default='verde')
    modo = db.Column(db.Enum('auto', 'manual'),
                     nullable=False, default='auto')
    segundos_restantes = db.Column(db.Integer)
    fin = db.Column(db.DateTime)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow)

    modulo = db.relationship('ModuloESP32', backref='semaforo_foco')

    def etiqueta_corta(self):
        return f'Foco {self.foco_activo} ({self.modo})'

    def __repr__(self):
        return f'<SemaforoFoco mod {self.modulo_id} -> {self.foco_activo} ({self.modo})>'