/* ============================================================
   AutoNova · esp32_autonova.ino — Firmware del módulo ESP32
   ------------------------------------------------------------
   VERSIÓN CORREGIDA (basada en tu código que ya funciona):
     ✔ Módulo numérico TM1637 con la librería TM1637Display
        -> CLK = GPIO19, DIO = GPIO18 (ya NO se multiplexa a mano).
     ✔ Cambio de estados arreglado: se guarda el último estado
        y solo se reacciona cuando cambia (el buzzer y las alertas
        NO se repiten en cada consulta).
     ✔ Consulta simple del estado cada 5 s con HTTP GET.
     ✔ LED ROJO nuevo (GPIO33) para el foco "rojo" del servidor
        (alquiler vencido) y para fallos de conexión WiFi/servidor,
        con doble pitido del buzzer y display 404 (estilo de tu
        código de referencia del LED rojo).

   ADAPTADO al backend real de AutoNova (Flask + MySQL):
     GET http://IP:5000/api/esp/ESP32-AUTONOVA-001/estado
       -> {"luz":"verde|azul|amarillo|rojo",
           "segundos_restantes":<seg|null>, "detalle":"..."}
     (No uses /api/vehiculo/1/estado: ese endpoint no existe en
      el servidor del proyecto; el real es /api/esp/<codigo>/estado)

   SEMÁFORO (significado de cada luz del servidor):
     verde    -> libre / disponible          (LED verde)
     azul     -> reserva por confirmar       (LED azul)
     amarillo -> alquiler EN CURSO           (LED amarillo + cuenta regresiva)
     rojo     -> alquiler VENCIDO            (LED ROJO + doble pitido + 9999)
     (fallo)  -> sin servidor / sin WiFi     (LED ROJO + doble pitido + 404)
   ============================================================ */

#include <WiFi.h>
#include <HTTPClient.h>
#include <TM1637Display.h>

/* ------------------ CONFIGURAR ANTES DE SUBIR ------------------ */
const char* WIFI_SSID     = "NETLIFE-ROJAS";
const char* WIFI_PASSWORD = "0915000319";

// CRÍTICO: pon la IP IPv4 de tu computadora. NUNCA "localhost" aquí.
const char* SERVER_HOST = "http://192.168.100.93:5000";

// Código del módulo registrado en el panel /admin/esp32.
// Debe coincidir EXACTO con el de la base de datos.
const char* MODULO_REF  = "ESP32-AUTONOVA-001";

const unsigned long POLL_MS         = 5000;   // consultar estado cada 5 s
const unsigned long HEARTBEAT_MS    = 15000;  // mantener "conectado" en el panel
const unsigned long WIFI_TIMEOUT_MS = 20000;  // timeout de conexión WiFi
const unsigned long HTTP_TIMEOUT_MS = 1500;   // timeout HTTP corto
/* --------------------------------------------------------------- */

/* ------------ PINES DEL HARDWARE (ajusta a tu cableado) ---------- */
#define CLK_PIN 19
#define DIO_PIN 18
TM1637Display display(CLK_PIN, DIO_PIN);

#define PIN_LED_VERDE    12
#define PIN_LED_AZUL     26
#define PIN_LED_AMARILLO 27
#define PIN_LED_ROJO     33
#define PIN_BUZZER       14

/* Si tus LED/buzzer encienden con HIGH deja esto en true.
   Si tu kit enciende con LOW cámbialo a false. */
const bool ACTUADORES_ACTIVO_ALTO = true;
const int  LED_ON  = ACTUADORES_ACTIVO_ALTO ? HIGH : LOW;
const int  LED_OFF = ACTUADORES_ACTIVO_ALTO ? LOW  : HIGH;
const int  BUZZ_ON  = ACTUADORES_ACTIVO_ALTO ? HIGH : LOW;
const int  BUZZ_OFF = ACTUADORES_ACTIVO_ALTO ? LOW  : HIGH;

/* Último estado recibido: EVITA repetir alertas en cada consulta */
String estadoAnterior = "";
String luzAnterior = "";
unsigned long ultimoHeartbeatMs = 0;
long cuentaRegresiva = -1;
unsigned long ultimoTickCuenta = 0;

/* ============================================================
   AUXILIARES DEL DISPLAY TM1637
   ============================================================ */
void mostrarNumero(long valor) {
  if (valor > 9999) valor = 9999;
  if (valor < 0)    valor = 0;
  display.showNumberDec((int)valor, false);
}

void mostrarCuentaRegresiva(long segundos) {
  if (segundos < 0) segundos = 0;
  long minutos = segundos / 60;
  long segundosEnMinuto = segundos % 60;
  if (minutos > 99) minutos = 99;
  display.showNumberDecEx((int)(minutos * 100 + segundosEnMinuto),
                          0b01000000, true);
}

void mostrarGuiones() {
  uint8_t guion[4] = {0x40, 0x40, 0x40, 0x40};  // segmento G = '-'
  display.setSegments(guion);
}

/* ============================================================
   PARSER SIMPLE DEL JSON (sin librerías extra)
   ============================================================ */
String extraerString(const String& s, const char* clave) {
  String tag = String("\"") + clave + String("\":\"");
  int i = s.indexOf(tag);
  if (i < 0) return "";
  i += tag.length();
  int j = s.indexOf('"', i);
  if (j < 0) return "";
  return s.substring(i, j);
}

long extraerLong(const String& s, const char* clave) {
  String tag = String("\"") + clave + String("\":");
  int i = s.indexOf(tag);
  if (i < 0) return -1;
  i += tag.length();
  while (i < (int)s.length() && !isDigit(s.charAt(i))) i++;
  if (i >= (int)s.length()) return -1;
  return s.substring(i).toInt();
}
/* ============================================================
   HARDWARE — LEDs + buzzer
   ============================================================ */
void apagarTodo() {
  digitalWrite(PIN_LED_VERDE,    LED_OFF);
  digitalWrite(PIN_LED_AZUL,     LED_OFF);
  digitalWrite(PIN_LED_AMARILLO, LED_OFF);
  digitalWrite(PIN_LED_ROJO,     LED_OFF);
  digitalWrite(PIN_BUZZER, BUZZ_OFF);
}

/* Alarma grave: doble pitido (estilo del código de referencia del LED rojo).
   Solo se dispara en un CAMBIO de estado, por eso no se repite. */
void alarmaGrave() {
  digitalWrite(PIN_BUZZER, BUZZ_ON);
  delay(150);
  digitalWrite(PIN_BUZZER, BUZZ_OFF);
  delay(150);
  digitalWrite(PIN_BUZZER, BUZZ_ON);
  delay(150);
  digitalWrite(PIN_BUZZER, BUZZ_OFF);
}

void alarmaInicio() {
  digitalWrite(PIN_BUZZER, BUZZ_ON);
  delay(220);
  digitalWrite(PIN_BUZZER, BUZZ_OFF);
}

/* Sin servidor / sin WiFi: LED ROJO + display 404, con alarma UNA sola vez.
   Se restaura automáticamente cuando el servidor vuelve a responder. */
void modoErrorConexion() {
  if (estadoAnterior == "ERROR_CONEXION") return;  // ya está en alerta
  Serial.println("[Estado] Sin servidor -> LED ROJO + 404");
  apagarTodo();
  digitalWrite(PIN_LED_ROJO, LED_ON);
  mostrarNumero(404);
  alarmaGrave();
  estadoAnterior = "ERROR_CONEXION";
}

/* Aplica la luz del semáforo al hardware y al módulo numérico.
   Se llama SOLO cuando el estado cambió (véase consultarEstado). */
void actualizarHardware(const String& luz, long segundosRestantes) {
  apagarTodo();            // seguridad: apagar todo antes de encender
  cuentaRegresiva = -1;    // detener cualquier cuenta de una renta anterior

  if (luz == "verde") {    // libre / disponible
    digitalWrite(PIN_LED_VERDE, LED_ON);
    mostrarNumero(1);      // código: vehículo libre
  }
  else if (luz == "azul") { // reserva por confirmar
    digitalWrite(PIN_LED_AZUL, LED_ON);
    mostrarNumero(2);      // código: reservado
  }
  else if (luz == "amarillo") { // alquiler EN CURSO
    digitalWrite(PIN_LED_AMARILLO, LED_ON);
    if (luzAnterior != "amarillo") alarmaInicio();
    // Muestra MM:SS. El servidor mantiene el valor oficial en MySQL.
    mostrarCuentaRegresiva(segundosRestantes);
    cuentaRegresiva = segundosRestantes;
    ultimoTickCuenta = millis();
  }
  else if (luz == "rojo") { // alquiler VENCIDO (LED ROJO físico, GPIO33)
    digitalWrite(PIN_LED_ROJO, LED_ON);
    mostrarNumero(9999);                   // código de error
    if (luzAnterior != "rojo") alarmaGrave(); // doble pitido, UNA sola vez
  }
  else {
    cuentaRegresiva = -1;
    mostrarGuiones();      // luz desconocida / sin señal
  }
  luzAnterior = luz;
}

void actualizarCuentaRegresiva() {
  if (cuentaRegresiva < 0) return;
  unsigned long ahora = millis();
  if (ahora - ultimoTickCuenta < 1000) return;
  long transcurridos = (ahora - ultimoTickCuenta) / 1000;
  cuentaRegresiva = max(0L, cuentaRegresiva - (long)transcurridos);
  ultimoTickCuenta += transcurridos * 1000;
  mostrarCuentaRegresiva(cuentaRegresiva);
}

/* ============================================================
   HTTP — consulta de estado + heartbeat
   ============================================================ */
void consultarEstado() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String url = String(SERVER_HOST) + "/api/esp/" + String(MODULO_REF) + "/estado";
  http.begin(url);
  http.setTimeout(HTTP_TIMEOUT_MS);

  int codigo = http.GET();
  if (codigo == 200) {
    String cuerpo = http.getString();

    // Normalizar la respuesta para comparar sin errores.
    cuerpo.toLowerCase();     // todo en minúsculas
    cuerpo.replace(" ", "");  // quitar espacios (robustez del JSON)

    // *** CAMBIO DE ESTADO ARREGLADO ***
    // Solo actuamos cuando el contenido es diferente al anterior.
    // Así el buzzer no se repite y el display no "parpadea" los códigos.
    if (cuerpo != estadoAnterior) {
      Serial.println("[Estado] ¡Cambio detectado! -> " + cuerpo);
      String luz      = extraerString(cuerpo, "luz");
      long   segundos = extraerLong(cuerpo, "segundos_restantes");
      if (segundos < 0) segundos = 0;
      actualizarHardware(luz, segundos);
      estadoAnterior = cuerpo;
    }
  } else {
    Serial.println("[Estado] Error HTTP: " + String(codigo));
    // El servidor no respondió -> alerta por LED rojo (display 404).
    // Se quita solo al recuperar la conexión y recibir el estado real.
    modoErrorConexion();
  }
  http.end();
}

/* (Opcional) Mantiene al módulo "conectado" en el panel /admin/esp32.
   Si lo quitas, el panel seguirá mostrando la última hora de conexión. */
void enviarHeartbeat() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String url = String(SERVER_HOST) + "/api/esp/" + String(MODULO_REF) + "/heartbeat";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(HTTP_TIMEOUT_MS);

  int codigo = http.POST("{\"estado\":\"conectado\"}");
  if (codigo <= 0) {
    Serial.println("[Heartbeat] Error HTTP: " + String(codigo));
  }
  http.end();
}
/* ============================================================
   SETUP
   ============================================================ */
void setup() {
  Serial.begin(115200);

  pinMode(PIN_LED_VERDE, OUTPUT);
  pinMode(PIN_LED_AZUL, OUTPUT);
  pinMode(PIN_LED_AMARILLO, OUTPUT);
  pinMode(PIN_LED_ROJO, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);

  display.setBrightness(0x0f);   // brillo máximo (0x00 = mínimo)

  apagarTodo();
  mostrarGuiones();

  Serial.println();
  Serial.println("=== AutoNova · módulo ESP32 (TM1637) ===");

  // --- Conectar WiFi con timeout (no se queda colgado para siempre) ---
  Serial.print("[WiFi] Conectando a " + String(WIFI_SSID) + "...");
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);          // el driver reintenta solo
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long inicio = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - inicio < WIFI_TIMEOUT_MS) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println(" OK. IP local: " + WiFi.localIP().toString());
  } else {
    Serial.println(" FALLO. Se reintentará dentro del loop.");
  }

  ultimoHeartbeatMs = millis();
}

/* ============================================================
   LOOP — simple y legible, como tu versión original
   ============================================================ */
void loop() {
  // 1. WiFi: si se cayó, reiniciar la conexión y reintentar en el
  //    siguiente ciclo (con esto también se recupera si falló al inicio)
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] Sin conexión, reconectando...");
    modoErrorConexion();   // alerta visual mientras no haya servidor
    WiFi.disconnect();
    delay(100);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    delay(1000);
    return;
  }

  unsigned long ahora = millis();

  // 2. Heartbeat opcional: mantiene "conectado" al módulo en el panel
  if (ahora - ultimoHeartbeatMs >= HEARTBEAT_MS) {
    ultimoHeartbeatMs = ahora;
    enviarHeartbeat();
  }

  // 3. Consultar el estado del semáforo y actualizar LEDs + display
  consultarEstado();
  actualizarCuentaRegresiva();

  // 4. Esperar antes de volver a consultar (cada 5 s)
  delay(POLL_MS);
}

/* ============================================================
   FIN — AutoNova · esp32_autonova.ino
   ============================================================ */