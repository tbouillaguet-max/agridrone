# Module : `formation-tp`

> Dossier : `src/modules/formation-tp/`. Plan et progression des étapes : [`GUIDE.md`](GUIDE.md).

## 1. Rôle
TP guidé qui fait construire pas à pas le planificateur web et le dialogue avec AU2 (protocole), à partir du code réel du projet. Public : à l'aise en électronique et en C++.

## 2. Interfaces (Contrat d'entrée/sortie)
- **Point d'entrée** : `GUIDE.md` ; fiches `etape_04_carte_web.md`, `etape_05_chemin_quadrillage.md` ; exercices dans `exercices_web/`, corrections dans `corrections/web/`.
- **Entrées** : code de référence de `planificateur` et `protocole`.
- **Sorties** : fiches, exercices et corrections ; aucun fichier de contrat.
- Étapes A à G (protocole C++, liaison AU2 ↔ AU1, journal de vol, arrêt d'urgence, caméra, essais) : à écrire.

## 3. Dépendances Déclarées
- **Consomme** : `planificateur`, `protocole`
- **Fournit à** : aucun
- **Données (`data/`)** : aucune

## 4. Commandes Propres
Depuis `src/modules/formation-tp/exercices_web/`.
- **Techno** : JS + Markdown (aucune dépendance)
- **Installer** : aucune
- **Lancer** : `lancer.bat` ou `lancer.sh`
- **Tests** : `npm test` (exercices) ; `npm run test:corrections` (corrections)

## 5. Règle d'Isolation (Interdits)
- Les numéros d'étape 4 et 5 sont conservés pour ne pas casser les liens des exercices.
- Quand le code de `planificateur` ou `protocole` change, vérifier que les corrections correspondent encore à la pièce complète.
- Ne jamais importer le code interne d'un autre module : les exercices sont des versions réduites copiées.
