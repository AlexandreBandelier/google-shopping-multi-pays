# feed_processor.py
import html
import re

# Table de correspondance Langue -> Nom de Domaine
DOMAIN_MAPPING = {
    'fr_FR': 'https://votre-site.fr',
    'fr_BE': 'https://votre-site.be',
    'de_DE': 'https://votre-site.de',
    'es_ES': 'https://votre-site.es',
    'it_IT': 'https://votre-site.it',
    'nl_NL': 'https://votre-site.nl',
    'da_DK': 'https://votre-site.dk',
    'en_GB': 'https://votre-site.eu',
}

# Table de correspondance Langue -> Devise officielle Google Shopping
CURRENCY_MAPPING = {
    'da_DK': 'DKK',
    'en_GB': 'EUR',  # Ou GBP selon votre ciblage EU
    'fr_FR': 'EUR',
    'fr_BE': 'EUR',
    'de_DE': 'EUR',
    'es_ES': 'EUR',
    'it_IT': 'EUR',
    'nl_NL': 'EUR',
}

# Traduction des étiquettes personnalisées de stock
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


def clean_html(text):
    """Nettoie le HTML et les espaces superflus."""
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', ' ', str(text))
    return " ".join(clean.split())


def fix_url_domain(link, lang):
    """
    Réécrit le nom de domaine racine pour correspondre à la langue et au TLD cible (.de, .es, .dk, etc.).
    """
    if not link:
        return ""
    target_domain = DOMAIN_MAPPING.get(lang)
    if not target_domain:
        return link

    # Remplace le protocole + nom de domaine principal par le domaine cible
    updated_link = re.sub(r'https?://[^/]+', target_domain, link)
    return updated_link


def process_product_item(item, lang="fr_FR"):
    """
    Traite un produit simple ou une variante WooCommerce 
    et extrait toutes les métadonnées pour Google Shopping avec adaptation multi-domaine.
    """
    prod_id = str(item.get('id'))
    parent_id = item.get('parent_id')
    item_group_id = str(parent_id) if parent_id else None

    title = clean_html(item.get('name', ''))
    description = clean_html(item.get('description', ''))
    
    # 1. Correction dynamique du lien selon le domaine du pays cible (.de, .dk, .es...)
    raw_link = item.get('permalink', '')
    link = fix_url_domain(raw_link, lang)

    # --- Images ---
    images = item.get('images', [])
    image_link = images[0].get('src') if images else ""
    additional_images = [img.get('src') for img in images[1:] if img.get('src')]

    # --- Prix et Devise ---
    currency = CURRENCY_MAPPING.get(lang, 'EUR')
    price_val = item.get('price', '0')
    price = f"{price_val} {currency}" if price_val else f"0 {currency}"

    # --- Stock & Availability (Incorpore l'enrichissement de woocommerce_fetcher.py) ---
    stock_status = item.get('stock_status', 'instock')
    
    # Prise en compte prioritaire du statut calculé par woocommerce_fetcher
    availability = item.get('calculated_availability')
    if not availability:
        if stock_status == 'instock':
            availability = 'in_stock'
        elif stock_status in ['onbackorder', 'backorder']:
            availability = 'backorder'
        else:
            availability = 'out_of_stock'

    availability_date = item.get('calculated_availability_date')

    # Custom label de stock traduit selon la langue
    labels_dict = STOCK_LABELS.get(lang, STOCK_LABELS['fr_FR'])
    if stock_status == 'instock':
        custom_stock_label = labels_dict['instock']
    elif stock_status in ['onbackorder', 'backorder']:
        custom_stock_label = labels_dict['onbackorder']
    else:
        custom_stock_label = labels_dict['outofstock']

    # --- Identification MPN / Brand / SKU ---
    sku = item.get('sku') or prod_id
    mpn = str(sku)
    brand = "VotreMarque"  # Remplacez par votre marque officielle

    # --- Attributs & Déclinaisons (Taille, Couleur, Matière) ---
    attributes = item.get('attributes', [])
    size = None
    color = item.get('extracted_color')  # Priorité à la couleur extraite par woocommerce_fetcher
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
        
        # Identification MPN / Brand
        'identifier_exists': 'no',
        'mpn': mpn,
        'brand': brand,

        # Custom Labels Google Ads (custom_label_0 à 4)
        'custom_label_0': gamme or '',
        'custom_label_1': discipline or '',
        'custom_label_2': public or '',
        'custom_label_3': personnalisation or '',
        'custom_label_4': custom_stock_label 
    }
