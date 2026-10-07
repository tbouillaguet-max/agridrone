# Demandes de données aux auteurs

Trois jeux sont très utiles mais pas (ou pas entièrement) téléchargeables librement. La
seule façon de les obtenir est d'écrire aux auteurs. Les adresses ci-dessous sont celles
que les auteurs publient eux-mêmes pour ce type de demande (fiche Zenodo ou article).

## Comment procéder

- **Écrire depuis votre adresse professionnelle** et nommer votre société.
- **Annoncer l'usage commercial.** Une autorisation obtenue pour de la « recherche » ne
  couvrirait pas le produit. Mieux vaut un refus clair qu'une autorisation inutilisable.
- **Demander la licence par écrit** (un mail suffit) et le garder : je l'archiverai avec
  les données (`reports/licences/`).
- **Délais** : comptez souvent plusieurs semaines. Une seule relance au bout de 2 à 3
  semaines. Réponses possibles : oui sous CC BY (idéal), oui mais non commercial (alors
  inutilisable pour le produit), ou pas de réponse.
- Dès réception, j'intègre les données au pipeline (chantier 2), avec somme de contrôle et
  licence enregistrées.

Priorité : **1 (John Innes)**, puis 2, puis 3.

---

## 1. John Innes Centre : jeu complet de 19 172 images de maladies du blé

- **Ce que c'est.** Les 999 images publiques (CC BY 4.0) sont un extrait d'un jeu de
  19 172 images couvrant 5 catégories : sain, rouille jaune, rouille brune, oïdium et
  septoriose, prises au champ et en serre au Royaume-Uni.
- **Pourquoi.** Ce sont exactement nos classes. Le jeu complet multiplie par environ 19
  les données d'entraînement du chantier 4, c'est le gain le plus important possible.
- **À qui.** James Brown, John Innes Centre : james.brown@jic.ac.uk. La fiche
  [Zenodo 7573133](https://zenodo.org/records/7573133) indique que le jeu complet est
  *« available on request »* auprès de lui.
- **Ce qu'il faut obtenir.**
  1. L'accès au jeu complet.
  2. Une licence compatible avec l'usage commercial, idéalement CC BY 4.0 comme l'extrait.
  3. Les métadonnées par image (date, lieu, champ ou serre, appareil), indispensables pour
     découper train/val/test par source et par date.

**Brouillon :**

> Subject: Request for the full wheat disease image dataset (Long et al., 2023)
>
> Dear Prof. Brown,
>
> I am [name], [role] at [company], where we are developing a drone-based crop monitoring
> system for winter wheat in France. We have been using the 999-image subset you published
> on Zenodo (record 7573133, CC BY 4.0) together with Long et al. (2023, Plant Pathology).
>
> The record mentions that the full dataset of 19,172 images is available on request. Would
> you be willing to share it with us? To be transparent: our goal is a commercial product,
> so we would need the data under terms that allow commercial use, ideally the same CC BY
> 4.0 licence as the subset, with full attribution to your team in our documentation.
>
> If possible, per-image metadata (acquisition date, site, field or glasshouse, device)
> would also help us build train/test splits without leakage between images from the same
> session.
>
> Thank you very much for considering this request.
>
> Best regards,
> [name, company, address, phone]

---

## 2. Su et al. : rouille jaune en multispectral RedEdge (Yangling, 2018–2019)

- **Ce que c'est.** Des orthomosaïques de réflectance à 5 bandes (MicaSense RedEdge, drone
  DJI M100, vol à ~20 m, ~1,3 cm/px), sur 18 micro-parcelles de blé d'hiver inoculées à
  6 niveaux de rouille jaune. Elles sont accompagnées de masques au pixel en 3 classes
  (rouille, sain, fond). C'est le jeu utilisé dans Su et al. 2018 et 2021 et dans Ir-UNet
  (2021).
- **Pourquoi.** C'est le seul jeu connu qui correspond exactement à la tâche visée par le
  chantier 5 : segmenter des zones malades de blé en multispectral drone. L'article de
  2021 (IEEE TII) dit que l'expérience a été conçue *« to generate an open-access
  dataset »*, mais aucun lien n'est publié et l'article Ir-UNet indique *« Data sharing is
  not applicable »*.
- **À qui.** Jinya Su (University of Essex) : j.su@essex.ac.uk, adresse donnée dans
  l'article Ir-UNet. En copie, Cunjia Liu (Loughborough University) : C.Liu5@lboro.ac.uk,
  auteur correspondant de l'article TII.
- **Ce qu'il faut obtenir.**
  1. Les orthomosaïques de réflectance calibrée (GeoTIFF, 5 bandes) de 2019, et si
     possible la série de 2018.
  2. Les masques d'étiquettes.
  3. Le plan des parcelles avec les niveaux d'inoculum.
  4. Une licence compatible avec l'usage commercial.

**Brouillon :**

> Subject: Access to the UAV multispectral wheat yellow rust dataset (Su et al. 2021; Zhang et al. 2021)
>
> Dear Dr Su, dear Prof. Liu,
>
> I am [name], [role] at [company]. We are developing a drone-based monitoring system for
> winter wheat diseases in France, and your work on yellow rust monitoring with RedEdge
> multispectral imagery (Su et al., IEEE TII 2021; Zhang et al., Remote Sensing 2021) is
> the closest reference to our use case.
>
> Your TII paper mentions that the field experiment at Caoxinzhuang (2019) was designed to
> generate an open-access dataset, but we could not find where it is hosted. Would it be
> possible to obtain:
> - the calibrated 5-band reflectance orthomosaics (and the 2018 time series if available),
> - the pixel-level labels (rust / healthy / background),
> - the plot layout with inoculum levels?
>
> To be transparent, our objective is a commercial product, so we would need terms that
> allow commercial use (for example CC BY 4.0), with full attribution and citation of your
> papers. We would of course be happy to share our benchmark results with you.
>
> Thank you for your consideration.
>
> Best regards,
> [name, company, address, phone]

---

## 3. Nguyen et al. 2023 : rouille jaune par micro-parcelle, DJI P4 Multispectral (Argentine, 2021)

- **Ce que c'est.** 700 micro-parcelles de blé de printemps (1,2 × 5 m) survolées en DJI
  P4 Multispectral à 20 m (1,04 cm/px). Chaque parcelle est notée sain / infection légère /
  infection sévère (592 parcelles notées), avec le rendement par parcelle.
- **Pourquoi.** Même famille de drone que ce que vous pourriez utiliser (P4M, 5 bandes),
  et de nombreuses parcelles. Les étiquettes sont **par parcelle** et non par pixel : elles
  servent à classer des zones, ou comme supervision faible pour la segmentation. Les
  données sont annoncées « disponibles sur demande ».
- **À qui.** Vasit Sagan (Saint Louis University), auteur correspondant :
  vasit.sagan@slu.edu.
- **Point d'attention.** L'étude a été menée avec un semencier (GDM Seeds). Les droits sur
  les données peuvent donc être partagés, et une demande commerciale peut être refusée.

**Brouillon :**

> Subject: Data request – Early detection of wheat yellow rust with multispectral UAV imagery (Remote Sensing 2023, 15, 3301)
>
> Dear Prof. Sagan,
>
> I am [name], [role] at [company], developing a drone-based disease monitoring system for
> winter wheat. Your 2023 study in Chacabuco with the DJI P4 Multispectral is highly
> relevant to us, and the paper indicates that the data are available on request.
>
> Would it be possible to obtain the reflectance orthomosaics, the plot boundaries, and the
> plot-level disease ratings (healthy / mild / severe) with yields? Our goal is a
> commercial product, so we would need to know under which terms the data could be used
> commercially; we would fully credit the authors and GDM Seeds.
>
> Thank you very much for your time.
>
> Best regards,
> [name, company, address, phone]
