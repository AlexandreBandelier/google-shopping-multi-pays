# feed_processor.py
import re
import html

# CONSTANTES (Chargées 1 seule fois en mémoire)
AGE_KEYWORDS = [
    'enfant', 'enfants', 'junior', 'kodomo', 'kids', 'baby', 
    'pupille', 'poussin', 'minime', 'taille enfant', 'kimono enfant', 
    '100cm', '110cm', '120cm', '130cm', '140cm', '150cm'
]

# Pattern Regex compilé avec bordures de mots (\b) pour éviter les faux positifs
AGE_PATTERN = re.compile(r'\b(' + '|'.join(re.escape(kw) for kw in AGE_KEYWORDS) + r')\b', re.IGNORECASE)
GENDER_PATTERN = re.compile(r'\b(femme|féminin|women|ladies)\b', re.IGNORECASE)

def clean_text(text):
    """Supprime les balises HTML et décode les entités XML/HTML."""
    if not text:
        return ''
    # 1. Supprime les balises HTML <...>
    text_no_html = re.sub(r'<[^>]+>', ' ', text)
    # 2. Décode les entités (ex: &amp; -> &)
    decoded_text = html.unescape(text_no_html)
    # 3. Nettoie les espaces multiples
    return ' '.join(decoded_text.split())

def enrich_and_clean_product(product):
    """
    Nettoie et enrichit les données d'un produit WooCommerce 
    selon les règles métier et exigences de Google Merchant Center.
    """
    raw_title = product.get('name', '')
    title = clean_text(raw_title)
    description = clean_text(product.get('description', ''))
    
    categories = [cat['name'] for cat in product.get('categories', [])]
    cat_str = " ".join(categories)
    full_text_search = f"{title} {cat_str}"

    # OPTIMISATION 1 : GENDER (Détection Regex exacte)
    if GENDER_PATTERN.search(full_text_search):
        gender = 'female'
    else:
        gender = 'unisex'

    # OPTIMISATION 2 : AGE GROUP (Mot exact Regex & Catégories)
    cat_lower = cat_str.lower()
    if 'enfant' in cat_lower or 'enfants' in cat_lower:
        age_group = 'kids'
    elif AGE_PATTERN.search(title):
        age_group = 'kids'
    else:
        age_group = 'adult'

    # 3. SIZE & COLOR (Taille et Couleur)
    size = None
    color = None

    for attr in product.get('attributes', []):
        attr_name = attr.get('name', '').lower()
        options = attr.get('options', [])
        
        if options:
            clean_option = clean_text(options[0])
            if 'taille' in attr_name or 'size' in attr_name:
                size = clean_option
            elif 'couleur' in attr_name or 'color' in attr_name:
                color = clean_option

    # Sécurité fallback
    if not size:
        size = 'one_size'

    # OPTIMISATION 3 : STRUCTURATION ROBUSTE (Description & Image)
    images = product.get('images', [])
    image_link = images[0]['src'] if images and isinstance(images, list) else ''

    return {
        'id': str(product['id']),
        'title': title,
        'description': description if description else title, # Fallback sur le titre si desc vide
        'link': product.get('permalink', ''),
        'image_link': image_link,
        'availability': 'in_stock' if product.get('stock_status') == 'instock' else 'out_of_stock',
        'price': f"{product.get('price', '0.00')} EUR",
        'gender': gender,
        'age_group': age_group,
        'size': size,
        'color': color,
        'identifier_exists': 'no' if not product.get('sku') else 'yes'
    }
