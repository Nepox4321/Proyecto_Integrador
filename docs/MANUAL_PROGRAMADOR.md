# Manual de programador de AutoNova

## 1. Alcance

Este documento explica cómo instalar, ejecutar, mantener y extender AutoNova. El backend está construido con Flask y Flask-SQLAlchemy; la persistencia usa MySQL; las vistas usan Jinja2, Bootstrap y CSS/JavaScript; la integración física se realiza con ESP32.

## 2. Requisitos

- Python 3.11 o posterior.
- MySQL 8.0 o MariaDB.
- Arduino IDE y tarjeta ESP32, solo si se probará el hardware.
- Dependencias de `requirements.txt`.

## 3. Instalación local

Desde la raíz del proyecto:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
```

Cree `.env` con valores locales:

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=su_clave
DB_NAME=autonova
SECRET_KEY=una-clave-local-larga
ESP32_ENDPOINT=http://127.0.0.1:5000/api
```

Inicialice la base:

```powershell
py init_db.py
py app.py
```

La aplicación queda disponible en `http://127.0.0.1:5000`.

> `.env` está excluido por `.gitignore` y nunca debe publicarse.

## 4. Arquitectura

- `app.py`: aplicación Flask, rutas web, autenticación, checkout, panel administrativo y API del ESP32.
- `models.py`: entidades ORM, reglas de dominio y contratos abstractos.
- `config.py`: configuración desde variables de entorno.
- `init_db.py`: creación y carga inicial de la base.
- `templates/`: vistas Jinja2.
- `static/`: estilos, imágenes y JavaScript.
- `firmware/esp32_autonova/`: firmware Arduino del módulo físico.
- `docs/`: documentación técnica y de usuario.

El flujo principal es navegador -> Flask -> SQLAlchemy/MySQL. El ESP32 consume la API REST para enviar heartbeat y telemetría, consultar estado y recibir comandos.

## 5. Requisitos de POO

### 5.0 Clases, herencia y conexión con la base de datos

En AutoNova cada modelo de `models.py` es una clase Python administrada por
SQLAlchemy. La clase representa una entidad del negocio y su atributo
`__tablename__` indica la tabla MySQL asociada. Por ejemplo, `Vehiculo` se
guarda en `vehiculos` y `Usuario` en `usuarios`.

La correspondencia principal es:

| Código POO | Persistencia SQLAlchemy/MySQL |
|---|---|
| Clase `Usuario` | Tabla `usuarios` |
| Atributo `email` | Columna `usuarios.email` |
| `db.Column(..., primary_key=True)` | Clave primaria `id` |
| `db.ForeignKey('usuarios.id_usuario')` | Clave foránea hacia otra tabla |
| `db.relationship(...)` | Navegación entre objetos relacionados |
| `db.Enum(...)` | Columna con valores restringidos en MySQL |

La herencia se integra con el ORM mediante clases base abstractas:

```text
DomainModel (base ORM abstracta)
└── Transaccion (contrato común)
	├── Reserva -> tabla reservas
	└── Venta   -> tabla ventas

EntidadModuloESP32 (base ORM abstracta)
├── TelemetriaESP32 -> tabla telemetria_esp32
├── ComandoESP32    -> tabla comandos_esp32
└── SemaforoFoco    -> tabla semaforo_focos
```

`Transaccion` reutiliza `id`, `usuario_id` y `vehiculo_id`; SQLAlchemy copia
esas columnas en las tablas concretas. La clase abstracta no crea una tabla
`transaccion`, por lo que la herencia de Python no obliga a cambiar el esquema
existente. `Reserva` y `Venta` agregan sus propias columnas y conservan las
claves foráneas hacia `usuarios` y `vehiculos`.

El flujo de guardado es:

1. Una ruta de `app.py` crea o modifica un objeto, por ejemplo `Reserva`.
2. `db.session.add(objeto)` lo registra en la sesión de SQLAlchemy.
3. `db.session.commit()` convierte los cambios en `INSERT` o `UPDATE` de MySQL.
4. SQLAlchemy asigna la clave primaria generada por la base y actualiza el objeto.
5. Una consulta como `Reserva.query.all()` reconstruye objetos Python desde las filas.

Las relaciones permiten navegar sin escribir SQL manual: `reserva.usuario`,
`reserva.vehiculo` y `vehiculo.reservas`. Las consultas siguen ejecutándose
contra MySQL; el ORM solo traduce entre objetos y filas.

Al agregar una clase nueva, defina `__tablename__`, sus columnas, claves
foráneas y relaciones; después revise `init_db.py` y el esquema SQL. No cambie
una columna existente sin una migración, porque `db.create_all()` crea tablas
faltantes pero no modifica de forma segura todas las tablas ya existentes.

### 5.1 Polimorfismo y reutilización: 3.1

`Transaccion` es una base común para `Reserva` y `Venta`. Reutiliza identificadores y relaciones, además de los métodos `es_alquiler()` y `codigo_corto()`.

Las subclases implementan `tipo_transaccion()`, `importe()` y `resumen()` con reglas diferentes. `resumir_transacciones()` recibe una colección mixta y llama a `resumen()` sin preguntar la clase concreta. Esto demuestra despacho dinámico y sustitución polimórfica.

`EntidadModuloESP32` reutiliza `id` y `modulo_id` para `TelemetriaESP32`, `ComandoESP32` y `SemaforoFoco`. Todas implementan `etiqueta_corta()`.

### 5.2 Sobrecarga: 3.2

Python no crea varias implementaciones de un método por firma como otros lenguajes. En `models.py`, `Transaccion.codigo_corto()` usa `typing.overload` para declarar las formas válidas:

```python
transaccion.codigo_corto()       # AN-0001 o VTA-0001
transaccion.codigo_corto(True)   # conserva el prefijo
transaccion.codigo_corto(False)  # solo 0001
```

Las declaraciones `@overload` sirven para análisis estático y una implementación común resuelve las llamadas en tiempo de ejecución. El prefijo sigue siendo polimórfico porque depende de `tipo_transaccion()`.

### 5.3 Clases abstractas y enums: 3.3

`DomainMeta` combina la metaclase de SQLAlchemy con `ABCMeta`. `DomainModel`, `Transaccion` y `EntidadModuloESP32` son bases abstractas y usan `@abstractmethod` para exigir contratos a sus subclases.

Los enums Python reutilizables se encuentran en `models.py`:

- `TipoTransaccion`.
- `EstadoVehiculo`.
- `ComandoESP32Enum`.
- `ModoSemaforo`.

Sus valores son cadenas compatibles con los valores ya existentes en MySQL. Las columnas `db.Enum` conservan el contrato de la base de datos y los enums Python centralizan los valores usados por la lógica de dominio.

### 5.4 Cómo leer el código con comentarios

Los comentarios con `#` identifican las capas y los puntos de conexión más
importantes: configuración, modelos ORM, inicialización de tablas, rutas web,
consultas, transacciones de base de datos y API ESP32. Las docstrings explican
el contrato de cada clase o función; los comentarios cortos junto a una
operación SQL explican por qué se usa `add`, `flush`, `commit` o `rollback`.
Para seguir una operación completa, empiece en la ruta de `app.py`, continúe
con el modelo utilizado y termine en la tabla indicada por `__tablename__`.

## 6. API ESP32

El firmware debe apuntar al endpoint configurado en `ESP32_ENDPOINT`. Las rutas principales son:

| Método | Ruta | Uso |
|---|---|---|
| `POST` | `/api/esp/<codigo>/heartbeat` | Envía conexión y telemetría del módulo. |
| `GET` | `/api/esp/<codigo>/estado` | Consulta semáforo, reserva activa y temporizador. |
| `GET` | `/api/esp/<codigo>/comando` | Obtiene el siguiente comando pendiente. |
| `GET` | `/api/esp` | Lista módulos para el panel. |

El código del módulo debe coincidir con `modulos_esp32.codigo`. Revise `app.py` y `firmware/esp32_autonova/esp32_autonova.ino` cuando cambie el contrato.

## 7. Base de datos

`lip.sql.txt` contiene el esquema de referencia. `init_db.py` crea tablas y datos iniciales. `docs/ANALISIS_BASE_DE_DATOS.md` explica las relaciones y enums de persistencia.

Para cambios de esquema en una instalación existente, use una migración controlada. No ejecute `--reset` salvo en una base de desarrollo, porque elimina la información existente.

## 8. Validación y diagnóstico

Comprobaciones rápidas:

```powershell
py -m py_compile app.py models.py config.py init_db.py
py -c "from models import TipoTransaccion, EstadoVehiculo; print(TipoTransaccion.ALQUILER.value, EstadoVehiculo.DISPONIBLE.value)"
```

Si la aplicación inicia con datos de ejemplo, revise `DB_HOST`, `DB_PORT`, usuario, contraseña, nombre de base y que MySQL esté activo. Para problemas del ESP32, compruebe conectividad entre la placa y el equipo que ejecuta Flask, además del código del módulo.

## 9. Seguridad antes de producción

- Cambie `SECRET_KEY` y la contraseña de administración demo.
- Use un servidor WSGI de producción; no exponga el servidor de desarrollo con `debug=True`.
- Proteja la API del ESP32 con autenticación o una red aislada.
- Valide y registre los cambios administrativos.
- No publique `.env`, contraseñas, dumps con datos reales ni direcciones privadas innecesarias.
