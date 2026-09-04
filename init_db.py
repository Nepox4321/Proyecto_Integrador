# -*- coding: utf-8 -*-
"""Utilidad: crea las tablas en la base MySQL `autonova` e inserta datos semilla.
Uso:
    py init_db.py            # crea tablas + puebla datos de ejemplo
    py init_db.py --create   # solo crea las tablas (sin datos)
    py init_db.py --seed     # crea tablas sin reiniciar + puebla datos
    py init_db.py --reset    # borra y recrea las tablas + datos
"""
import sys
from datetime import datetime

from werkzeug.security import generate_password_hash

from app import app, init_database, ADMIN_EMAIL, ADMIN_PASSWORD
from models import db, Usuario, Sucursal, Vehiculo, ModuloESP32


def seed():
    """Datos de ejemplo para poder visualizar la app sin escritura manual."""
    with app.app_context():
        # Sucursales
        if Sucursal.query.count() == 0:
            db.session.add_all([
                Sucursal(nombre='Monterrey Centro', ciudad='Monterrey',
                         direccion='Av. Paseo 1000', telefono='+52 81 1111 2222'),
                Sucursal(nombre='San Pedro', ciudad='San Pedro Garza',
                         direccion='Calle Real 45', telefono='+52 81 2222 3333'),
            ])
            db.session.commit()
            print('  + Sucursales de ejemplo')

        # Usuario administrador de ejemplo (credenciales demo de app.py)
        if Usuario.query.count() == 0:
            db.session.add(Usuario(
                nombre='Admin', apellidos='AutoNova',
                email=ADMIN_EMAIL,
                password_hash=generate_password_hash(ADMIN_PASSWORD),
                rol='admin', licencia='ADM-001', es_activo=True))
            db.session.commit()
            print(f'  + Usuario admin de ejemplo ({ADMIN_EMAIL} / {ADMIN_PASSWORD})')

        # Vehículos de ejemplo
        if Vehiculo.query.count() == 0:
            mk = [
                ('Mercedes-Benz', 'Clase E 400', 'MEC-72-11', 'elegante', 128, 'vehiculo1.jpg'),
                ('Lamborghini', 'Huracán EVO', 'LMB-01-99', 'deportivo', 320, 'lambo.jpg'),
                ('Porsche', '911 Carrera', 'PRS-23-10', 'deportivo', 450, 'mercedes.jpg'),
                ('BMW', 'X5 M', 'BMW-88-77', 'suv', 260, 'vehiculo4.jpg'),
                ('Tesla', 'Model S', 'TSL-00-EV', 'electrico', 340, 'vehiculo5.jpg'),
                ('Audi', 'Q7', 'ADQ-31-24', 'suv', 240, 'vehiculo6.jpg'),
            ]
            for i, (marca, modelo, placa, cat, tarifa, imagen) in enumerate(mk, 1):
                db.session.add(Vehiculo(
                    marca=marca, modelo=modelo, placa=placa, categoria=cat,
                    tarifa_dia=tarifa, imagen_url=imagen,
                    estado='alquilado' if i == 3 else
                           ('reservada' if i == 5 else 'disponible'),
                    sucursal_id=1 if i <= 3 else 2))
            db.session.commit()
            print('  + 6 vehículos de ejemplo')

        # Módulos ESP32
        if ModuloESP32.query.count() == 0:
            db.session.add_all([
                ModuloESP32(codigo='ESP32-AUTONOVA-001', nombre='Módulo ESP32-001',
                            vehiculo_id=1, estado='conectado', ip_local='192.168.1.101',
                            ultimo_heartbeat=datetime.utcnow()),
                ModuloESP32(codigo='ESP32-AUTONOVA-002', nombre='Módulo ESP32-002',
                            vehiculo_id=2, estado='esperando', ip_local='192.168.1.102'),
                ModuloESP32(codigo='ESP32-AUTONOVA-003', nombre='Módulo ESP32-003',
                            vehiculo_id=3, estado='apagado', ip_local='192.168.1.103'),
            ])
            db.session.commit()
            print('  + 3 módulos ESP32 de ejemplo')


def main():
    args = sys.argv[1:]
    reset = '--reset' in args
    seed_data = '--create' not in args

    if reset:
        with app.app_context():
            db.drop_all()
        print('Tablas eliminadas (reset).')

    if not init_database():
        print('\nNo se pudo inicializar MySQL. Revisa DB_USER y DB_PASSWORD en .env.')
        return 1
    if seed_data:
        seed()
    return 0


if __name__ == '__main__':
    import sys
    exit_code = main()
    if exit_code == 0:
        print('\nListo. Ahora ejecuta:  py app.py')
    raise SystemExit(exit_code)