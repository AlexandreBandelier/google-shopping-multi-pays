import os
import requests
from dict2xml import dict2xml
from feed_processor import enrich_and_clean_product

def fetch_all_woocommerce_products(url, key, secret):
    """
    Récupère la totalité du catalogue WooCommerce par pagination de 100 produits.
    """
    products = []
    page = 1
    per_page = 100
    
    api_url = f"{url.rstrip('/')}/wp-json/wc/v3/products"
    
    print("Début de l'extraction du catalogue WooCommerce...")
    
    while True:
        params = {
            'per_page': per_page,
            'page': page,
            'status': 'publish'  # Uniquement les produits publiés
        }
        
        response = requests.get(api_url, auth=(key, secret), params=params)
        
        if response.status_code != 200:
            raise Exception(f"Erreur API WooCommerce (Code {response.status_code}): {response.text}")
            
        data = response.json()
        
        if not data:
            break  # Plus de produits à récupérer
            
        products.extend(data)
        print(f"  -> Page {page} récupérée ({len(products)} produits au total)")
        page += 1
        
    print(f"Extraction terminée : {len(products)} produits récupérés au total.")
    return products


def generate_rss_xml(cleaned_products):
    """
    Convertit la liste des produits nettoyés au format XML standard Google Shopping (RSS 2.0).
    """
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

    # Structure XML exigée par Google Merchant Center
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
    # 1. Récupération des secrets d'environnement
    woo_url = os.getenv('WOO_URL')
    woo_key = os.getenv('WOO_KEY')
    woo_secret = os.getenv('WOO_SECRET')

    if not all([woo_url, woo_key, woo_secret]):
        raise ValueError("Erreur : Les variables d'environnement WOO_URL, WOO_KEY et WOO_SECRET doivent être définies.")

    # 2. Récupération des données brutes
    raw_products = fetch_all_woocommerce_products(woo_url, woo_key, woo_secret)

    # 3. Traitement et nettoyage
    print("Nettoyage et enrichissement des données...")
    cleaned_products = [enrich_and_clean_product(p) for p in raw_products]

    # 4. Génération XML
    print("Génération du fichier XML Google Shopping...")
    xml_output = generate_rss_xml(cleaned_products)

    # 5. Écriture dans le fichier physique
    output_filename = "google_shopping_feed.xml"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(xml_output)

    print(f"Succès ! Le fichier '{output_filename}' a été généré avec succès.")


if __name__ == "__main__":
    main()
