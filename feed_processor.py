# feed_processor.py
import html
import re

# Table de correspondance Langue -> Nom de Domaine officiel
DOMAIN_MAPPING = {
    'fr_FR': 'https://karate-gi.fr',
    'fr_BE': 'https://karate-gi.be',
    'de_DE': 'https://karate-gi.de',
    'es_ES': 'https://karate-gi.es',
    'it_IT': 'https://karate-gi.it',
    'nl_NL': 'https://karate-gi.nl',
    'da_DK': 'https://karate-gi.dk',
    'en_GB': 'https://karate-gi.eu',
}

# Table de correspondance Langue -> Devise officielle Google Shopping
CURRENCY_MAPPING = {
    'da_DK': 'DKK',
    'en_GB': 'EUR',
    'fr_FR': 'EUR',
    'fr_BE': 'EUR',
    'de_DE': 'EUR',
    'es_ES': 'EUR',
    'it_IT': 'EUR',
    'nl_NL': 'EUR',
}

# Traduction des étiquettes personnalisées de stock (Custom Label 4)
STOCK_LABELS = {
    'fr_FR': {'instock': 'En Stock', 'onbackorder': 'Sur Commande', 'outofstock': 'Rupture'},
    'fr_BE': {'instock': 'En Stock', 'onbackorder': 'Sur Commande', 'outofstock': 'Rupture'},
    'de_DE': {'instock': 'Auf Lager', 'onbackorder': 'Nachbestellung', 'outofstock': 'Ausverkauft'},
    'es_ES': {'instock': 'En Stock', 'onbackorder': 'Bajo Pedido', 'outofstock': 'Agotado'},
    'it_IT': {'instock': 'In Stock', 'onbackorder': 'Su Ordinazione', 'outofstock': 'Esaurito'},
    'nl_NL': {'instock': 'Op Voorraad', 'onbackorder': 'Nalevering', 'outofstock': 'Niet op voorraad'},
    'da_DK': {'instock': 'På lager', 'onbackorder': 'Restordre', 'outofstock': 'Udsolgt'},
    'en_GB': {'instock': 'In Stock', 'onbackorder': 'On Backorder', 'outofstock': 'Out of Stock'},
}

CLEAN_HTML_REGEX = re.compile(r'<[^>]+>')


def clean_html(text):
    """Nettoie le HTML, décodes les entités et supprime les espaces superflus."""
    if not text:
        return ""
    text_unescaped = html.unescape(str(text))
    clean = CLEAN_HTML_REGEX.sub(' ', text_unescaped)
    return " ".join(clean.split())


def get_exact_product_url(item):
    """
    Extrait le permalink canonique exact renvoyé directement par l'API du site.
    """
    link = item.get('permalink', '').strip()
    if not link:
        # Fallback au cas où le permalink direct est absent
        link = item.get('guid', {}).get('rendered', '')
    return link


def extract_brand(item):
    """
    Extrait dynamiquement la marque depuis les attributs du produit ou les marques WooCommerce.
    """
    # 1. Inspection des attributs WooCommerce (ex: Marque, Brand, pa_brand)
    attributes = item.get('attributes', [])
    for attr in attributes:
        attr_name = str(attr.get('name', '')).lower()
        if 'brand' in attr_name or 'marque' in attr_name:
            options = attr.get('options', [])
            if options:
                return options[0]
            elif attr.get('option'):
                return attr.get('option')

    # 2. Inspection de la taxonomie 'brands' (extensions WooCommerce Brands)
    brands = item.get('brands', [])
    if brands and isinstance(brands, list):
        return brands[0].get('name', '')

    return ""


def process_product_item(item, lang="fr_FR"):
    """
    Traite un produit simple ou une variante WooCommerce et extrait toutes 
    les métadonnées optimisées pour Google Shopping (Multi-domaine & Multi-langue).
    """
    prod_id = str(item.get('id'))
    parent_id = item.get('parent_id')
    item_group_id = str(parent_id) if parent_id else None

    title = clean_html(item.get('name', ''))
    
    # Optimisation : Fallback sur la description courte si la longue est absente
    raw_desc = item.get('description') or item.get('short_description') or ""
    description = clean_html(raw_desc)
    
    # Récupération directe du permalien brut renvoyé par le domaine natif
    link = get_exact_product_url(item)

    # --- Images ---
    images = item.get('images', [])
    image_link = images[0].get('src') if images else ""
    additional_images = [img.get('src') for img in images[1:] if img.get('src')]

    # --- Prix et Devise ---
    currency = CURRENCY_MAPPING.get(lang, 'EUR')
    price_val = item.get('price', '0')
    price = f"{price_val} {currency}" if price_val else f"0 {currency}"

    # --- Statut de Stock & Disponibilité Google ---
    stock_status = item.get('stock_status', 'instock')
    availability = item.get('calculated_availability')
    
    if not availability:
        if stock_status == 'instock':
            availability = 'in_stock'
        elif stock_status in ['onbackorder', 'backorder']:
            availability = 'backorder'
        else:
            availability = 'out_of_stock'

    availability_date = item.get('calculated_availability_date')

    # Custom Label 4 (Statut de stock traduit)
    labels_dict = STOCK_LABELS.get(lang, STOCK_LABELS['fr_FR'])
    if stock_status == 'instock':
        custom_stock_label = labels_dict['instock']
    elif stock_status in ['onbackorder', 'backorder']:
        custom_stock_label = labels_dict['onbackorder']
    else:
        custom_stock_label = labels_dict['outofstock']

    # --- MPN, SKU & Marque Dynamique ---
    sku = item.get('sku') or prod_id
    mpn = str(sku)
    brand = extract_brand(item)

    # --- Attributs & Déclinaisons ---
    attributes = item.get('attributes', [])
    size = None
    color = item.get('extracted_color')
    material = None
    discipline = None
    gamme = None
    public = None
    personnalisation = None

    for attr in attributes:
        name = str(attr.get('name', '')).lower()
        option = attr.get('option', '')

        if 'taille' in name or 'size' in name:
            size = option
        elif ('couleur' in name or 'color' in name) and not color:
            color = option
        elif 'matière' in name or 'tissu' in name or 'material' in name:
            material = option
        elif 'discipline' in name or 'usage' in name:
            discipline = option
        elif 'gamme' in name:
            gamme = option
        elif 'public' in name or 'niveau' in name:
            public = option
        elif 'personnalisation' in name or 'broderie' in name:
            personnalisation = option

    return {
        'id': prod_id,
        'item_group_id': item_group_id,
        'title': title,
        'description': description,
        'link': link,
        'image_link': image_link,
        'additional_images': additional_images,
        'availability': availability,
        'availability_date': availability_date,
        'price': price,
        'size': size,
        'color': color,
        'material': material,
        'gender': 'unisex',
        'age_group': 'adult',
        
        # Identification du produit
        'identifier_exists': 'yes' if brand else 'no',
        'mpn': mpn,
        'brand': brand,

        # Custom Labels Google Ads
        'custom_label_0': gamme or '',
        'custom_label_1': discipline or '',
        'custom_label_2': public or '',
        'custom_label_3': personnalisation or '',
        'custom_label_4': custom_stock_label 
    }
