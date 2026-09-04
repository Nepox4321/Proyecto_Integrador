"""Configuración central de la aplicación AutoNova.

Cadena de conexión MySQL → base de datos `autonova`.
Valores por defecto: host=localhost, puerto=3306, usuario=root.
La contraseña se lee desde variables de entorno (o un archivo `.env`)
para no exponer credenciales en el código:
    DB_PASSWORD=tu_password
"""
import os
from urllib.parse import quote_plus

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'cambia-esta-clave-en-produccion')

    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = os.environ.get('DB_PORT', '3306')
    DB_USER = os.environ.get('DB_USER', 'root')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
    DB_NAME = os.environ.get('DB_NAME', 'autonova')

    SQLALCHEMY_DATABASE_URI = (
        f'mysql+pymysql://{DB_USER}:{quote_plus(DB_PASSWORD)}'
        f'@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_recycle': 280,
        'pool_pre_ping': True,
    }

    ESP32_ENDPOINT = os.environ.get('ESP32_ENDPOINT', 'http://192.168.100.93:5000/api')