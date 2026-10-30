// =============================================================================
// Exécute le croquis banc_au2_mission sur PC : Serial (le câble USB) est un
// serveur TCP. Sert au test croisé planificateur (JavaScript) <-> AU2 (C++) :
//
//   make -C protocole/arduino/test_hote banc
//   ./protocole/arduino/test_hote/banc_hote 5761
//   puis, dans planificateur/ :  BANC_AU2=127.0.0.1:5761 npm test
//
// BANC_ARME=1 dans l'environnement : la broche « armé » est reliée à GND
// (le banc refuse alors toute nouvelle mission).
// =============================================================================
#include "arduino_hote.h"

#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <sys/socket.h>
#include <unistd.h>

#include <chrono>
#include <cstdlib>
#include <thread>

static auto debut = std::chrono::steady_clock::now();
unsigned long millis() {
  return (unsigned long)std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - debut).count();
}
void pinMode(uint8_t, uint8_t) {}
int digitalRead(uint8_t) {  // broche « armé » : reliée à GND si BANC_ARME=1
  const char *v = std::getenv("BANC_ARME");
  return (v && v[0] == '1') ? LOW : HIGH;
}
void digitalWrite(uint8_t, uint8_t) {}

/** Serial : serveur TCP, un client à la fois (le planificateur ou un test). */
class Tcp : public FluxHote {
 public:
  void ecouter(int port) {
    serveur_ = socket(AF_INET, SOCK_STREAM, 0);
    int oui = 1;
    setsockopt(serveur_, SOL_SOCKET, SO_REUSEADDR, &oui, sizeof oui);
    sockaddr_in a{};
    a.sin_family = AF_INET;
    a.sin_port = htons((uint16_t)port);
    a.sin_addr.s_addr = htonl(INADDR_ANY);
    if (bind(serveur_, (sockaddr *)&a, sizeof a) != 0 || listen(serveur_, 1) != 0) {
      std::perror("port TCP");
      std::exit(1);
    }
    fcntl(serveur_, F_SETFL, O_NONBLOCK);
    std::printf("[hôte] Serial = TCP port %d\n", port);
  }
  int available() override {
    accepter();
    if (client_ < 0) return 0;
    if (n_ > i_) return n_ - i_;
    ssize_t r = recv(client_, tampon_, sizeof tampon_, MSG_DONTWAIT);
    if (r == 0) { std::printf("[hôte] client déconnecté\n"); close(client_); client_ = -1; return 0; }
    if (r < 0) return 0;
    i_ = 0;
    n_ = (int)r;
    return n_;
  }
  int read() override { return available() ? tampon_[i_++] : -1; }
  size_t write(const uint8_t *o, size_t n) override {
    if (client_ >= 0) send(client_, o, n, MSG_NOSIGNAL);
    return n;
  }
 private:
  void accepter() {
    if (client_ >= 0) return;
    int c = accept(serveur_, nullptr, nullptr);
    if (c < 0) return;
    int oui = 1;
    setsockopt(c, IPPROTO_TCP, TCP_NODELAY, &oui, sizeof oui);
    client_ = c;
    i_ = n_ = 0;
    std::printf("[hôte] client connecté\n");
  }
  int serveur_ = -1, client_ = -1;
  uint8_t tampon_[1024];
  int i_ = 0, n_ = 0;
};

static Tcp tcp;
FluxHote &Serial = tcp;

int main(int argc, char **argv) {
  tcp.ecouter(argc > 1 ? std::atoi(argv[1]) : 5761);
  setup();
  for (;;) {
    loop();
    std::this_thread::sleep_for(std::chrono::microseconds(200));
  }
}

// Le croquis lui-même, compilé tel quel (seul ProtocoleDrone.h et arduino_hote.h sont inclus en plus).
#include "../exemples/banc_au2_mission/banc_au2_mission.ino"
