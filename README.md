
# AutoNova

**AutoNova** es una plataforma web completa de alquiler, renta y venta de
vehículos premium, con monitoreo IoT en tiempo real mediante módulos **ESP32**.
Fue desarrollada como **Proyecto Integrador** y su diseño visual proviene de
**Figma**.

La aplicación combina un backend **Flask** con una base de datos **MySQL**
(SQLAlchemy ORM), plantillas **Jinja2** + **Bootstrap 5** en el frontend, y un
firmware de bajo nivel para ESP32 que gestiona un semáforo de luces, un
cronómetro de alquiler en un display de 7 segmentos y comunicación bidireccional
con el servidor.

---

## Tabla de contenidos

1. [Descripción general](#descripción-general)
2. [Estructura de carpetas](#estructura-de-carpetas)
3. [Arquitectura del sistema](#arquitectura-del-sistema)
4. [Guía de instalación y ejecución](#guía-de-instalación-y-ejecución)
5. [Endpoints y rutas](#endpoints-y-rutas)
6. [Modelo de datos](#modelo-de-datos)
7. [Manuales](#manuales)
8. [Guía de archivos](#guía-de-archivos)
9. [Paleta de diseño](#paleta-de-diseño)
10. [Credenciales de acceso](#credenciales-de-acceso)

---

## Descripción general

| Característica | Detalle |
|---|---|
| **Stack web** | Flask 2.3+ · Jinja2 · Bootstrap 5.3 · SQLAlchemy 2.0 |
| **Base de datos** | MySQL 8.0 (via PyMySQL) — fallback a datos semilla sin BD |
| **Firmware IoT** | ESP32 (Arduino/C++) — máquina de estados no bloqueante |
| **Diseño** | Figma → CSS personalizado (variables CSS, paleta de marca) |
| **Autenticación** | Login/registro con hash Werkzeug (bcrypt-style) |
| **Admin panel** | Dashboard con KPIs, gestión de flota, reservas, clientes y ESP32 |
| **IoT bidireccional** | Heartbeat, telemetría, comandos y semáforo vial |

AutoNova permite a los usuarios buscar, alquilar y comprar vehículos premium,
gestionar reservas y seguir el estado de su renta en tiempo real. El panel de
administración brinda control total sobre la flota, las reservas, los clientes y
los módulos ESP32 que monitorean cada vehículo.

---

## Estructura de carpetas

```
Proyecto integrador/
├── .env                          # Variables de entorno (credenciales, endpoints)
├── .vscode/
│   └── settings.json             # Configuración de VS Code (MCP Figma)
├── app.py                        # Aplicación Flask principal (rutas + API)
├── config.py                     # Configuración central (MySQL, Flask, ESP32)
├── init_db.py                    # Utilidad: crea tablas + datos semilla
├── models.py                     # Modelos ORM (SQLAlchemy)
├── requirements.txt              # Dependencias de Python
├── docs/
│   ├── ANALISIS_BASE_DE_DATOS.md # Análisis del esquema SQL relacional
│   ├── MANUAL_USUARIO.md         # Operación de la plataforma
│   └── MANUAL_PROGRAMADOR.md     # Instalación, arquitectura y POO
├── firmware/
│   └── esp32_autonova/
│       └── esp32_autonova.ino    # Firmware ESP32 (máquina de estados + IoT)
├── static/
│   ├── css/
│   │   ├── custom.css            # Paleta de colores + estilos base/globales
│   │   ├── home.css              # Estilos de la página de inicio
│   │   ├── catalogo.css          # Estilos del catálogo / flota
│   │   ├── perfil.css            # Estilos del perfil de usuario
│   │   └── admin.css             # Estilos del panel de administración
│   ├── js/
│   │   ├── main.js               # Interactividad general (filtros, checkout, nav)
│   │   └── esp32.js              # Polling en tiempo real del monitoreo ESP32
│   └── media/                    # Imágenes (hero, galería, vehículos)
│       ├── auth.jpg
│       ├── galeria1.jpg
│       ├── galeria2.jpg
│       ├── galeria3.jpg
│       ├── hero.jpg
│       ├── lambo.jpg
│       ├── mercedes.jpg
│       ├── vehiculo1.jpg
│       ├── vehiculo3.jpg
│       ├── vehiculo4.jpg
│       ├── vehiculo5.jpg
│       └── vehiculo6.jpg
└── templates/                    # Plantillas Jinja2 (HTML)
    ├── base.html                 # Layout base (navbar + footer + scripts globales)
    ├── inicio.html               # Página de inicio (hero + destacados)
    ├── catalogo.html             # Catálogo / flota completa
    ├── vehiculo.html             # Detalle de un vehículo
    ├── checkout.html             # Formulario de reserva (cálculo de total)
    ├── confirmacion.html         # Confirmación de reserva
    ├── login.html                # Iniciar sesión
    ├── registro.html             # Registro de nueva cuenta
    ├── perfil.html               # Mi Perfil (datos, renta activa, historial)
    ├── admin_base.html           # Layout base del panel admin
    ├── admin.html                # Dashboard (KPIs + ESP32)
    ├── admin_vehiculos.html      # Gestión de vehículos
    ├── admin_reservas.html       # Gestión de reservas
    ├── admin_clientes.html       # Gestión de clientes
    ├── admin_esp32.html          # Gestión de módulos ESP32
    ├── admin_esp32_detalle.html  # Detalle de un módulo ESP32
    ├── admin_reportes.html       # Reportes y métricas
    ├── admin_modal_vehiculo.html # Modal: añadir/editar vehículo
    ├── admin_modal_usuario.html  # Modal: añadir/editar usuario
    └── admin_modal_esp32.html    # Modal: añadir/editar módulo ESP32
---

## Arquitectura del sistema

```
                    ┌─────────────────────────────┐
                    │         Navegador           │
                    │  (HTML/Jinja + Bootstrap 5   │
                    │   CSS variables + JS)        │
                    └──────────┬─────────┬────────┘
                               │  HTTP   │
                               │         │
                    ┌──────────▼──┐  ┌───▼──────────┐
                    │  Flask App  │  │   API REST   │
                    │  (app.py)   │  │  (/api/esp)  │
                    └──────────┬──┘  └───────┬──────┘
                               │              │
                    ┌──────────▼──────────────▼──────┐
                    │        MySQL (autonova)        │
                    │  (SQLAlchemy ORM — models.py)  │
                    └────────────────────────────────┘

                    ┌─────────────────────────────┐
                    │        ESP32 Hardware        │
                    │  (esp32_autonova.ino)        │
                    │  • Display 5641BS 7-seg     │
                    │  • Semáforo (verde/azul/    │
                    │    amarillo/rojo)            │
                    │  • Motor DC + Buzzer         │
                    │  • WiFi → HTTPClient         │
                    └──────────┬────────┬─────────┘
                               │  HTTP  │
                               │ Polls  │
                               │ (5s hb │
                               │  10s   │
                               │  cmd)  │
                    ┌──────────▼────────▼──────────┐
                    │         Flask App            │
                    │  /api/esp/<ref>/heartbeat    │
                    │  /api/esp/<ref>/estado       │
                    │  /api/esp/<ref>/comando      │
                    └──────────────────────────────┘
```

### Flujo de comunicación ESP32 ↔ Servidor

1. El ESP32 se conecta al WiFi y envía un **heartbeat** cada 5 s a
   `/api/esp/<codigo>/heartbeat` con telemetría (lat/lng, velocidad, batería,
   RSSI).
2. El servidor responde con el **estado del semáforo** (foco activo +
   cronómetro restante) calculado según las reservas activas.
3. Cada 10 s, el ESP32 consulta `/api/esp/<codigo>/comando` para recoger
   órdenes del panel admin (ping, reiniciar, encender, apagar, abrir_cajuela).
4. El panel admin (`/admin/esp32`) muestra el estado en tiempo real vía polling
   de `/api/esp` (JS: `esp32.js`).

---

## Guía de instalación y ejecución

### Prerrequisitos

- **Python** 3.11+
- **MySQL** 8.0 (o MariaDB) con la base `autonova`
- **ESP32** con las librerías `WiFi.h` e `HTTPClient.h`

### 1. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 2. Configurar el entorno

Edita `.env` con tus credenciales de MySQL y el endpoint de los ESP32:

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=tu_password
DB_NAME=autonova
SECRET_KEY=cambia-esta-clave-en-produccion
ESP32_ENDPOINT=http://192.168.3.8:5000/api
```

### 3. Inicializar la base de datos

```bash
py init_db.py          # crea tablas + datos semilla
# o para resetear todo:
py init_db.py --reset
```

### 4. Ejecutar la aplicación

```bash
py app.py
# Abre http://127.0.0.1:5000
```

### 5. Panel de administración

Accede con las credenciales demo (se crean automáticamente al iniciar):

- **Email:** `admin@autonova.mx`
- **Contraseña:** `admin123`

### 6. Firmware ESP32

1. Abre `firmware/esp32_autonova/esp32_autonova.ino` en Arduino IDE.
2. Ajusta `WIFI_SSID`, `WIFI_PASSWORD`, `SERVER_HOST` y `MODULO_REF`.
3. Selecciona tu placa ESP32 y sube el firmware.

---

## Endpoints y rutas

### Rutas web (Flask)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Página de inicio (hero + vehículos destacados) |
| GET | `/flota` | Catálogo completo de vehículos |
| GET | `/vehiculo/<id>` | Detalle de un vehículo |
| GET/POST | `/checkout/<id>` | Formulario de reserva con cálculo de total |
| GET | `/confirmacion` | Confirmación de reserva |
| GET | `/login` | Iniciar sesión |
| GET/POST | `/registro` | Registro de nueva cuenta |
| GET | `/logout` | Cerrar sesión |
| GET | `/perfil` | Mi Perfil (datos, renta activa, historial) |
| GET | `/perfil/exportar` | Exportar historial de reservas (CSV) |
| POST | `/perfil/reserva/<rid>/cancelar` | Cancelar una reserva |
| GET | `/admin` | Dashboard de administración |
| GET | `/admin/vehiculos` | Gestión de flota |
| GET | `/admin/reservas` | Gestión de reservas |
| GET | `/admin/clientes` | Gestión de clientes |
| GET | `/admin/esp32` | Gestión de módulos ESP32 |
| GET | `/admin/reportes` | Reportes y métricas + transacciones recientes (Reservas + Ventas) |

### Rutas admin (acciones POST)

| Método | Ruta | Acción |
|--------|------|--------|
| POST | `/admin/esp32/nuevo` | Registrar un nuevo módulo ESP32 |
| POST | `/admin/esp32/<mid>/editar` | Editar módulo ESP32 |
| POST | `/admin/esp32/<mid>/asignar` | Asignar/desasignar vehículo al módulo (semáforo a automático) |
| POST | `/admin/esp32/<mid>/estado` | Cambiar estado (conectado/esperando/apagado) |
| POST | `/admin/esp32/<mid>/semaforo` | Fijar foco del semáforo (manual/auto) |
| POST | `/admin/esp32/<mid>/eliminar` | Eliminar un módulo |
| POST | `/admin/esp32/<mid>/comando` | Enviar comando al ESP32 (ping, encender, etc.) |
| GET | `/admin/esp32/<mid>/telemetria` | Ver telemetría del módulo |
| POST | `/admin/vehiculos/nuevo` | Añadir vehículo |
| POST | `/admin/vehiculos/<vid>/estado` | Cambiar estado del vehículo |
| POST | `/admin/vehiculos/<vid>/eliminar` | Eliminar vehículo |
| POST | `/admin/reservas/<rid>/estado` | Cambiar estado de reserva |
| POST | `/admin/clientes/<uid>/toggle` | Activar/desactivar cliente |
| POST | `/admin/usuarios/nuevo` | Crear usuario desde el admin |
| POST | `/admin/usuarios/<uid>/eliminar` | Eliminar usuario |

### API REST (ESP32)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/esp` | Estado de todos los módulos ESP32 (JSON, para polling) |
| GET | `/api/esp/<modulo_id>/status` | Estado individual de un módulo |
| POST | `/api/esp/<modulo_ref>/heartbeat` | Actualizar estado + telemetría (lo llama el ESP32) |
| GET | `/api/esp/<modulo_ref>/estado` | Estado del semáforo (luces + cronómetro) |
| GET | `/api/esp/<modulo_ref>/comando` | Recoger comando pendiente (lo llama el ESP32) |

---

## Modelo de datos

La base de datos `autonova` está compuesta por las siguientes entidades
(modeladas en `models.py` como clases SQLAlchemy):

```
usuarios          1 ──* reservas      * ──1 vehiculos
                  1 ──* modulos_esp32 1 ──1 vehiculos
modulos_esp32     1 ──* telemetria_esp32
reservas          1 ──* pagos
ventas            1 ──1 reserva (opcional)
                  * ──1 vehiculos
```

| Tabla | Entidad | Descripción |
|-------|---------|-------------|
| `usuarios` | Usuario | Clientes y administradores (email único, hash de contraseña) |
| `sucursales` | Sucursal | Puntos físicos de entrega/recepción |
| `vehiculos` | Vehiculo | Unidades de la flota (marca, placa, tarifa, estado) |
| `reservas` | Reserva | Alquileres: usuario ↔ vehículo con fechas y total (hereda de `Transaccion`) |
| `pagos` | Pago | Pagos asociados a reservas |
| `ventas` | Venta | Compras directas de vehículos (hereda de `Transaccion`) |
| `modulos_esp32` | ModuloESP32 | Hardware IoT (código, IP, estado, firmware) |
| `telemetria_esp32` | TelemetriaESP32 | Lecturas en vivo (lat/lng, velocidad, batería, RSSI) |
| `comandos_esp32` | ComandoESP32 | Órdenes encoladas desde el panel admin |
| `semaforo_focos` | SemaforoFoco | Estado de los focos del semáforo (fuente de verdad en BD) |

> El esquema completo con SQL DDL está en `docs/ANALISIS_BASE_DE_DATOS.md`.

### Clases y polimorfismo (POO)

Las entidades se modelan como clases ORM en `models.py`. Junto a las clases
independientes (`Usuario`, `Sucursal`, `Vehiculo`, `Pago` y `ModuloESP32`),
existen **dos familias de clases con herencia y polimorfismo real**:

| Clase base (abstracta) | Subclases | Métodos polimórficos |
|------------------------|-----------|----------------------|
| `Transaccion` | `Reserva`, `Venta` | `tipo_transaccion()`, `importe()`, `resumen()`, `codigo_corto()` |
| `EntidadModuloESP32` | `TelemetriaESP32`, `ComandoESP32`, `SemaforoFoco` | `etiqueta_corta()` |

- **`Transaccion`** agrupa lo común de `Reserva` y `Venta` (`id`, `usuario_id`,
  `vehiculo_id`) y define un contrato que cada subclase implementa a su manera:
  `Reserva.tipo_transaccion()` devuelve `'alquiler'` y su `importe()` usa el
  campo `total`, mientras `Venta` devuelve `'venta'` y usa `precio_final`.
  Métodos de la base como `es_alquiler()` y `codigo_corto()` (AN-XXXX / VTA-XXXX)
  aprovechan ese despacho dinámico.
- **`EntidadModuloESP32`** agrupa `id` y `modulo_id` de las entidades IoT, y cada
  subclase sobrescribe `etiqueta_corta()` (`Telemetría #n`, `Comando reiniciar`,
  `Foco verde (auto)`).

El polimorfismo se usa en producción: en `/admin/reportes` (`app.py`) se mezclan
objetos `Reserva` y `Venta` en una misma lista y a todos se les invoca
`t.resumen()` de forma uniforme (`app.py:1205`).

> Ambas bases son abstractas (`__abstract__ = True`): **no crean tabla propia**
> y el esquema físico de la base de datos permanece igual.

### Sobrecarga, enums y reutilización

El requisito 3.2 se demuestra en `Transaccion.codigo_corto()`, que declara con
`typing.overload` las llamadas `codigo_corto()`, `codigo_corto(True)` y
`codigo_corto(False)`, manteniendo una sola implementación en tiempo de
ejecución. La última forma devuelve únicamente el consecutivo numérico.

El requisito 3.3 también cuenta con enums Python reutilizables:
`TipoTransaccion`, `EstadoVehiculo`, `ComandoESP32Enum` y `ModoSemaforo`.
Sus valores coinciden con los `db.Enum` persistidos en MySQL, por lo que la
lógica de dominio tiene valores centralizados sin modificar el esquema.

## Manuales

- [Manual de usuario](docs/MANUAL_USUARIO.md): acceso, reservas, perfil y
  panel administrativo.
- [Manual de programador](docs/MANUAL_PROGRAMADOR.md): instalación,
  arquitectura, API ESP32, base de datos y requisitos de POO.

---

## Guía de archivos

### Backend (Python / Flask)

#### `app.py`
Aplicación Flask principal. Define todas las rutas web, la API REST para los
ESP32, el contexto global de plantillas (`session_user`, `session_rol`,
`ESP32_ENDPOINT`) y la inicialización de la base de datos al arranque
(`init_database()`) con la cuenta administradora demo. Incluye datos semilla
(`SAMPLE_VEHICULOS`, `SAMPLE_MODULOS`) que se usan automáticamente si la base
de datos no responde, garantizando que la interfaz siempre muestre contenido.

Los códigos de reserva se generan con el método polimórfico `codigo_corto()`
(`AN-XXXX` para alquileres y `VTA-XXXX` para ventas), reemplazando la
concatenación manual en checkout, perfil, exportación CSV y cancelación. El
endpoint `/admin/reportes` consolida además las **transacciones recientes**
(Top 5 de `Reserva` + Top 5 de `Venta` ordenadas por fecha, hasta 8) y las
serializa con `resumen()` para el bloque polimórfico del panel.

#### `config.py`
Clase `Config` con la configuración central de la aplicación: cadena de
conexión MySQL (`mysql+pymysql://`), `SECRET_KEY` y `ESP32_ENDPOINT`, todos
cargados desde variables de entorno (o el archivo `.env` via `python-dotenv`).
La contraseña se escapa con `quote_plus` para manejar caracteres especiales.

#### `models.py`
Definición de todos los modelos ORM con SQLAlchemy: `Usuario`, `Sucursal`,
`Vehiculo`, `Reserva`, `Pago`, `Venta`, `ModuloESP32`, `TelemetriaESP32`,
`ComandoESP32` y `SemaforoFoco`. Contiene la instancia global `db =
SQLAlchemy()` que se enlaza a la app con `db.init_app(app)` en `app.py`.

Los modelos aplican **herencia y polimorfismo** (POO):

- `Transaccion` (clase base abstracta, `__abstract__ = True`) agrupa lo común
  de `Reserva` y `Venta` (`id`, `usuario_id`, `vehiculo_id`) y define el
  contrato polimórfico `tipo_transaccion()`, `importe()`, `codigo_corto()` y
  `resumen()`, implementado distinto por cada subclase.
- `EntidadModuloESP32` (clase base abstracta) agrupa `id` y `modulo_id` de
  `TelemetriaESP32`, `ComandoESP32` y `SemaforoFoco`, con el método
  polimórfico `etiqueta_corta()`.

Como las bases son abstractas, **el esquema físico de la base de datos no
cambia**: las columnas se copian a las tablas hijas existentes.

#### `init_db.py`
Utilidad de línea de comandos para crear las tablas en MySQL e insertar datos
semilla (sucursales, admin demo, 6 vehículos, 3 módulos ESP32). Comandos:
`py init_db.py`, `py init_db.py --create`, `py init_db.py --reset`.

#### `requirements.txt`
Dependencias de Python: Flask, Flask-SQLAlchemy, SQLAlchemy, PyMySQL,
python-dotenv y cryptography.

### Configuración

#### `.env`
Archivo de variables de entorno (NO subir a repositorios públicos). Contiene
las credenciales de MySQL (`DB_PASSWORD`), la clave secreta de Flask
(`SECRET_KEY`) y el endpoint de los módulos ESP32 (`ESP32_ENDPOINT`).

#### `.vscode/settings.json`
Configuración del entorno de desarrollo en VS Code. Incluye el servidor MCP de
Figma para integración de diseño.

#### `.git/`
Repositorio Git del proyecto. Contiene todo el historial de versiones.


### Frontend (CSS)

#### `static/css/custom.css`
**Estilos globales.** Define la paleta de colores del proyecto como variables
CSS, tipografías (Inter/Poppins), botones, navbar, footer, tarjetas, badges y
utilidades de spacing. Es el archivo base importado por todas las páginas.

#### `static/css/home.css`
**Página de inicio.** Hero section, sección de estadísticas, filtros de
categorías, tarjetas de vehículos destacados, CTA y botón de volver arriba.

#### `static/css/catalogo.css`
**Catálogo.** Layout de cuadrícula de vehículos, filtros de búsqueda y
categoría, tarjetas con overlay de estado.

#### `static/css/perfil.css`
**Perfil de usuario.** Layout de datos de cuenta, renta activa en card
destacada, historial de reservas en tabla, barra de progreso de días.

#### `static/css/admin.css`
**Panel de administración.** Tarjetas KPI, tabla de flota con badges de estado,
tarjetas de módulos ESP32, pills de semáforo y estilos para modals.

### Frontend (JavaScript)

#### `static/js/main.js`
**Interactividad general.** Marca el enlace de nave activo según la ruta
(`data-active`), filtra el catálogo por categoría y búsqueda en tiempo real,
calcula el total del checkout por días, y gestiona el botón "volver arriba".

#### `static/js/esp32.js`
**Monitoreo IoT en tiempo real.** Hace polling cada 3 s a `/api/esp`, actualiza
las tarjetas de estado de los módulos (conectado/esperando/apagado), muestra el
tiempo online, el semáforo de luces (verde/azul/amarillo/rojo) con colores y
cronómetro de cuenta regresiva, y la animación de la barra de latencia
(equalizer).

#### `static/media/`
Imágenes estáticas referenciadas por las plantillas:

| Archivo | Uso |
|---------|-----|
| `hero.jpg` | Imagen hero de la página de inicio |
| `auth.jpg` | Imagen de fondo de login y registro |
| `galeria1-3.jpg` | Galería de imágenes en el detalle de vehículo |
| `lambo.jpg` | Imagen del Lamborghini Huracán EVO |
| `mercedes.jpg` | Imagen del Mercedes-Benz Clase E 400 |
| `vehiculo1.jpg`, `vehiculo3-6.jpg` | Imágenes de la flota (una por vehículo) |


### Plantillas (`templates/`)

#### Layout base

- **`base.html`** — Layout maestro de la aplicación pública. Contiene el
  `<head>` con fuentes de Google Fonts, Bootstrap 5 y los CSS globales
  (`custom.css`, `home.css`), la barra de navegación responsive con enlaces
  dinámicos según el estado de sesión, el sistema de mensajes flash y el footer
  con enlaces de servicios, soporte y redes sociales. Incluye el script
  `main.js` global.

- **`admin_base.html`** — Layout maestro del panel de administración. Navbar
  lateral con navegación entre secciones (Flota, Reservas, Clientes, ESP32,
  Reportes), carga `admin.css` y `esp32.js`.

#### Páginas públicas

- **`inicio.html`** — Homepage: hero principal, selector de fechas y lugar de
  recogida, estadísticas de la flota (vehículos, clientes, calificación,
  entrega 24 h), filtros de categoría y tarjetas de vehículos destacados con
  badge de estado y botón de reserva.

- **`catalogo.html`** — Catálogo completo con filtro de búsqueda por marca y
  categoría, ordenación y tarjetas de todos los vehículos disponibles con
  estado, tarifa y botón de detalle.

- **`vehiculo.html`** — Detalle de un vehículo: galería de imágenes,
  especificaciones técnicas (marca, modelo, año, transmisión, combustible,
  kilometraje), tarifas y formulario de fechas para iniciar el checkout.

- **`checkout.html`** — Formulario de reserva: selección de fechas de inicio y
  fin, sucursal de recogida, cálculo automático del total en vivo (JS), valida-
  ción de disponibilidad y confirmación de datos del cliente.

- **`confirmacion.html`** — Página de confirmación de reserva con código AN-XXXX,
  resumen del vehículo, fechas, total y botón para ver en el perfil.

- **`login.html`** — Formulario de inicio de sesión (email + contraseña) con
  enlace a registro y mensajes flash de error.

- **`registro.html`** — Formulario de creación de cuenta (nombre, apellidos,
  email, teléfono, licencia, contraseña con verificación).

- **`perfil.html`** — "Mi Perfil": datos de la cuenta, renta activa con barra
  de progreso de días transcurridos vs. total, historial de reservas en tabla
  con estado y botón de exportar a CSV.


#### Panel de administración

- **`admin.html`** — Dashboard: tarjetas KPI (usuarios, vehículos, disponibles,
  módulos conectados), tabla resumizada de flota y panel de módulos ESP32 con
  indicador de estado en vivo y tiempo online.

- **`admin_vehiculos.html`** — Tabla completa de la flota con marca, placa,
  estado, tarifa y acciones de baja/reactivación. Incluye botón para añadir
  vehículos (modal).

- **`admin_reservas.html`** — Listado de todas las reservas con cliente,
  vehículo, fechas, total y estado. Permite cambiar el estado de cada reserva.

- **`admin_clientes.html`** — Listado de usuarios registrados con filtro por
  rol y toggle de activación. Permite crear nuevos usuarios.

- **`admin_esp32.html`** — Panel de gestión de módulos: tabla con estado, IP,
  firmware, último heartbeat, semáforo visual y acciones (editar, cambiar
  estado, semáforo, enviar comando, telemetría, eliminar).

- **`admin_esp32_detalle.html`** — Vista detallada de un módulo ESP32 con
  telemetría histórica y gráfica de señal (RSSI).

- **`admin_reportes.html`** — Reportes de métricas: ingresos por período,
  vehículos más reservados, ocupación de sucursales y tendencias. Incluye una
  tabla de **transacciones recientes** (Reservas + Ventas) con referencias
  `codigo_corto()` que se renderiza de forma uniforme gracias al método
  polimórfico `resumen()` de `Transaccion`.

#### Modals (parciales incluidos)

- **`admin_modal_vehiculo.html`** — Modal para crear/editar un vehículo (marca,
  modelo, placa, categoría, tarifa, imagen, sucursal).

- **`admin_modal_usuario.html`** — Modal para crear/editar un usuario (nombre,
  email, rol, estado).

- **`admin_modal_esp32.html`** — Modal para registrar/editar un módulo ESP32
  (código, nombre, vehículo asignado, IP, firmware).

### Firmware ESP32

#### `firmware/esp32_autonova/esp32_autonova.ino`
Firmware en C++ para ESP32 (Arduino) que **consulta el semáforo del servidor**
cada 5 s vía HTTP GET y traduce la luz del foco al hardware local, sin
bloquear el `loop()` más allá de la propia consulta:

```text
                                   ┌──────── semáforo ─────────┐
  verde     → libre/disponible           (LED verde, display "1")
  azul      → reserva por confirmar      (LED azul, display "2")
  amarillo  → alquiler EN CURSO          (LED amarillo + cuenta regresiva en minutos)
  rojo      → alquiler VENCIDO           (LED ROJO + doble pitido + "9999")
  (fallo)   → sin servidor / sin WiFi    (LED ROJO + doble pitido + "404")
```

- **Cambio de estado sólo de verdad**: guarda la última respuesta completa y
  sólo actúa cuando cambia, por lo que el buzzer y las alertas **no se repiten**
  en cada consulta.
- **LED ROJO (GPIO33)**: nuevo foco físico para el estado `rojo` del servidor
  (alquiler vencido) y para fallos de conexión WiFi/servidor, con doble pitido
  del buzzer y display `404` (estilo del código de referencia del LED rojo). La
  alerta de conexión se quita sola cuando el servidor vuelve a responder.

**Hardware gestionado:**
- Módulo numérico **TM1637** (4 dígitos, CLK=GPIO19, DIO=GPIO18) con la
  librería `TM1637Display` (sin multiplexado manual).
- Semáforo de 4 luces: verde (GPIO25), azul (GPIO26), amarillo (GPIO27) y
  rojo (GPIO33), con polaridad configurable (`ACTUADORES_ACTIVO_ALTO`).
- Buzzer (GPIO14) para alertas de vencimiento y fallo de conexión.

**Comunicación:**
- WiFi (`WiFi.h`) con timeout configurable (20 s) y reconexión automática.
- HTTPClient hacia `/api/esp/<MODULO_REF>/estado` (GET cada 5 s).
- Heartbeat opcional hacia `/api/esp/<MODULO_REF>/heartbeat` (POST cada 15 s)
  para mantener al módulo como "conectado" en el panel admin.

### Documentación

#### `docs/ANALISIS_BASE_DE_DATOS.md`
Análisis del diseño en Figma (`deskopt`) que documenta las 8 entidades
detectadas, el esquema relacional SQL propuesto (DDL MySQL 8), las relaciones
entre tablas (diagrama ER) y los KPIs derivados para el dashboard.

---

## Paleta de diseño

Las variables CSS están definidas en `static/css/custom.css`:

| Variable | Color | Uso |
|----------|-------|-----|
| `--an-cream` | `#F5F4EF` | Fondo general |
| `--an-carbono` | `#1E293B` | Navbar, footer, hero, texto primario |
| `--an-emerald` | `#059669` | Color primario (botones, links) |
| `--an-emerald-lt` | `#34D399` | Acento |
| `--an-amber` | `#F59E0B` | Estado "en curso" |
| `--an-red` | `#EF4444` | Estado "error/vencido" |

Tipografías: **Poppins** (encabezados) y **Inter** (cuerpo), ambas desde Google
Fonts.

---

## Credenciales de acceso

| Rol | Email | Contraseña |
|-----|-------|------------|
| Admin | `admin@autonova.mx` | `admin123` |

> Las credenciales admin demo se crean/actualizan automáticamente al iniciar
> `app.py` si la base de datos está disponible. Si la BD no responde, la
> aplicación funciona con datos semilla de ejemplo.
"# Proyecto_Integrador" 
"# Proyecto_Integrador" 
