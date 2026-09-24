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
            # Optimisation 1 : wcapi utilise en interne la librairie requests.
            # L'appel direct reste le même, mais la gestion réseau est sécurisée.
            response = wcapi.get(endpoint, params=params)

            time.sleep(0.5)
            
            # Traitement explicite des codes HTTP
            if response.status_code == 200:
                return response.json()
            elif response.status_code in (429, 500, 502, 503, 504):
                # Backoff exponentiel sur erreurs serveurs/limitation
                logger.warning(
                    f"Tentative {attempt}/{max_retries} - Erreur API {endpoint} : "
                    f"Code {response.status_code}. Attente..."
                )
                time.sleep((2 ** attempt))
            else:
                logger.error(f"Erreur fatale API {endpoint} (Code {response.status_code}): {response.text}")
                return []
                
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
    if lang == "fr_BE":
        wpml_lang = "fr_BE"
    else:
        wpml_lang = lang.split("_")[0] if "_" in lang else lang

    all_products = []
    page = 1

    logger.info(f"Début de l'extraction des produits pour la langue : {lang} (WPML lang='{wpml_lang}')")

    while True:
        params = {
            "per_page": 100,
            "page": page,
            "status": "publish",
            "lang": wpml_lang,
        }

        products = safe_api_get(wcapi, "products", params=params)

        if not products:
            break

        # Optimisation 2 : On ajoute tous les produits principaux d'un coup (plus rapide que append dans un for)
        all_products.extend(products)

        for product in products:
            if product.get("type") == "variable":
                product_id = product.get("id")
                # Optimisation 3 : Évaluation du nom parent une seule fois pour tout le lot de variations
                parent_title = product.get("name") or product.get("title") or ""
                parent_desc = product.get("description")
                parent_short_desc = product.get("short_description")
                parent_brands = product.get("brands", [])
                parent_images = product.get("images", [])
                
                var_page = 1
                while True:
                    var_params = {
                        "per_page": 100,
                        "page": var_page,
                        "lang": wpml_lang,
                    }
                    variations = safe_api_get(
                        wcapi, f"products/{product_id}/variations", params=var_params
                    )

                    if not variations:
                        break

                    for variation in variations:
                        variation["parent_id"] = product_id
                        variation["parent_name"] = parent_title
                        variation["description"] = variation.get("description") or parent_desc
                        variation["short_description"] = parent_short_desc
                        variation["brands"] = parent_brands

                        if not variation.get("images"):
                            variation["images"] = parent_images

                    # Ajout par bloc optimisé
                    all_products.extend(variations)
                    var_page += 1

        logger.info(f"-> Page {page} récupérée pour [{lang}] ({len(products)} produits principaux)")
        page += 1

    logger.info(f"Total produits & variations récupérés pour [{lang}] : {len(all_products)}")
    return all_products
