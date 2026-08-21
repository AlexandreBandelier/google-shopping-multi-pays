# google-shopping-multi-pays

Ce projet automatise la génération, la localisation, la synchronisation et l'analyse de flux **Google Shopping XML (RSS 2.0)** et d'**Avis-clients Produits** pour une infrastructure WooCommerce multi-domaines.

---

## Vue d'Ensemble

Le script se connecte aux différentes instances de la boutique via l'API REST WooCommerce, extrait les produits (simples et déclinaisons), nettoie et normalise la donnée pour la rendre conforme aux exigences de **Google Merchant Center**, puis téléverse automatiquement les flux XML dans un dossier **Google Drive** centralisé via GitHub Actions.

Un volet **Data Analysis** permet également d'exploiter les flux XML générés pour effectuer du reporting e-commerce et piloter le catalogue produit.

---

## Couverture Multi-Pays & Multi-Devises

Le pipeline gère **8 domaines & langues** distincts avec adaptation automatique des devises (seulement deux devises), des libellés de stock, de la couleur et des tailles par défaut :

| Code Langue | Domaine Web | Devise | Fichier XML sur Google Drive |
| :--- | :--- | :---: | :--- |
| `fr_FR` | `https://mon-site.fr` | EUR | `Shopping Graph_feed.xml` |
| `fr_BE` | `https://mon-site.be` | EUR | `Shopping Graph_feed_BE.xml` |
| `de_DE` | `https://mon-site.de` | EUR | `Shopping Graph_feed_DE.xml` |
| `es_ES` | `https://mon-site.es` | EUR | `Shopping Graph_feed_ES.xml` |
| `it_IT` | `https://mon-site.it` | EUR | `Shopping Graph_feed_IT.xml` |
| `nl_NL` | `https://mon-site.nl` | EUR | `Shopping Graph_feed_NL.xml` |
| `da_DK` | `https://mon-site.dk` | DKK | `Shopping Graph_feed_DK.xml` |
| `en_GB` | `https://mon-site.eu` | EUR | `Shopping Graph_feed_EU.xml` |
| **Avis** | `mon-site.fr` (Source) | - | `product_reviews_feed.xml` |

---

## Architecture du Projet

```text
.
├── .github/
│   └── workflows/
│       └── google_shopping_feed.yml  # Automation CI/CD & Matrix Build GitHub Actions
├── feed_processor.py                 # Normalisation, nettoyage HTML, mapping d'attributs
├── woocommerce_fetcher.py           # Extraction API WooCommerce (Produits & Variations)
├── reviews_fetcher.py               # Extraction & formatage XML du flux d'Avis Clients
├── gdrive_uploader.py               # Gestion du téléversement/mise à jour sur Google Drive
├── main.py                          # Chef d'orchestre du pipeline
├── requirements.txt                 # Dépendances Python (WooCommerce, Google API, etc.)
├── .gitignore
├── LICENSE
└── README.md

```

---

## Fonctionnalités Clés

1. **Nettoyage & Sécurisation des Données (`feed_processor.py`)** :
* Regex optimisées pour nettoyer le HTML des descriptions et éliminer les faux titres qui s'inséraient précédemment (ex: "en stock", "expédié sous 24h").
* Gestion intelligente du nom du produit parent pour conserver une cohérence visuelle sur les variations.
* Extraction automatique du poids de livraison (`kg`), de la marque, de la couleur, du matériau et de la taille.
* Normalisation des attributs e-commerce personnalisés (`custom_label_0` à `custom_label_4` : Gamme, Catégorie, Public, Personnalisation, Statut de stock).


2. **Performance & Traitement en Mémoire (`main.py`)** :
* Utilisation de `io.StringIO` et `io.BytesIO` pour générer le XML directement en mémoire sans écriture disque inutile.
* Utilisation de blocs `CDATA` sécurisés pour éviter tout crash de parsing XML dans Google Merchant Center.


3. **Flux d'Avis-Clients (`reviews_fetcher.py`)** :
* Génération automatique du flux d'avis-clients depuis le site, au format accepté par Google Merchant Center Product Reviews.


4. **Gestion des Quotas Google Drive (`gdrive_uploader.py`)** :
* Contournement des limitations de quota des comptes de service Google Cloud en effectuant une mise à jour (`update`) des fichiers existants sur Drive au lieu d'une création à chaque exécution.



### Stack Data recommandée :

* **Python / Pandas / DuckDB :** Parsing des flux XML pour transformation en DataFrames / Tables SQL.
* **Power BI / Looker Studio :** Visualisation des KPI (Taux de disponibilité, répartition par marques/gammes).

---

## Workflow GitHub Actions

La mise à jour des flux est exécutée automatiquement via la matrice de builds configurée dans `.github/workflows/google_shopping_feed.yml` :

* **Déclenchement :** Planification automatique (CRON) ou manuelle (`workflow_dispatch`).
* **Matrice de jobs :** Traitement parallèle des pays cibles pour un temps d'exécution optimisé.

---

## Variables d'Environnement (Secrets GitHub)

Pour fonctionner, le projet nécessite la configuration des secrets suivants dans le dépôt GitHub (`Settings > Secrets and variables > Actions`) :

| Nom du Secret | Description |
| --- | --- |
| `WOO_URL` | URL de base WooCommerce par défaut |
| `WOO_KEY` | Clé Client API WooCommerce (`ck_...`) |
| `WOO_SECRET` | Clé Secrète API WooCommerce (`cs_...`) |
| `GDRIVE_FOLDER_ID` | Identifiant du dossier cible Google Drive |
| `GDRIVE_SERVICE_ACCOUNT_JSON` | Contenu JSON de la clé du compte de service Google Cloud |

---

## Installation & Exécution Locale

### 1. Prérequis

* Python 3.9+
* Un accès API REST WooCommerce fonctionnel

### 2. Installation

```bash
# Cloner le dépôt
git clone [https://github.com/](https://github.com/)[UTILISATEUR]/[NOM_DU_DEPOT].git
cd [NOM_DU_DEPOT]

# Installer les dépendances
pip install -r requirements.txt

```

### 3. Exécution locale (Exemple pour le domaine principal)

```bash
export WOO_KEY="votre_ck"
export WOO_SECRET="votre_cs"
export GDRIVE_FOLDER_ID="votre_folder_id"
export GDRIVE_SERVICE_ACCOUNT_JSON='{"type": "service_account", ...}'

# Lancement pour une langue spécifique
export TARGET_LANG="fr_FR"
export TARGET_FILE="Shopping Graph_feed.xml"

python main.py

```

---

## Licence

Ce projet est sous licence MIT - voir le fichier [LICENSE](https://www.google.com/search?q=LICENSE) pour plus de détails.

```

---

Souhaitez-vous que je modifie également les noms des fichiers Python si vous préférez masquer la logique interne, ou cette structure vous convient-elle ainsi ?

```
