// Paramètres du planificateur, regroupés ici. Modifiez ce fichier puis
// rechargez la page (Ctrl+F5).

export const CONFIG = {
  // --- Carte -----------------------------------------------------------------
  centreParDefaut: [46.6, 2.4], // France
  zoomParDefaut: 6,
  // Fonds de carte gratuits. Orthophotos IGN (Géoplateforme) : licence ouverte
  // Etalab 2.0, sans clé, résolution 20 cm en France. OSM : ODbL.
  fonds: {
    "Orthophotos IGN": {
      url: "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image/jpeg",
      options: { maxNativeZoom: 19, maxZoom: 22, attribution: "© IGN Géoplateforme (orthophotos)" },
    },
    "Plan IGN": {
      url: "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&STYLE=normal&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image/png",
      options: { maxNativeZoom: 19, maxZoom: 22, attribution: "© IGN Géoplateforme" },
    },
    OpenStreetMap: {
      url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      options: { maxNativeZoom: 19, maxZoom: 22, attribution: "© contributeurs OpenStreetMap" },
    },
  },
  calques: {
    "Parcelles agricoles (RPG)": {
      url: "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=LANDUSE.AGRICULTURE.LATEST&STYLE=normal&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image/png",
      options: { minZoom: 6, maxNativeZoom: 16, maxZoom: 22, opacity: 0.55, attribution: "RPG © IGN / ASP" },
    },
    Cadastre: {
      url: "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=CADASTRALPARCELS.PARCELLAIRE_EXPRESS&STYLE=PCI%20vecteur&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image/png",
      options: { maxNativeZoom: 19, maxZoom: 22, attribution: "Cadastre © IGN / DGFiP" },
    },
  },

  // --- Caméra -----------------------------------------------------------------
  // TO DO : caméra programmable pas encore choisie. Valeurs PROVISOIRES d'une
  // caméra 12 Mpx générique (capteur 7,2 × 5,4 mm, focale 5,4 mm) : elles ne
  // servent qu'à faire tourner les calculs. Les remplacer par celles du modèle
  // retenu, puis passer `cameraProvisoire` à false (la vérification « Caméra »
  // reste en avertissement tant que c'est true).
  cameraProvisoire: true,
  camera: {
    capteurLargeurMm: 7.2,
    capteurHauteurMm: 5.4,
    focaleMm: 5.4,
    imageLargeurPx: 4000,
    imageHauteurPx: 3000,
    intervalleMinS: 1.0, // cadence de prise de vue que la caméra tient (à mesurer)
    expositionMinUs: 100,
  },

  // --- Cultures (choix obligatoire, enregistré dans mission.json) --------------
  // Non transmis au drone : sert au pipeline d'analyse (drone), qui choisit
  // le modèle de détection d'après cette valeur. Liste à garder identique au
  // registre des modèles du pipeline (pipeline\modeles.json).
  cultures: {
    ble: "Blé",
    mais: "Maïs",
    pommier: "Pommier",
  },

  // --- Paramètres proposés pour une nouvelle mission --------------------------
  mission: {
    altitudeM: 5,
    vitesseMaxMs: 0, // 0 = vitesse par défaut, limitée par la cadence photo
    recouvrementFrontalPct: 75,
    recouvrementLateralPct: 70,
    capPassesDeg: null, // null = automatique
    margeLimitesM: 2,
    margeZonesM: 3,
    grandCoteTransversal: true, // grand côté de l'image perpendiculaire aux passes
    finMission: "retour", // "retour" | "atterrir" | "stationnaire"
    vitesseManuelleMs: 2, // waypoints manuels
  },

  // --- Limites techniques du vol ----------------------------------------------
  tech: {
    vitesseDefautMs: 3,
    vitesseMaxAbsolueMs: 8,
    flouMaxPx: 1,
  },

  // --- Capacités d'AU2 et bornes autorisées ------------------------------------
  // À aligner avec les constantes du code d'AU2 (ProtocoleDrone.h : MAX_WAYPOINTS…).
  // Si AU2 ne peut pas stocker la mission, il répond CAPACITE_DEPASSEE.
  capacites: {
    maxWaypoints: 150,
    maxZones: 8,
    maxSommetsLimites: 30,
    maxSommetsZone: 16,
    hauteurMinM: 2,
    hauteurMaxM: 50, // ≤ 120 m (réglementation) : mettre la hauteur de l'autorisation préfectorale
    vitesseMaxMs: 8,
  },

  // --- Modèle énergétique (à étalonner avec les relevés de vol) ----------------
  // Phantom 3 Standard : batterie 4S 4480 mAh, 15,2 V, 68 Wh (masse à refaire
  // avec AU1, AU2 et la nouvelle caméra). Puissance
  // moyenne mesurable en vol : tension × courant (télémétrie d'AU1).
  drone: {
    puissanceMoyenneW: 200,
    capaciteBatterieWh: 68,
    tensionNominaleV: 15.2,
    reserveBatteriePct: 25,
    vitesseVerticaleMs: 1.5,
    vitesseTransitMs: 5,
    tempsParVirageS: 3,
    tempsDecollageAtterrissageS: 30,
  },

  // --- Transfert vers AU2 par le câble USB (Web Serial) -------------------------
  serie: {
    debitBauds: 115200,
    attenteDemarrageMs: 2000, // la Mega redémarre à l'ouverture du port (DTR)
    delaiReponseMs: 500,
    essais: 5,
    essaisRelecture: 2,
  },

  // --- Archivage des missions envoyées (serveur_local.py) ------------------------
  // Le dossier d'archive est choisi par serveur_local.py (option --missions).
  archivage: {
    actif: true,
  },
};
