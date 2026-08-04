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

def fetch_variations_for_product(wcapi, parent_prod):
    """Récupère toutes les variations d'un produit parent donné."""
    variations_list = []
    var_page = 1
    
    while True:
        vars_data = safe_api_get(
            wcapi, 
            f"products/{parent_prod['id']}/variations", 
            params={"per_page": 100, "page": var_page}
        )
        
        if not vars_data:
            break
            
        for var in vars_data:
            # Héritage des données du parent
            var['parent_id'] = parent_prod['id']
            var['parent_name'] = parent_prod['name']
            var['parent_description'] = parent_prod.get('description', '')
            var['categories'] = parent_prod.get('categories', [])
            var['parent_images'] = parent_prod.get('images', [])
            var['parent_attributes'] = parent_prod.get('attributes', [])
            variations_list.append(var)
            
        var_page += 1
        
    return variations_list

def fetch_all_products_with_variations(wcapi):
    """
    Extrait les produits simples ET toutes les variations de chaque produit variable
    de façon optimisée et parallélisée.
    """
    all_items = []
    page = 1
    
    logger.info("Début de la récupération des produits WooCommerce...")
    
    while True:
        products = safe_api_get(wcapi, "products", params={"per_page": 100, "page": page})
        
        if not products:
            break
            
        logger.info(f"-> Page {page} récupérée ({len(products)} produits)")
        
        variable_products = [p for p in products if p.get("type") == "variable"]
        simple_products = [p for p in products if p.get("type") != "variable"]
        
        # 1. Ajout direct des produits simples
        all_items.extend(simple_products)
        
        # 2. Récupération parallèle des variations pour les produits variables
        if variable_products:
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = [
                    executor.submit(fetch_variations_for_product, wcapi, prod) 
                    for prod in variable_products
                ]
                
                for future in as_completed(futures):
                    try:
                        variations = future.result()
                        all_items.extend(variations)
                    except Exception as e:
                        logger.error(f"Erreur lors du traitement d'une variation : {e}")
                        
        page += 1
        
    logger.info(f"Extraction terminée : {len(all_items)} articles/déclinaisons récupérés au total.")
    return all_items
