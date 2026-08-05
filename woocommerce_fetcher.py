# woocommerce_fetcher.py
import logging
import time
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Nombre de requêtes simultanées vers l'API WooCommerce pour les variations
MAX_WORKERS = 2


def safe_api_get(wcapi, endpoint, params=None, max_retries=3):
    """
    Effectue une requête GET sécurisée sur l'API WooCommerce.
    Optimisation : Attente exponentielle (Backoff) pour éviter de surcharger l'API.
    """
    if params is None:
        params = {}

    for attempt in range(1, max_retries + 1):
        try:
            response = wcapi.get(endpoint, params=params)
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(
                    f"Tentative {attempt}/{max_retries} : {endpoint} a renvoyé le statut {response.status_code}"
                )
        except Exception as e:
            logger.warning(
                f"Tentative {attempt}/{max_retries} : Erreur sur {endpoint} ({e})"
            )

        # Attente exponentielle (2s, 4s, 8s...)
        time.sleep(2**attempt)

    logger.error(f"Échec définitif pour la requête : {endpoint}")
    return None


def get_availability_date(days_ahead=20):
    """
    Calcule la date de disponibilité future au format ISO 8601 (YYYY-MM-DD)
    exigé par Google Merchant Center pour les produits en réapprovisionnement/précommande.
    """
    future_date = datetime.now(timezone.utc) + timedelta(days=days_ahead)
    return future_date.strftime("%Y-%m-%d")


def extract_color(product, parent_product=None):
    """
    Extrait intelligemment la couleur d'un produit ou d'une variation.
    Analyse les attributs WooCommerce (ex: pa_couleur, couleur, color).
    Hérite du parent si la variation n'a pas de couleur propre définie.
    """
    target_names = {"couleur", "color", "pa_couleur", "pa_color"}

    # 1. Recherche dans les attributs du produit actuel
    attributes = product.get("attributes", [])
    if isinstance(attributes, list):
        for attr in attributes:
            name = str(attr.get("name", "")).lower().strip()
            if name in target_names or any(t in name for t in target_names):
                # Cas d'une variation (clé 'option')
                if "option" in attr and attr["option"]:
                    return str(attr["option"]).strip()
                # Cas d'un produit simple/parent (clé 'options')
                elif "options" in attr and attr["options"]:
                    options = attr["options"]
                    if isinstance(options, list) and len(options) > 0:
                        return str(options[0]).strip()
                    elif isinstance(options, str):
                        return options.strip()

    # 2. Si non trouvé et qu'un parent existe, recherche dans le parent
    if parent_product:
        return extract_color(parent_product, None)

    return None


def enrich_product_data(product, parent_product=None):
    """
    Optimisation 1 : Pipeline d'enrichissement automatique.
    Calcule et valide toutes les métadonnées requises pour Google Shopping :
    - Disponibilité exacte ('in_stock', 'backorder', 'out_of_stock')
    - Date de disponibilité (+20 jours si backorder)
    - Couleur extraite
    """
    stock_status = str(product.get("stock_status", "instock")).lower()

    # Gestion du statut de stock et de la date de disponibilité
    if stock_status in ["onbackorder", "backorder"]:
        product["calculated_availability"] = "backorder"
        product["calculated_availability_date"] = get_availability_date(20)
    elif stock_status in ["outofstock", "out_of_stock"]:
        product["calculated_availability"] = "out_of_stock"
        product["calculated_availability_date"] = None
    else:
        product["calculated_availability"] = "in_stock"
        product["calculated_availability_date"] = None

    # Extraction et assignation de la couleur
    product["extracted_color"] = extract_color(product, parent_product)

    return product


def fetch_product_variations(wcapi, parent_product, lang="fr_FR"):
    """
    Récupère toutes les variations d'un produit parent donné,
    hérite intelligemment des métadonnées du parent (images, attributs, couleur)
    et enrichit les données à la volée.
    """
    parent_id = parent_product["id"]
    parent_images = parent_product.get("images", [])
    variations = []
    page = 1

    while True:
        params = {"per_page": 100, "page": page, "lang": lang}
        res = safe_api_get(
            wcapi, f"products/{parent_id}/variations", params=params
        )

        if not res:
            break

        for var in res:
            var["parent_id"] = parent_id

            # Héritage des images du parent si la variation n'en a pas
            if not var.get("images") and parent_images:
                var["images"] = parent_images

            # Héritage du nom/titre du parent si manquant
            if not var.get("name") and parent_product.get("name"):
                var["name"] = parent_product["name"]

            # Enrichissement des données de la variation
            enriched_var = enrich_product_data(var, parent_product=parent_product)
            variations.append(enriched_var)

        page += 1

    return variations


def fetch_all_products_with_variations(wcapi, lang="fr_FR"):
    """
    Récupère l'ensemble des produits (simples et déclinaisons)
    depuis l'API WooCommerce en filtrant par langue WPML.
    Optimisation 3 : Multithreading optimisé & Enrichissement automatique systématique.
    """
    all_items = []
    page = 1

    logger.info(
        f"Début de la récupération des produits WooCommerce (Langue WPML: {lang})..."
    )

    while True:
        params = {
            "per_page": 100,
            "page": page,
            "status": "publish",
            "lang": lang,
        }

        products = safe_api_get(wcapi, "products", params=params)

        if not products:
            break

        logger.info(
            f"-> Page {page} récupérée ({len(products)} produits - {lang})"
        )

        variable_products = []

        for product in products:
            if product.get("type") == "variable":
                variable_products.append(product)
            else:
                # Produit simple : enrichissement direct
                enriched_product = enrich_product_data(product)
                all_items.append(enriched_product)

        # Extraction parallèle multithreadée des variations
        if variable_products:
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {
                    executor.submit(
                        fetch_product_variations, wcapi, p, lang
                    ): p
                    for p in variable_products
                }
                for future in as_completed(futures):
                    parent_prod = futures[future]
                    try:
                        variations = future.result()
                        if variations:
                            all_items.extend(variations)
                        else:
                            # Repli sur le produit parent enrichi si aucune variante n'est extraite
                            all_items.append(enrich_product_data(parent_prod))
                    except Exception as e:
                        logger.error(
                            f"Erreur lors de l'extraction des variations du produit {parent_prod.get('id')}: {e}"
                        )
                        all_items.append(enrich_product_data(parent_prod))

        page += 1

    logger.info(
        f"Extraction terminée ({lang}) : {len(all_items)} articles/déclinaisons récupérés et enrichis au total."
    )
    return all_items
