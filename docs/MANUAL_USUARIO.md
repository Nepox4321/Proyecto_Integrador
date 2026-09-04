# Manual de usuario de AutoNova

## 1. Descripción

AutoNova permite consultar la flota de vehículos, reservar unidades, revisar el historial de alquileres y, para el personal autorizado, administrar vehículos, usuarios, reservas y módulos ESP32.

## 2. Acceso

1. Abra `http://127.0.0.1:5000` en el navegador.
2. Seleccione **Registrarse** para crear una cuenta de cliente.
3. Complete nombre, apellidos, correo, teléfono, licencia y contraseña.
4. Inicie sesión con el correo y la contraseña registrados.
5. Para cerrar sesión, use la opción **Salir** del menú.

La cuenta administrativa de demostración es:

- Correo: `admin@autonova.mx`
- Contraseña: `admin123`

Cambie estas credenciales antes de usar la aplicación en un entorno real.

## 3. Consultar la flota

1. Entre en **Flota**.
2. Revise la marca, modelo, categoría, tarifa, estado y fotografía de cada vehículo.
3. Seleccione **Ver detalle** para consultar la información completa.
4. Use **Reservar** en una unidad disponible.

Los vehículos que no están disponibles no deben seleccionarse para una nueva reserva.

## 4. Crear una reserva

1. Seleccione las fechas de inicio y fin.
2. Compruebe que la fecha final sea posterior a la fecha inicial.
3. Revise la tarifa diaria y el total calculado.
4. Inicie sesión o regístrese si todavía no tiene una cuenta.
5. Confirme la reserva y el método de pago.
6. Guarde la pantalla de confirmación y el código de reserva.

El total se calcula multiplicando los días del periodo por la tarifa diaria. El sistema considera al menos un día cuando las fechas corresponden al mismo día.

## 5. Perfil e historial

Desde **Mi perfil** puede:

- Consultar sus datos personales.
- Ver reservas activas y anteriores.
- Consultar el vehículo asociado y el periodo contratado.
- Cancelar una reserva pendiente o confirmada.
- Exportar el historial en formato CSV.

Una reserva en uso o completada no puede cancelarse desde el perfil.

## 6. Panel administrativo

El panel está disponible para cuentas con rol `admin`.

### Dashboard

Muestra indicadores de la flota, usuarios, reservas y estado de los módulos ESP32.

### Vehículos

Permite crear, editar y eliminar unidades. Capture placa única, categoría, estado, tarifas, sucursal y datos descriptivos.

### Reservas

Permite consultar reservas, cambiar su estado y revisar la información del cliente y del vehículo.

### Clientes

Permite consultar, crear, editar y desactivar cuentas de usuario según los permisos de la aplicación.

### ESP32

Permite registrar módulos, asignarlos a un vehículo, consultar su conexión y enviar comandos como `ping`, `reiniciar`, `encender`, `apagar` y `abrir_cajuela`.

El estado del semáforo puede funcionar en modo automático o manual. En modo automático se calcula con base en las reservas activas; en modo manual el administrador selecciona el foco.

### Reportes

Consolida métricas y muestra transacciones recientes. Las reservas y ventas se presentan con el mismo formato gracias al polimorfismo del modelo de dominio.

## 7. Recomendaciones

- No comparta contraseñas ni use la clave demo en producción.
- Verifique las fechas y el importe antes de confirmar.
- No desconecte un ESP32 durante una operación activa.
- Si el panel muestra datos de ejemplo, revise la conexión con MySQL.
- Ante un error, anote la ruta, la acción realizada y la hora para facilitar el diagnóstico.
