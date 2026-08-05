# woocommerce_fetcher.py
import logging
import time
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


def fetch_product_variations(wcapi, parent_product, lang="fr_FR"):
    """
    Récupère toutes les variations d'un produit parent donné
    et hérite intelligemment des métadonnées du parent si absentes.
    """
    parent_id = parent_product['id']
    parent_images = parent_product.get('images', [])
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
            var['parent_id'] = parent_id
            # Optimisation : Si la variation n'a pas d'image propre, elle hérite des images du parent
            if not var.get('images') and parent_images:
                var['images'] = parent_images
            variations.append(var)

        page += 1

    return variations


def fetch_all_products_with_variations(wcapi, lang="fr_FR"):
    """
    Récupère l'ensemble des produits (simples et déclinaisons)
    depuis l'API WooCommerce en filtrant par langue WPML.
    Optimisation : Utilisation du multithreading pour accélérer la récupération des déclinaisons.
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
            "lang": lang,  # Transmet le filtre régional/langue à WPML (ex: fr_FR, de_DE)
        }

        products = safe_api_get(wcapi, "products", params=params)

        if not products:
            break

        logger.info(
            f"-> Page {page} récupérée ({len(products)} produits - {lang})"
        )

        variable_products = []

        for product in products:
            if product.get('type') == 'variable':
                variable_products.append(product)
            else:
                all_items.append(product)

        # Optimisation : Récupération parallèle multithreadée des variations pour les produits variables de la page
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
                            # Repli sur le produit parent si aucune variante n'est extraite
                            all_items.append(parent_prod)
                    except Exception as e:
                        logger.error(
                            f"Erreur lors de l'extraction des variations du produit {parent_prod.get('id')}: {e}"
                        )
                        all_items.append(parent_prod)

        page += 1

    logger.info(
        f"Extraction terminée ({lang}) : {len(all_items)} articles/déclinaisons récupérés au total."
    )
    return all_items
