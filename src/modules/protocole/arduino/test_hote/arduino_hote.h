// =============================================================================
// arduino_hote.h — émulation minimale de l'API Arduino sur PC (Linux, macOS, WSL)
//
// Permet de compiler un croquis .ino d'AU2 avec g++ et de l'essayer sans
// carte : Serial = socket TCP (le planificateur de test s'y connecte à la
// place du câble USB).
// Seules les fonctions utilisées par les croquis du TP sont émulées.
// =============================================================================
#pragma once
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>

#define F(texte) (texte)
#define HEX 16
#define DEC 10
#define LOW 0
#define HIGH 1
#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2
#define LED_BUILTIN 13

unsigned long millis();
void pinMode(uint8_t broche, uint8_t mode);
int digitalRead(uint8_t broche);
void digitalWrite(uint8_t broche, uint8_t valeur);

/** Flux série émulé : les fonctions print/println d'Arduino au-dessus de deux primitives. */
class FluxHote {
 public:
  virtual ~FluxHote() {}
  virtual void begin(unsigned long) {}
  virtual int available() = 0;
  virtual int read() = 0;
  virtual size_t write(const uint8_t *octets, size_t n) = 0;
  size_t write(uint8_t o) { return write(&o, 1); }

  size_t print(const char *s) { return write(reinterpret_cast<const uint8_t *>(s), std::strlen(s)); }
  size_t print(char c) { return write(static_cast<uint8_t>(c)); }
  size_t print(const std::string &s) { return print(s.c_str()); }
  size_t print(long v, int base = DEC) {
    char t[24];
    std::snprintf(t, sizeof t, base == HEX ? "%lX" : "%ld", v);
    return print(t);
  }
  size_t print(unsigned long v, int base = DEC) {
    char t[24];
    std::snprintf(t, sizeof t, base == HEX ? "%lX" : "%lu", v);
    return print(t);
  }
  size_t print(int v, int base = DEC) { return print(static_cast<long>(v), base); }
  size_t print(unsigned int v, int base = DEC) { return print(static_cast<unsigned long>(v), base); }
  size_t print(unsigned char v, int base = DEC) { return print(static_cast<unsigned long>(v), base); }
  size_t print(unsigned short v, int base = DEC) { return print(static_cast<unsigned long>(v), base); }
  size_t print(short v, int base = DEC) { return print(static_cast<long>(v), base); }
  template <typename T>
  size_t println(T v) { size_t n = print(v); return n + print("\r\n"); }
  template <typename T>
  size_t println(T v, int base) { size_t n = print(v, base); return n + print("\r\n"); }
  size_t println() { return print("\r\n"); }
};

extern FluxHote &Serial;

// Le croquis
void setup();
void loop();
