# woocommerce_fetcher.py
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_WORKERS = 5  # Nombre de requêtes simultanées vers l'API WooCommerce

def safe_api_get(wcapi, endpoint, params=None, max_retries=3):
    """Effectue une requête GET sécurisée avec réessais en cas d'erreur temporaire."""
    for attempt in range(1, max_retries + 1):
        try:
            response = wcapi.get(endpoint, params=params)
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Tentative {attempt}/{max_retries} : {endpoint} a renvoyé le statut {response.status_code}")
        except Exception as e:
            logger.warning(f"Tentative {attempt}/{max_retries} : Erreur sur {endpoint} ({e})")
            
    logger.error(f"Échec définitif pour la requête : {endpoint}")
    return None

def fetch_product_variations(wcapi, parent_id, lang="fr"):
    """Récupère toutes les variations d'un produit parent donné."""
    variations = []
    page = 1

    while True:
        params = {
            "per_page": 100, 
            "page": page,
            "lang": lang
        }
        res = safe_api_get(wcapi, f"products/{parent_id}/variations", params=params)
        
        if not res:
            break
            
        variations.extend(res)
        page += 1

    return variations


def fetch_all_products_with_variations(wcapi, lang="fr"):
    """
    Récupère l'ensemble des produits (simples et déclinaisons/variations) 
    depuis l'API WooCommerce en filtrant par langue grâce à WPML.
    """
    all_items = []
    page = 1

    logger.info(f"Début de la récupération des produits WooCommerce (Langue: {lang.upper()})...")

    while True:
        params = {
            "per_page": 100, 
            "page": page, 
            "status": "publish",
            "lang": lang  # Transmet le filtre de langue à WPML
        }
        
        products = safe_api_get(wcapi, "products", params=params)

        if not products:
            break

        logger.info(f"-> Page {page} récupérée ({len(products)} produits - {lang.upper()})")

        for product in products:
            product_type = product.get('type')

            # Si le produit est variable, on extrait toutes ses déclinaisons
            if product_type == 'variable':
                variations = fetch_product_variations(wcapi, product['id'], lang=lang)
                
                if variations:
                    # Conserve les images du produit parent si les déclinaisons n'en ont pas
                    parent_images = product.get('images', [])
                    for var in variations:
                        var['parent_id'] = product['id']
                        if not var.get('images') and parent_images:
                            var['images'] = parent_images
                        all_items.append(var)
                else:
                    # En cas de repli si la déclinaison ne remonte pas
                    all_items.append(product)
            else:
                # Produit simple ou autre type
                all_items.append(product)

        page += 1

    logger.info(f"Extraction terminée ({lang.upper()}) : {len(all_items)} articles/déclinaisons récupérés au total.")
    return all_items
