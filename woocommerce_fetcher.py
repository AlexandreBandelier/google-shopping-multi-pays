# woocommerce_fetcher.py
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def safe_api_get(wcapi, endpoint, params=None, max_retries=3):
    """Effectue un appel API WooCommerce sécurisé avec tentative de reconnexion."""
    if params is None:
        params = {}

    for attempt in range(1, max_retries + 1):
        try:
            response = wcapi.get(endpoint, params=params)
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(
                    f"Tentative {attempt}/{max_retries} - Erreur API {endpoint} : "
                    f"Code {response.status_code}"
                )
        except Exception as e:
            logger.warning(
                f"Tentative {attempt}/{max_retries} - Exception lors de l'appel {endpoint} : {e}"
            )
        time.sleep(2 * attempt)

    logger.error(f"Échec de la récupération des données pour {endpoint} après {max_retries} tentatives.")
    return []


def fetch_all_products_with_variations(wcapi, lang="fr"):
    """
    Extrait l'ensemble des produits et leurs variations depuis WooCommerce
    en passant impérativement le filtre de langue WPML.
    """
    # Extraction du code court de langue pour WPML (ex: 'es_ES' -> 'es', 'de_DE' -> 'de')
    wpml_lang = lang.split("_")[0] if "_" in lang else lang

    all_products = []
    page = 1

    logger.info(f"Début de l'extraction des produits pour la langue : {lang} (WPML lang='{wpml_lang}')")

    while True:
        # Transmission explicite de 'lang' à WPML dans la requête API
        params = {
            "per_page": 100,
            "page": page,
            "status": "publish",
            "lang": wpml_lang,  # Paramètre crucial pour que WPML renvoie les vrais slugs traduits
        }

        products = safe_api_get(wcapi, "products", params=params)

        if not products:
            break

        for product in products:
            all_products.append(product)

            # Si le produit est variable, extraire ses déclinaisons avec le même paramètre de langue
            if product.get("type") == "variable":
                product_id = product.get("id")
                var_page = 1
                while True:
                    var_params = {
                        "per_page": 100,
                        "page": var_page,
                        "lang": wpml_lang,  # Transmission du paramètre de langue aux variations
                    }
                    variations = safe_api_get(
                        wcapi, f"products/{product_id}/variations", params=var_params
                    )

                    if not variations:
                        break

                    for variation in variations:
                        # Fusion des métadonnées parentes utiles
                        variation["parent_id"] = product_id
                        variation["description"] = variation.get("description") or product.get("description")
                        variation["short_description"] = product.get("short_description")
                        variation["brands"] = product.get("brands", [])

                        # Si la variation n'a pas d'images propres, utiliser celles du parent
                        if not variation.get("images"):
                            variation["images"] = product.get("images", [])

                        all_products.append(variation)

                    var_page += 1

        logger.info(f"-> Page {page} récupérée pour [{lang}] ({len(products)} produits principaux)")
        page += 1

    logger.info(f"Total produits & variations récupérés pour [{lang}] : {len(all_products)}")
    return all_products
