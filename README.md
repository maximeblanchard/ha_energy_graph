# Graphique d'énergie (`ha_energy_graph`)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=maximeblanchard&repository=ha_energy_graph&category=integration)
[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=ha_energy_graph)

Intégration Home Assistant sans dépendances générant un **camembert** et un **graphique en aires empilées** de la consommation du jour, accompagnés d'une **page web interactive** (zoom, pan, historique par date, infobulles détaillées).

---

## 🚀 Installation

### Méthode 1 : Via HACS (recommandé)

1. Cliquez sur le bouton **Ouvrir dans HACS** en haut de cette page pour ajouter le dépôt *(ou dans HACS > Menu 3 points > **Dépôts personnalisés** > URL : `https://github.com/maximeblanchard/ha_energy_graph`, Type : **Intégration**)*.
2. Cliquez sur **Télécharger**.
3. **Redémarrez Home Assistant**.
4. Cliquez sur le bouton **Ajouter l'intégration** en haut de cette page *(ou allez dans **Paramètres** > **Appareils et services** > **Ajouter une intégration** > recherchez **« Graphique d'énergie »**)*.

---

### Méthode 2 : Installation manuelle

1. Téléchargez ou clonez ce dépôt.
2. Copiez le dossier `custom_components/ha_energy_graph` dans votre répertoire `/config/custom_components/`.
3. Redémarrez Home Assistant.
4. Allez dans **Paramètres** > **Appareils et services** > **Ajouter une intégration** > recherchez **« Graphique d'énergie »**.

---

## ⚙️ Configuration

Une fois l'intégration ajoutée, cliquez sur **Configurer** pour gérer vos appareils :
- **Compteur d'énergie** : compteur cumulatif Zigbee/Z-Wave ou remis à zéro chaque jour (ex. prises Tapo, Shelly, Tuya).
- **Capteur de puissance** : puissance instantanée en Watts (`measurement`).
- **Lumières / Ampoules** : puissance maximale en Watts (à 100 %). **La puissance réelle consommée est automatiquement modulée selon la luminosité (`brightness`)** tant que la lumière est allumée.
- **Consommation fixe** : valeur en Wh/24h répartie de manière continue sur la journée (ex. VMC, box Internet).
- **Capteur d'énergie totale de la maison** : permet de calculer automatiquement la catégorie **« Autre »** (différence entre le total du logement et la somme des appareils suivis).

---

## 📊 Entités créées

- **Images SVG (mises à jour automatiquement) :**
  - `image.<nom>_camembert` : répartition en camembert du jour.
  - `image.<nom>_aires_empilees` : courbe en aires empilées lissées au cours de la journée.
- **Capteurs d'énergie :**
  - `sensor.*_aujourd_hui` : kWh consommés aujourd'hui pour chaque appareil, pour le total et pour la catégorie « Autre ».
  - Attribut `url_interactive` sur les entités permettant d'ouvrir la vue interactive (dans une carte `iframe` par exemple).

---

## 🌐 Page web interactive

Accessible via l'URL fournie dans l'attribut `url_interactive` :
`/api/ha_energy_graph/<entry_id>/<token>?v=both&date=AAAA-MM-JJ` (options `v` : `pie`, `area` ou `both`).

- **Navigation temporelle** : sélecteur de date, boutons ◀ / ▶ et raccourci « Aujourd'hui ».
- **Graphique en aires interactif** :
  - Résolution ajustable : 5, 10, 15, 30 ou 60 minutes.
  - Lissage paramétrable (aucun, léger, moyen, fort).
  - Échelle **linéaire** ou **compressée ($\sqrt{x}$)** : met en valeur les veilles et faibles consommations face aux gros pics.
  - Regroupement des couches par catégorie de couleur.
  - Zoom & déplacement : sélection à la souris, boutons $+/-$, `Ctrl + molette`, double-clic pour réinitialiser.
  - Infobulle détaillée sur chaque tranche horaire.
  - Légende interactive permettant de masquer/afficher des appareils au clic.
- **Rechargement automatique** : synchronisé toutes les 5 minutes juste après la compilation des statistiques de Home Assistant (se met en pause pendant que vous zoomez).

---

## 🛠️ Réglages avancés (Configurer > Capteur total et réglages)

- **Fréquence de mise à jour** : multiple de 5 minutes calé sur le cycle d'agrégation de Home Assistant.
- **Lissage des compteurs quantifiés** : supprime les faux pics générés par les compteurs qui ne remontent qu'en gros paliers (ex. par tranches de 20 Wh ou 100 Wh) en redistribuant l'énergie vers l'arrière tout en conservant scrupuleusement le total consommé.
- **Seuil de veille** : étale la consommation de veille continue depuis le palier précédent ou minuit.
- **Palier isolé** : étale un palier ponctuel isolé sur les $X$ dernières minutes.
