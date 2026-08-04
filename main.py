# main.py
import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dict2xml import dict2xml

from feed_processor import enrich_and_clean_product
from gdrive_uploader import upload_feed_to_gdrive


def create_resilient_session():
    """Crée une session HTTP avec retries automatiques et réutilisation des connexions."""
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1,  # Attend 1s, 2s, 4s, 8s... entre chaque essai
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def fetch_all_woocommerce_products(url, key, secret):
    """
    Récupère la totalité du catalogue WooCommerce par pagination.
    Optimisé via une session persistante et un filtrage strict des champs (_fields).
    """
    products = []
    page = 1
    per_page = 100
    api_url = f"{url.rstrip('/')}/wp-json/wc/v3/products"
    
    session = create_resilient_session()

    # 1. OPTIMISATION : Ne demander à l'API que les champs indispensables
    fields_needed = [
        "id", "name", "description", "permalink", "images",
        "stock_status", "price", "categories", "attributes", "sku"
    ]

    print("Début de l'extraction du catalogue WooCommerce...")

    while True:
        params = {
            'per_page': per_page,
            'page': page,
            'status': 'publish',
            '_fields': ",".join(fields_needed)  # Réduit considérablement le poids du JSON
        }
        
        # 2. OPTIMISATION : Utilisation de la session résiliente
        response = session.get(api_url, auth=(key, secret), params=params, timeout=30)
        
        if response.status_code != 200:
            raise Exception(f"Erreur API WooCommerce (Code {response.status_code}): {response.text}")
            
        data = response.json()
        
        if not data:
            break  # Fin de la pagination
            
        products.extend(data)
        print(f"  -> Page {page} récupérée ({len(products)} produits au total)")
        page += 1
        
    print(f"Extraction terminée : {len(products)} produits récupérés au total.")
    return products


def generate_rss_xml(cleaned_products):
    """Convertit la liste des produits nettoyés au format XML standard Google Shopping (RSS 2.0)."""
    items = []
    for prod in cleaned_products:
        item = {
            'g:id': prod['id'],
            'title': prod['title'],
            'description': prod['description'],
            'link': prod['link'],
            'g:image_link': prod['image_link'],
            'g:availability': prod['availability'],
            'g:price': prod['price'],
            'g:gender': prod['gender'],
            'g:age_group': prod['age_group'],
            'g:size': prod['size'],
            'g:identifier_exists': prod['identifier_exists']
        }
        if prod.get('color'):
            item['g:color'] = prod['color']
            
        items.append(item)

    xml_structure = {
        'rss': {
            '@version': '2.0',
            '@xmlns:g': 'http://base.google.com/ns/1.0',
            'channel': {
                'title': 'Flux Produits WooCommerce',
                'link': os.getenv('WOO_URL', ''),
                'description': 'Flux automatique enrichi via Python & GitHub Actions',
                'item': items
            }
        }
    }
    
    return dict2xml(xml_structure)


def main():
    # Récupération des secrets d'environnement
    woo_url = os.getenv('WOO_URL')
    woo_key = os.getenv('WOO_KEY')
    woo_secret = os.getenv('WOO_SECRET')
    gdrive_folder_id = os.getenv('GDRIVE_FOLDER_ID')
    gdrive_json = os.getenv('GDRIVE_SERVICE_ACCOUNT_JSON')

    if not all([woo_url, woo_key, woo_secret]):
        raise ValueError("Erreur : Secrets WooCommerce (WOO_URL, WOO_KEY, WOO_SECRET) manquants.")

    # 1. Extraction des données WooCommerce
    raw_products = fetch_all_woocommerce_products(woo_url, woo_key, woo_secret)

    # 2. Nettoyage et enrichissement des données
    print("Nettoyage et enrichissement des données...")
    cleaned_products = [enrich_and_clean_product(p) for p in raw_products]

    # 3. Génération XML
    print("Génération du fichier XML Google Shopping...")
    xml_output = generate_rss_xml(cleaned_products)

    output_filename = "google_shopping_feed.xml"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(xml_output)

    print(f"Fichier local '{output_filename}' généré avec succès.")

    # 3. OPTIMISATION : Téléversement Google Drive automatique sécurisé
    if gdrive_folder_id and gdrive_json:
        print("Envoi du fichier vers Google Drive...")
        upload_feed_to_gdrive(output_filename, gdrive_folder_id, gdrive_json)
    else:
        print("Secrets Google Drive non détectés. Étape de téléversement ignorée.")

    print("Pipeline exécuté avec succès !")


if __name__ == "__main__":
    main()
