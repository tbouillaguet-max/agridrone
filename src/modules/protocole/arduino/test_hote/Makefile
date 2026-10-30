# Compile et lance les tests de ProtocoleDrone.h et FichiersVol.h sur PC (Linux, macOS, WSL).
CXX ?= g++
CXXFLAGS ?= -std=c++11 -Wall -Wextra -Werror -O1

test: test_protocole test_fichiers_vol
	./test_protocole
	./test_fichiers_vol

test_protocole: test_protocole.cpp vecteurs_test.h ../ProtocoleDrone/ProtocoleDrone.h
	$(CXX) $(CXXFLAGS) -o $@ test_protocole.cpp

test_fichiers_vol: test_fichiers_vol.cpp ../ProtocoleDrone/FichiersVol.h ../ProtocoleDrone/ProtocoleDrone.h
	$(CXX) $(CXXFLAGS) -o $@ test_fichiers_vol.cpp

# Banc d'essai « AU2 » (croquis banc_au2_mission) exécuté sur PC, Serial = serveur TCP
banc: banc_hote

banc_hote: banc_hote.cpp arduino_hote.h ../exemples/banc_au2_mission/banc_au2_mission.ino ../ProtocoleDrone/ProtocoleDrone.h
	$(CXX) -std=c++11 -Wall -Wextra -O1 -I../ProtocoleDrone -include arduino_hote.h -x c++ -o $@ banc_hote.cpp -lpthread

clean:
	rm -f test_protocole test_fichiers_vol banc_hote

.PHONY: test banc clean
