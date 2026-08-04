# feed_processor.py

def enrich_and_clean_product(product):
    """
    Nettoie et enrichit les données d'un produit WooCommerce 
    selon les règles métier et exigences de Google Merchant Center.
    """
    title = product.get('name', '')
    title_lower = title.lower()
    categories = [cat['name'].lower() for cat in product.get('categories', [])]
    cat_str = " ".join(categories)

    # 1. GENDER (Genre)
    # Règle : 'female' si contient 'femme' ou 'féminin', sinon 'unisex'
    if 'femme' in title_lower or 'féminin' in title_lower or 'femme' in cat_str or 'féminin' in cat_str:
        gender = 'female'
    else:
        gender = 'unisex'

    # 2. AGE GROUP (Tranche d'âge)
    # Règle : Vérification catégorie d'abord, puis liste de mots-clés dans le titre
    age_keywords = [
        'enfant', 'enfants', 'junior', 'kodomo', 'kids', 'baby', 
        'pupille', 'poussin', 'minime', 'taille enfant', 'kimono enfant', 
        '100cm', '110cm', '120cm', '130cm', '140cm', '150cm'
    ]
    
    if 'enfant' in cat_str or 'enfants' in cat_str:
        age_group = 'kids'
    elif any(kw in title_lower for kw in age_keywords):
        age_group = 'kids'
    else:
        age_group = 'adult'

    # 3. SIZE & COLOR (Taille et Couleur)
    # Règle : Séparation stricte taille/couleur. Fallback 'one_size' si absente.
    size = None
    color = None

    for attr in product.get('attributes', []):
        attr_name = attr.get('name', '').lower()
        options = attr.get('options', [])
        
        if options:
            if 'taille' in attr_name or 'size' in attr_name:
                size = options[0]
            elif 'couleur' in attr_name or 'color' in attr_name:
                color = options[0]

    # Sécurité si aucune taille valide n'a été extraite via l'API
    if not size:
        size = 'one_size'

    # 4. STRUCTURATION DU PRODUIT
    return {
        'id': str(product['id']),
        'title': title,
        'description': product.get('description', ''),
        'link': product.get('permalink', ''),
        'image_link': product['images'][0]['src'] if product.get('images') else '',
        'availability': 'in_stock' if product.get('stock_status') == 'instock' else 'out_of_stock',
        'price': f"{product.get('price', '0.00')} EUR",
        'gender': gender,
        'age_group': age_group,
        'size': size,
        'color': color,
        'identifier_exists': 'no' if not product.get('sku') else 'yes'
    }
