# AutoNova — Análisis de Base de Datos

> **Origen:** Análisis del archivo Figma `Sin título` → página **"deskopt"** (node `20-2809`).
> **Propósito:** modelar el esquema relacional que alimenta la aplicación **AutoNova** (plataforma de alquiler/reserva y venta de vehículos premium con monitoreo IoT vía módulos ESP32).

---

## 1. Entidades detectadas en los frames

| # | Entidad | Evidencia en Figma (frame / componente) | Descripción |
|---|---------|------------------------------------------|-------------|
| 1 | **Usuario / Cliente** | `LoginPage`, `SignUpPage`, panel ESP32 (campo *"Nombre del cliente"*), navbar (*Iniciar sesión*, *Registro*), testimonial *"Cliente desde 2024 · CDMX"* | Persona registrada que inicia sesión o se registra para alquilar/comprar. |
| 2 | **Vehículo** | Tabla `AdminDashboard` (Marca/Modelo/Placa/Tarifa, imágenes `Clase E 400`, `Huracán EVO`), stat `84+ Vehículos` | Unidad de la flota: marca, modelo, placa, tarifa/día, estado (`Alquilado`/`Disponible`), imagen, categoría. |
| 3 | **Reserva / Alquiler** | Hero y navbar `Alquilar`, botones de acción, `ConfirmationPage` | Cliente ↔ vehículo con fechas, tarifa, estado y total. |
| 4 | **Venta** | Navbar `Ventas` | Compra directa de un vehículo (v1 opcional). |
| 5 | **Sucursal / Entrega** | Stat `24 h Entrega`, navbar `Flota` | Punto físico de entrega/recepción + contacto. |
| 6 | **Módulo ESP32** | Panel admin: `Módulo ESP32-001/002/003`, IDs `ESP32-AUTONOVA-001`, estados `Esperando/Conectado/Offline`, endpoint `http://192.168.1.105:5000/api` | Hardware IoT que monitorea el vehículo en tiempo real. |
| 7 | **Telemetría ESP32** | Barra "estado de conexión", latencia | Heartbeats + datos en vivo que alimentan el cronómetro. |
| 8 | **KPI / Métricas** | `AdminDashboard` grid de **4 tarjetas** | Métricas derivadas: total, alquilados, ingresos, módulos online. |

---

## 2. Modelo relacional propuesto (SQL)

```sql
-- ============================================================
--  AutoNova · Esquema relacional v1 (MySQL 8 / SQLite dev)
-- ============================================================

CREATE TABLE usuarios (
  id_usuario    INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  nombre        VARCHAR(120) NOT NULL,
  apellidos     VARCHAR(120),
  email         VARCHAR(150) NOT NULL UNIQUE,
  telefono      VARCHAR(20),
  password_hash VARCHAR(255) NOT NULL,
  licencia      VARCHAR(30),
  rol           ENUM('cliente','admin','staff') NOT NULL DEFAULT 'cliente',
  avatar_url    VARCHAR(255),
  es_activo     BOOLEAN DEFAULT 1,
  creado_en     DATETIME DEFAULT CURRENT_TIMESTAMP,
  ultimo_acceso DATETIME
);

CREATE TABLE sucursales (
  id        INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  nombre    VARCHAR(120) NOT NULL,
  ciudad    VARCHAR(80)  NOT NULL,
  direccion VARCHAR(180),
  telefono  VARCHAR(20),
  email     VARCHAR(150),
  lat       DECIMAL(10,7),
  lng       DECIMAL(10,7)
);

CREATE TABLE vehiculos (
  id               INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  marca            VARCHAR(60) NOT NULL,
  modelo           VARCHAR(120) NOT NULL,
  anio             SMALLINT,
  placa            VARCHAR(12) NOT NULL UNIQUE,   -- ej. "MEC-72-11"
  categoria        ENUM('sedan','suv','deportivo','elegante','electrico','convertible') NOT NULL DEFAULT 'sedan',
  motor            VARCHAR(60),
  transmision      ENUM('manual','automatica') DEFAULT 'automatica',
  combustible      VARCHAR(30) DEFAULT 'Gasolina',
  kilometraje      INT UNSIGNED DEFAULT 0,
  tarifa_dia       DECIMAL(10,2) NOT NULL,        -- ej. $320.00/día
  tarifa_mes       DECIMAL(10,2),
  precio_venta     DECIMAL(12,2),
  descripcion      TEXT,
  imagen_url       VARCHAR(255),
  estado           ENUM('disponible','reservada','alquilado','mantenimiento','baja') NOT NULL DEFAULT 'disponible',
  sucursal_id      INT UNSIGNED,
  disponible_desde DATE,
  veces_alquilado  INT UNSIGNED DEFAULT 0,
  creado_en        DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (sucursal_id) REFERENCES sucursales(id) ON DELETE SET NULL
);
```
CREATE TABLE reservas (
  id           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  usuario_id   INT UNSIGNED NOT NULL,
  vehiculo_id  INT UNSIGNED NOT NULL,
  sucursal_id  INT UNSIGNED,
  fecha_inicio DATE NOT NULL,
  fecha_fin    DATE NOT NULL,
  tarifa_dia   DECIMAL(10,2) NOT NULL,   -- tarifa congelada al reservar
  total        DECIMAL(10,2),
  tipo         ENUM('alquiler','venta') DEFAULT 'alquiler',
  estado       ENUM('pendiente','confirmada','en_uso','completada','cancelada') NOT NULL DEFAULT 'pendiente',
  creada_en    DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (usuario_id)  REFERENCES usuarios(id),
  FOREIGN KEY (vehiculo_id) REFERENCES vehiculos(id)
);

CREATE TABLE pagos (
  id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  reserva_id  INT UNSIGNED NOT NULL,
  monto       DECIMAL(10,2) NOT NULL,
  metodo      ENUM('tarjeta','transferencia','oxxo','efectivo'),
  estado      ENUM('pendiente','pagado','rechazado','reembolsado') DEFAULT 'pendiente',
  referencia  VARCHAR(120),
  creado_en   DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (reserva_id) REFERENCES reservas(id) ON DELETE CASCADE
);

-- Módulos ESP32 (monitoreo IoT)
CREATE TABLE modulos_esp32 (
  id               INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  codigo           VARCHAR(60) NOT NULL UNIQUE,   -- "ESP32-AUTONOVA-001"
  nombre           VARCHAR(60) NOT NULL,          -- "Módulo ESP32-001"
  vehiculo_id      INT UNSIGNED UNIQUE,           -- auto donde está instalado
  usuario_id       INT UNSIGNED,                  -- "Nombre del cliente" del panel
  estado           ENUM('esperando','conectado','apagado') NOT NULL DEFAULT 'esperando',
  endpoint_api     VARCHAR(255) DEFAULT 'http://192.168.1.105:5000/api',
  ultimo_heartbeat DATETIME,                      -- base del cronómetro
  ip_local         VARCHAR(45),
  firmware         VARCHAR(30) DEFAULT '1.0.0',
  creado_en        DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (vehiculo_id) REFERENCES vehiculos(id) ON DELETE SET NULL,
  FOREIGN KEY (usuario_id)  REFERENCES usuarios(id)  ON DELETE SET NULL
);

CREATE TABLE telemetria_esp32 (
  id        INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  modulo_id INT UNSIGNED NOT NULL,
  lat       DECIMAL(10,7),
  lng       DECIMAL(10,7),
  velocidad SMALLINT,
  bateria   TINYINT,
  motor     ENUM('on','off'),
  rssi      SMALLINT,
  leido_en  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_modulo_tiempo (modulo_id, leido_en),
  FOREIGN KEY (modulo_id) REFERENCES modulos_esp32(id) ON DELETE CASCADE
);

-- Ventas (opcional v1)
CREATE TABLE ventas (
  id           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  reserva_id   INT UNSIGNED UNIQUE,
  vehiculo_id  INT UNSIGNED NOT NULL,
  usuario_id   INT UNSIGNED NOT NULL,
  precio_final DECIMAL(12,2) NOT NULL,
  estado       ENUM('cotizada','pagada','entregada'),
  fecha_en     DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (usuario_id)  REFERENCES usuarios(id),
  FOREIGN KEY (vehiculo_id) REFERENCES vehiculos(id)
);
```
### 2.1 Tabla **Vehículos** (columnas clave)
`id`, `marca`, `modelo`, `anio`, `placa` (única), `categoria`, `motor`, `transmision`, `combustible`, `kilometraje`, `tarifa_dia`, `tarifa_mes`, `precio_venta`, `descripcion`, `imagen_url`, `estado`, `sucursal_id`, `disponible_desde`, `veces_alquilado`.

### 2.2 Tabla **Usuarios**
`id`, `nombre`, `email` (único), `telefono`, `password_hash`, `licencia`, `rol` (`cliente|admin|staff`), `avatar_url`, `activo`, `creado_en`.

### 2.3 Tabla **Sucursales**
`id`, `nombre`, `ciudad`, `direccion`, `telefono`, `email`, `lat`, `lng`.

### 2.4 Tabla **Reservas / Alquileres**
`id`, `usuario_id`, `vehiculo_id`, `sucursal_id`, `fecha_inicio`, `fecha_fin`, `tarifa_dia`, `total`, `tipo` (`alquiler|venta`), `estado`, `creado_en`.

### 2.5 Tabla **Módulos ESP32**
`id`, `codigo` (único), `nombre`, `vehiculo_id`, `usuario_id`, `estado` (`esperando|conectado|apagado`), `endpoint_api`, `ultimo_heartbeat`, `ip_local`, `firmware`.

### 2.6 Tabla **Telemetría** (cronómetro / estado en vivo)
`id`, `modulo_id`, `lat`, `lng`, `velocidad`, `bateria`, `motor`, `rssi`, `leido_en`.

---

## 3. Relaciones (ER resumido)

```
usuarios 1───* reservas *───1 vehiculos
usuarios 1───* modulos_esp32 1───1 vehiculos
modulos_esp32 1───* telemetria_esp32
reservas 1───* pagos
ventas 1───1 reserva (opcional) / *───1 vehiculos
```

## 4. KPIs / Métricas del panel (derivadas vía SQL)

1. **Flota total** = `COUNT(vehiculos)`.
2. **Alquilados** = `COUNT(*) WHERE estado='alquilado'`.
3. **Disponibles** = `COUNT(*) WHERE estado='disponible'`.
4. **Ingresos/reservas de hoy** = `SUM(total) WHERE fecha_inicio = CURDATE()`.
5. **Módulos online** = `COUNT(modulos_esp32 WHERE estado='conectado' AND TIMESTAMPDIFF(SECOND, ultimo_heartbeat, NOW()) < 60)`.

---

> Nota: el esquema cubre alquiler, venta y monitoreo ESP32. Es implantable en MySQL (script de arriba) o como modelos SQLAlchemy/PeeWee en Flask.