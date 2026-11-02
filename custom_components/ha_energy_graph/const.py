"""Constantes de l'intégration Graphique d'énergie."""

DOMAIN = "ha_energy_graph"

CONF_TOTAL_ENTITY = "total_entity"
CONF_DEVICES = "devices"
CONF_KIND = "kind"
CONF_CATEGORY = "category"
CONF_WH_PER_DAY = "wh_per_day"
CONF_UPDATE_MINUTES = "update_minutes"
CONF_SMOOTH_HOURS = "smooth_hours"
CONF_SPREAD_MIN = "spread_min"
CONF_STANDBY_WH = "standby_wh"
CONF_IMAGE_SCALE = "image_scale"
CONF_IMAGE_GROUP = "image_group"
CONF_REMOVE = "remove"
CONF_TOKEN = "token"
CONF_ID = "id"
CONF_WATTS = "watts"

LIGHTS_ID = "lights"
LIGHTS_NAME = "Ampoules"

KIND_ENERGY = "energy"  # compteur d'énergie (total_increasing, ou remis à zéro chaque jour)
KIND_POWER = "power"  # capteur de puissance instantanée (W)
KIND_LIGHT = "light"  # lumière : watts comptés pendant qu'elle est allumée
KIND_FIXED = "fixed"  # consommation fixe (Wh / 24 h), lissée sur la journée

DEFAULT_UPDATE_MINUTES = 5
DEFAULT_SMOOTH_HOURS = 3.0
DEFAULT_SPREAD_MIN = 30.0
DEFAULT_STANDBY_WH = 20.0
DEFAULT_IMAGE_SCALE = "lin"
BUCKET_SECONDS = 300  # résolution des statistiques court terme du recorder

# clé: (libellé, teinte HSL en degrés, saturation)
# L'ordre de ce dict est l'ordre d'empilement dans les graphiques.
CATEGORIES: dict[str, tuple[str, int, float]] = {
    "informatique": ("Informatique", 225, 0.85),
    "multimedia": ("Multimédia / Loisirs", 205, 0.90),
    "eclairage": ("Éclairage", 280, 0.80),
    "cuisine": ("Cuisine", 8, 0.90),
    "chauffage": ("Chauffage / Climatisation", 24, 0.95),
    "eau_chaude": ("Eau chaude", 145, 0.95),
    "froid": ("Froid (frigo, congélateur)", 188, 0.95),
    "ventilation": ("Ventilation / VMC", 165, 0.90),
    "bien_etre": ("Piscine / Spa", 100, 0.85),
    "divers": ("Divers", 40, 0.45),
}

OTHER_LABEL = "Autre"
OTHER_COLOR = "#9e9e9e"
