#include "esp_camera.h"                // # ESP32-CAM Kameratreiber
#include <WiFi.h>                      // # WLAN Verbindung
#include <HTTPClient.h>                // # HTTP Requests (API Calls)
#include <ArduinoJson.h>               // # JSON Parsing (Plant.id Antwort)
#include "mbedtls/base64.h"            // # Base64 Encoding (Bild -> Text)

// ===================== WLAN & API =====================

const char* ssid = "DEIN_WIFI_NAME";            // # WLAN Name
const char* password = "DEIN_PASSWORT";         // # WLAN Passwort

const char* plantApiKey = "DEIN_PLANTID_API_KEY"; // # Plant.id API Key
const char* plantApiUrl = "https://api.plant.id/v2/identify"; // # Plant.id Endpoint

// ===================== PINS (AI Thinker ESP32-CAM) =====================

const int ledGreen = 33;                // # Grün LED an GPIO33 (frei nutzbar)
const int ledRed   = 2;                 // # Rot LED an GPIO2 (oft onboard LED, geht aber auch extern)
const int pumpPin  = 4;                 // # Pumpensteuerung an GPIO4 (über 1k -> Transistorbasis)

const int soilD0Pin = 14;               // # Bodenfeuchte DIGITAL D0 an GPIO14 (trocken/nass)

// ===================== Hilfsfunktionen: LED =====================

void setLedGreen() {                    // # Funktion: Grün an, Rot aus
  digitalWrite(ledGreen, HIGH);         // # Grün LED EIN
  digitalWrite(ledRed, LOW);            // # Rot LED AUS
}

void setLedRed() {                      // # Funktion: Rot an, Grün aus
  digitalWrite(ledGreen, LOW);          // # Grün LED AUS
  digitalWrite(ledRed, HIGH);           // # Rot LED EIN
}

void setLedOff() {                      // # Funktion: beide LEDs AUS
  digitalWrite(ledGreen, LOW);          // # Grün LED AUS
  digitalWrite(ledRed, LOW);            // # Rot LED AUS
}

// ===================== Hilfsfunktionen: Pumpe =====================

void pumpOn() {                         // # Funktion: Pumpe einschalten
  digitalWrite(pumpPin, HIGH);          // # Pumpenpin HIGH -> Transistor schaltet -> Pumpe läuft
}

void pumpOff() {                        // # Funktion: Pumpe ausschalten
  digitalWrite(pumpPin, LOW);           // # Pumpenpin LOW -> Transistor aus -> Pumpe stoppt
}

// ===================== Base64 Encoding =====================

String toBase64(const uint8_t* data, size_t len) {               // # Bytes -> Base64 String
  size_t outLen = 0;                                             // # Länge für Base64 Output
  mbedtls_base64_encode(NULL, 0, &outLen, data, len);             // # benötigte Länge berechnen
  unsigned char* out = (unsigned char*)malloc(outLen + 1);       // # Speicher reservieren
  if (!out) return "";                                           // # wenn Speicher fehlt -> leer zurück
  mbedtls_base64_encode(out, outLen, &outLen, data, len);         // # Base64 encoden
  out[outLen] = 0;                                               // # String terminieren
  String result = String((char*)out);                             // # in Arduino String umwandeln
  free(out);                                                      // # Speicher freigeben
  return result;                                                  // # Ergebnis zurückgeben
}

// ===================== Kamera Setup (AI Thinker) =====================

void setupCamera() {                                             // # Kamera initialisieren
  camera_config_t config;                                        // # Kamera-Konfig anlegen

  config.ledc_channel = LEDC_CHANNEL_0;                          // # PWM-Kanal
  config.ledc_timer   = LEDC_TIMER_0;                            // # PWM-Timer

  config.pin_d0       = 5;                                       // # Kamera Daten D0
  config.pin_d1       = 18;                                      // # Kamera Daten D1
  config.pin_d2       = 19;                                      // # Kamera Daten D2
  config.pin_d3       = 21;                                      // # Kamera Daten D3
  config.pin_d4       = 36;                                      // # Kamera Daten D4
  config.pin_d5       = 39;                                      // # Kamera Daten D5
  config.pin_d6       = 34;                                      // # Kamera Daten D6 (WICHTIG: deshalb NICHT als Soil Analog verwenden)
  config.pin_d7       = 35;                                      // # Kamera Daten D7

  config.pin_xclk     = 0;                                       // # XCLK Pin
  config.pin_pclk     = 22;                                      // # PCLK Pin
  config.pin_vsync    = 25;                                      // # VSYNC Pin
  config.pin_href     = 23;                                      // # HREF Pin
  config.pin_sscb_sda = 26;                                      // # SCCB SDA
  config.pin_sscb_scl = 27;                                      // # SCCB SCL
  config.pin_pwdn     = 32;                                      // # PowerDown
  config.pin_reset    = -1;                                      // # Reset nicht genutzt

  config.xclk_freq_hz = 20000000;                                // # 20 MHz Kamera Clock
  config.pixel_format = PIXFORMAT_JPEG;                          // # JPEG Format (für Upload ideal)

  config.frame_size   = FRAMESIZE_QVGA;                          // # QVGA = schnell, ausreichend
  config.jpeg_quality = 12;                                      // # Qualität 0..63 (kleiner = bessere Qualität)
  config.fb_count     = 1;                                       // # 1 Framebuffer (RAM sparen)

  esp_err_t err = esp_camera_init(&config);                      // # Kamera starten
  if (err != ESP_OK) {                                           // # wenn Fehler
    Serial.printf("Kamera init fehlgeschlagen: 0x%x\n", err);     // # Fehler ausgeben
    while (true) delay(1000);                                    // # stoppen
  }
}

// ===================== Plant.id Request =====================

String identifyPlant() {                                         // # Foto machen und Pflanze erkennen
  camera_fb_t* fb = esp_camera_fb_get();                         // # Foto aufnehmen
  if (!fb) {                                                     // # wenn Foto fehlgeschlagen
    Serial.println("Kamerafehler");                              // # Fehler melden
    return "unknown";                                            // # unknown zurückgeben
  }

  String imageBase64 = toBase64(fb->buf, fb->len);               // # JPEG -> Base64
  esp_camera_fb_return(fb);                                      // # Framebuffer freigeben

  if (imageBase64.length() < 10) {                               // # Sicherheit: Base64 sollte nicht leer sein
    Serial.println("Base64 Fehler");                             // # Fehler melden
    return "unknown";                                            // # unknown zurückgeben
  }

  HTTPClient http;                                               // # HTTP Client erstellen
  http.begin(plantApiUrl);                                       // # Ziel-URL setzen
  http.addHeader("Content-Type", "application/json");            // # JSON Body
  http.addHeader("Api-Key", plantApiKey);                        // # API Key Header

  String body = "{\"images\":[\"" + imageBase64 + "\"],\"modifiers\":[\"similar_images\"],\"plant_language\":\"en\"}"; // # JSON Request
  int httpCode = http.POST(body);                                // # POST absenden
  String response = http.getString();                            // # Antwort lesen
  http.end();                                                    // # HTTP schließen

  if (httpCode <= 0) {                                           // # wenn Request nicht geklappt
    Serial.println("HTTP Fehler");                               // # Fehler ausgeben
    return "unknown";                                            // # unknown zurückgeben
  }

  StaticJsonDocument<4096> doc;                                  // # JSON Speicher
  DeserializationError err = deserializeJson(doc, response);      // # JSON parsen
  if (err) {                                                     // # wenn Parse fehlschlägt
    Serial.println("JSON Parse Fehler");                         // # Fehler
    return "unknown";                                            // # unknown
  }

  const char* plantName = doc["suggestions"][0]["plant_name"];   // # erster Vorschlag von Plant.id
  if (!plantName) return "unknown";                              // # falls leer -> unknown

  return String(plantName);                                      // # Pflanzenname zurück
}

// ===================== Bodenfeuchte (DIGITAL) =====================

bool soilIsDry() {                                               // # check: ist Boden trocken?
  int v = digitalRead(soilD0Pin);                                // # D0 lesen
  // Viele Module: HIGH = trocken, LOW = nass. Wenn bei dir falsch: return (v == LOW);
  return (v == HIGH);                                            // # TRUE wenn trocken
}

// ===================== Bewässern =====================

void waterPlant(int ms) {                                        // # Pumpe für ms Millisekunden laufen lassen
  Serial.println("💧 Bewässerung startet");                       // # Log
  pumpOn();                                                      // # Pumpe EIN
  delay(ms);                                                     // # warten
  pumpOff();                                                     // # Pumpe AUS
  Serial.println("💧 Bewässerung beendet");                       // # Log
}

// ===================== Setup / Loop =====================

void setup() {                                                   // # einmaliger Start
  Serial.begin(115200);                                          // # Serial starten

  pinMode(ledGreen, OUTPUT);                                     // # Grün LED output
  pinMode(ledRed, OUTPUT);                                       // # Rot LED output
  pinMode(pumpPin, OUTPUT);                                      // # Pumpe output
  pinMode(soilD0Pin, INPUT);                                     // # Boden-D0 input

  setLedOff();                                                   // # LEDs aus
  pumpOff();                                                     // # Pumpe aus

  setupCamera();                                                 // # Kamera initialisieren

  WiFi.begin(ssid, password);                                    // # WLAN starten
  Serial.print("Verbinde WLAN");                                 // # Log
  while (WiFi.status() != WL_CONNECTED) {                        // # warten bis verbunden
    Serial.print(".");                                           // # Punkte anzeigen
    delay(400);                                                  // # kurz warten
  }
  Serial.println("\nWLAN verbunden!");                            // # verbunden

  setLedGreen();                                                 // # Grün = bereit
}

void loop() {                                                    // # läuft ständig
  Serial.println("---- HappyPlant 2.0 Zyklus ----");              // # neuer Zyklus

  String plant = identifyPlant();                                // # Pflanze erkennen
  Serial.print("Erkannte Pflanze: ");                             // # Log
  Serial.println(plant);                                         // # Pflanzenname ausgeben

  bool dry = soilIsDry();                                        // # Bodenstatus prüfen
  Serial.print("Boden trocken? ");                                // # Log
  Serial.println(dry ? "JA" : "NEIN");                            // # Ausgabe

  // Beispiel-Logik: wenn trocken -> rot + bewässern, sonst grün
  if (dry) {                                                     // # wenn trocken
    setLedRed();                                                 // # Rot LED an
    waterPlant(5000);                                            // # 5 Sekunden gießen
  } else {                                                       // # wenn nicht trocken
    setLedGreen();                                               // # Grün LED an
  }

  delay(15000);                                                  // # 15s warten (API nicht spammen)
}
