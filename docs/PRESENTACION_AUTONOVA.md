# Guion de presentación de AutoNova

## Objetivo

Este archivo sirve como guía para una exposición de dos personas. El contenido se limita a las funciones implementadas en el proyecto y a los temas de POO solicitados.

Duración sugerida: 7 a 10 minutos.

## Antes de comenzar

- Tener la aplicación ejecutándose en `http://127.0.0.1:5000`.
- Abrir la página de inicio.
- Tener preparado el acceso de demostración del administrador.
- Mostrar el catálogo, el inicio de sesión, el perfil y el panel administrativo.
- Si se cuenta con el ESP32 conectado, mostrar el módulo y su estado. Si no, explicar la pantalla usando los datos de ejemplo.

## Participante 1: presentación general y recorrido de usuario

### 1. Saludo y objetivo

> Buenos días. Nuestro proyecto se llama AutoNova. Es una plataforma web para administrar una flota de vehículos y gestionar reservas de alquiler. También cuenta con un panel administrativo y una integración con módulos ESP32 para consultar telemetría y controlar un semáforo asociado a los vehículos.

### 2. Página de inicio y catálogo

> En la página de inicio mostramos los vehículos destacados. Desde la opción Flota se puede consultar el catálogo completo, revisar la información de cada vehículo y entrar al detalle de una unidad.

Mostrar:

1. Página de inicio.
2. Opción **Flota**.
3. Detalle de un vehículo.

> El catálogo muestra datos como marca, modelo, categoría, placa, tarifa y estado. La persona usuaria puede elegir un vehículo disponible para comenzar una reserva.

### 3. Registro, inicio de sesión y reserva

> Para reservar, la persona debe iniciar sesión o crear una cuenta. El sistema valida los datos del formulario y guarda la contraseña como un hash, no como texto normal.

Mostrar:

1. Formulario de registro o inicio de sesión.
2. Selección de fechas en el checkout.
3. Total calculado.
4. Pantalla de confirmación.

> En el checkout se validan las fechas, se calcula el número de días y se obtiene el total multiplicando los días por la tarifa diaria. Cuando se confirma, se crea una reserva relacionada con el usuario y el vehículo.

### 4. Perfil del usuario

> En Mi Perfil se puede consultar la renta activa, el historial de reservas, el estado de cada reserva y el total gastado. También existe una opción para exportar el historial en CSV y otra para cancelar reservas que todavía estén pendientes o confirmadas.

Mostrar brevemente el perfil o explicar su flujo si la base de datos no está disponible.

### Cierre del participante 1

> Con esto mostramos el flujo principal de una persona usuaria: consultar la flota, iniciar sesión, seleccionar fechas, confirmar una reserva y consultar su historial.

## Participante 2: administración, POO y ESP32

### 5. Panel administrativo

> El panel administrativo está protegido por un decorador que verifica que exista una sesión y que el rol sea `admin`. Desde aquí se pueden consultar usuarios, vehículos, reservas y módulos ESP32.

Acceso de demostración:

- Correo: `admin@autonova.mx`
- Contraseña: `admin123`

Mostrar:

1. Dashboard con indicadores.
2. Gestión de vehículos.
3. Gestión de reservas.
4. Gestión de clientes.
5. Gestión de módulos ESP32.
6. Reportes.

> El administrador puede registrar o editar vehículos, cambiar estados, consultar reservas, activar o desactivar cuentas y administrar los módulos ESP32. Los reportes reúnen información de la flota y las transacciones.

### 6. Clases y herencia

> En el código usamos clases para representar las entidades de la aplicación. Por ejemplo, `Usuario`, `Vehiculo`, `Reserva`, `Venta` y `ModuloESP32` son modelos que representan datos del sistema.

> `Transaccion` es una clase abstracta que concentra los datos y comportamientos comunes de una transacción. De ella heredan `Reserva` y `Venta`. Así evitamos repetir los atributos `id`, `usuario_id` y `vehiculo_id`.

> También existe `EntidadModuloESP32`, una clase abstracta de la que heredan `TelemetriaESP32`, `ComandoESP32` y `SemaforoFoco`. Estas clases comparten la relación con el módulo ESP32.

### 7. Polimorfismo y reutilización

> `Reserva` y `Venta` implementan los mismos métodos: `tipo_transaccion()`, `importe()` y `resumen()`. Cada clase responde de acuerdo con su propia información. Una reserva calcula el importe usando `total`, mientras que una venta utiliza `precio_final`.

> En los reportes se pueden reunir reservas y ventas en una misma lista y llamar a `resumen()` sin preguntar qué clase concreta es cada objeto. Ese es el uso del polimorfismo en el proyecto.

### 8. Sobrecarga

> En `Transaccion.codigo_corto()` usamos `@overload` para documentar diferentes formas de llamada. `codigo_corto()` devuelve un código como `AN-0001`, y `codigo_corto(False)` devuelve solamente `0001`. La implementación mantiene el prefijo correspondiente según el tipo de transacción.

### 9. Clases abstractas y enums

> Las clases `Transaccion` y `EntidadModuloESP32` son abstractas. Definen métodos obligatorios con `@abstractmethod`, por lo que sus clases hijas deben implementar ese comportamiento.

> También usamos enums para centralizar valores del dominio, como `TipoTransaccion`, `EstadoVehiculo`, `ComandoESP32Enum` y `ModoSemaforo`. Esto evita escribir valores diferentes para una misma opción.

### 10. Relación entre clases y base de datos

> SQLAlchemy conecta las clases Python con MySQL. Cada clase tiene un `__tablename__` que indica la tabla correspondiente. Cada `db.Column` representa una columna y las claves foráneas conectan tablas como usuarios, vehículos y reservas.

> Cuando una ruta crea una reserva, el objeto se agrega con `db.session.add()` y se guarda con `db.session.commit()`. Después, una consulta ORM recupera los datos de MySQL como objetos Python.

### 11. Integración con ESP32

> El ESP32 se comunica con el servidor mediante la API. Envía un heartbeat y datos de telemetría, consulta el estado del semáforo y recoge comandos pendientes enviados desde el panel.

> El semáforo puede trabajar en modo automático, según el estado de una reserva, o en modo manual, cuando el administrador fija el foco desde el panel. Los estados principales son verde, azul, amarillo y rojo.

Mostrar, si está disponible:

1. Panel de módulos ESP32.
2. Estado de conexión.
3. Semáforo.
4. Telemetría o comando.

### Cierre del participante 2

> AutoNova integra una página web, una base de datos y un módulo físico. La POO nos permite reutilizar clases, aplicar herencia, usar polimorfismo, definir clases abstractas y organizar los estados con enums. Con esto terminamos la presentación.

## Demostración rápida recomendada

1. Abrir la página de inicio.
2. Entrar a **Flota**.
3. Mostrar el detalle de un vehículo.
4. Iniciar sesión como administrador.
5. Mostrar el dashboard.
6. Entrar a **Vehículos** o **Reservas**.
7. Mostrar **ESP32** y **Reportes**.
8. Explicar brevemente `Transaccion`, `Reserva`, `Venta` y `EntidadModuloESP32` en `models.py`.
9. Cerrar con la conexión entre Flask, SQLAlchemy, MySQL y ESP32.

## Respuestas breves para preguntas comunes

**¿Qué problema resuelve el proyecto?**

> Organiza la flota, las reservas, las cuentas de usuario y el monitoreo de los vehículos desde una sola plataforma.

**¿Dónde se observa la herencia?**

> En `Transaccion` con `Reserva` y `Venta`, y en `EntidadModuloESP32` con las entidades de telemetría, comandos y semáforo.

**¿Dónde se observa el polimorfismo?**

> En el método `resumen()`, porque reservas y ventas responden de manera diferente al mismo método.

**¿Cómo se guarda la información?**

> Flask recibe la petición, SQLAlchemy convierte los objetos en operaciones de base de datos y MySQL almacena la información.

**¿Qué hace el ESP32?**

> Envía telemetría, consulta el estado del semáforo y recibe comandos del panel administrativo.
