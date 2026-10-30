/*
  ÉTAPE 1 — Scanner I2C et identification du compas du DJI Phantom 3
  ===================================================================

  But : savoir si le compas répond en I2C, à quelle adresse, et quelle
  puce il contient (la marque "KB1646" ne permet pas de l'identifier :
  "1646" ressemble à un code de date, 2016 semaine 46).

  Source du brochage (Phantom 3 Pro/Advanced, à confirmer sur le
  Standard avec les couleurs de fils) :
  https://github.com/o-gs/dji-firmware-tools/wiki/P3X-ESC-center-board
  Connecteur compas JST GH 5 broches, pas de 1,25 mm :
    1 = SCL   2 = GND   3 = HDRDY (data ready)   4 = 3V6   5 = SDA

  CÂBLAGE (ne rien brancher avant confirmation des couleurs de fils)
  ------------------------------------------------------------------
    Arduino Uno                 Compas Phantom 3
    3.3V  --------------------- 3V6   (le compas est prévu pour 3,6 V,
                                       3,3 V convient ; conso ~1 mA)
    GND   --------------------- GND
    A4 (SDA) ------------------ SDA
    A5 (SCL) ------------------ SCL
    (rien)                      HDRDY (laisser en l'air)

    Résistances de rappel externes, vers le 3,3 V (PAS vers le 5 V) :
    3.3V --[ 4,7 kΩ ]-- A4 (SDA)
    3.3V --[ 4,7 kΩ ]-- A5 (SCL)

  PROTECTION 5 V
  --------------
  Wire.begin() active les résistances de rappel internes de l'ATmega
  (~35 kΩ vers 5 V). On les coupe juste après, par logiciel. Pendant
  quelques microsecondes, SDA/SCL voient le 5 V à travers ~35 kΩ : le
  courant (< 0,1 mA) est absorbé par les diodes de protection du compas,
  c'est sans danger pratique. Ensuite la ligne ne monte qu'à 3,3 V
  (l'I2C ne fait que tirer vers 0 V). L'Uno lit un "1" à partir de 3,0 V :
  3,3 V passe, avec peu de marge.

  CE QUE TU DOIS OBSERVER (moniteur série, 115200 bauds)
  ------------------------------------------------------
  - "Lignes au repos : SDA=1 SCL=1" -> câblage et rappels corrects.
  - Une ou plusieurs adresses trouvées, avec la puce identifiée.
  - Si aucune adresse : vérifier GND, 3,3 V, inversion SDA/SCL.
*/

#include <Wire.h>

// Lit un registre ; renvoie false si le composant ne répond pas.
static bool lireRegistre(uint8_t adresse, uint8_t registre, uint8_t &valeur) {
  Wire.beginTransmission(adresse);
  Wire.write(registre);
  if (Wire.endTransmission(false) != 0) return false;  // redémarrage répété
  if (Wire.requestFrom(adresse, (uint8_t)1) != 1) return false;
  valeur = Wire.read();
  return true;
}

static bool repond(uint8_t adresse) {
  Wire.beginTransmission(adresse);
  return Wire.endTransmission() == 0;
}

static void afficherHex(uint8_t v) {
  if (v < 0x10) Serial.print('0');
  Serial.print(v, HEX);
}

// Essaie de reconnaître la puce grâce à ses registres d'identification.
static void identifier(uint8_t a) {
  uint8_t r0, r1, r2;

  // Honeywell HMC5883L / HMC5983 : registres 0x0A..0x0C = 'H' '4' '3'
  if (lireRegistre(a, 0x0A, r0) && lireRegistre(a, 0x0B, r1) &&
      lireRegistre(a, 0x0C, r2) && r0 == 'H' && r1 == '4' && r2 == '3') {
    Serial.println(F("  -> HMC5883L ou HMC5983 (Honeywell, ou clone compatible)"));
    return;
  }
  // ST LIS3MDL : WHO_AM_I (0x0F) = 0x3D
  if (lireRegistre(a, 0x0F, r0) && r0 == 0x3D) {
    Serial.println(F("  -> LIS3MDL (ST)"));
    return;
  }
  // iSentek IST8310 : WAI (0x00) = 0x10
  if (lireRegistre(a, 0x00, r0) && r0 == 0x10) {
    Serial.println(F("  -> IST8310 (iSentek)"));
    return;
  }
  // AKM AK8963 : WIA (0x00) = 0x48
  if (lireRegistre(a, 0x00, r0) && r0 == 0x48) {
    Serial.println(F("  -> AK8963 (AKM)"));
    return;
  }
  // AKM AK09916 : WIA2 (0x01) = 0x09
  if (lireRegistre(a, 0x01, r0) && r0 == 0x09) {
    Serial.println(F("  -> AK09916 (AKM)"));
    return;
  }
  // QST QMC5883L : registre 0x0D = 0xFF (à l'adresse 0x0D)
  if (a == 0x0D && lireRegistre(a, 0x0D, r0) && r0 == 0xFF) {
    Serial.println(F("  -> QMC5883L (QST)"));
    return;
  }
  Serial.println(F("  -> puce non reconnue (envoie-moi le vidage ci-dessous)"));
}

// Vidage des registres 0x00..0x0F pour analyse.
static void viderRegistres(uint8_t a) {
  Serial.print(F("  registres 00..0F :"));
  for (uint8_t r = 0; r < 0x10; r++) {
    uint8_t v;
    Serial.print(' ');
    if (lireRegistre(a, r, v)) afficherHex(v);
    else Serial.print(F("--"));
  }
  Serial.println();
}

void setup() {
  Serial.begin(115200);
  Serial.println(F("\n=== Etape 1 : scanner I2C du compas ==="));

  // Avant Wire.begin(), les broches sont des entrées sans rappel :
  // on peut voir si les résistances externes tirent bien vers le haut.
  Serial.print(F("Lignes au repos : SDA="));
  Serial.print(digitalRead(SDA));
  Serial.print(F(" SCL="));
  Serial.println(digitalRead(SCL));
  if (!digitalRead(SDA) || !digitalRead(SCL)) {
    Serial.println(F("ATTENTION : une ligne est a 0. Verifier les 4,7 kOhm vers 3,3 V,"));
    Serial.println(F("le GND et l'alimentation du compas. Le scan risque d'echouer."));
  }

  Wire.begin();
  // Coupe les rappels internes vers 5 V (voir en-tête).
  digitalWrite(SDA, LOW);
  digitalWrite(SCL, LOW);
  Wire.setClock(100000);           // 100 kHz, le plus tolérant
  Wire.setWireTimeout(25000, true);  // évite un blocage si le bus est coincé
}

void loop() {
  Serial.println(F("\nScan des adresses 0x08 a 0x77..."));
  uint8_t trouves = 0;
  for (uint8_t a = 0x08; a <= 0x77; a++) {
    if (!repond(a)) continue;
    trouves++;
    Serial.print(F("Trouve : 0x"));
    afficherHex(a);
    Serial.println();
    identifier(a);
    viderRegistres(a);
  }
  if (Wire.getWireTimeoutFlag()) {
    Serial.println(F("Bus I2C bloque (delai depasse) : verifier le cablage."));
    Wire.clearWireTimeoutFlag();
  }
  if (trouves == 0) Serial.println(F("Aucun composant I2C trouve."));
  delay(5000);
}
