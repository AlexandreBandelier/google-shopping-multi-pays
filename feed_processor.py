# feed_processor.py
from datetime import datetime, timedelta
import html
import re

# Table de correspondance Langue -> Nom de Domaine officiel
DOMAIN_MAPPING = {
    'fr_FR': 'https://karate-gi.fr', 'fr_BE': 'https://karate-gi.be',
    'de_DE': 'https://karate-gi.de', 'es_ES': 'https://karate-gi.es',
    'it_IT': 'https://karate-gi.it', 'nl_NL': 'https://karate-gi.nl',
    'da_DK': 'https://karate-gi.dk', 'en_GB': 'https://karate-gi.eu',
}

CURRENCY_MAPPING = {
    'da_DK': 'DKK', 'en_GB': 'EUR', 'fr_FR': 'EUR',
    'fr_BE': 'EUR', 'de_DE': 'EUR', 'es_ES': 'EUR',
    'it_IT': 'EUR', 'nl_NL': 'EUR',
}

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

# Valeurs de secours (fallbacks) traduites selon la langue cible
FALLBACK_VALUES = {
    'fr_FR': {'color': 'Blanc', 'size': 'Taille Unique'},
    'fr_BE': {'color': 'Blanc', 'size': 'Taille Unique'},
    'de_DE': {'color': 'Weiß', 'size': 'Einheitsgröße'},
    'es_ES': {'color': 'Blanco', 'size': 'Talla Única'},
    'it_IT': {'color': 'Bianco', 'size': 'Taglia Unica'},
    'nl_NL': {'color': 'Wit', 'size': 'Eén maat'},
    'da_DK': {'color': 'Hvid', 'size': 'One Size'},
    'en_GB': {'color': 'White', 'size': 'One Size'},
}

# Lookup table d'attributs pour une recherche directe et rapide O(1)
KEYWORD_MAPPING = {
    # Taille
    'taille': 'size', 'size': 'size', 'groesse': 'size', 'grösse': 'size', 'pa_taille': 'size', 'pa_size': 'size',
    # Couleur
    'couleur': 'color', 'color': 'color', 'farbe': 'color', 'pa_couleur': 'color', 'pa_color': 'color', 'pa_farbe': 'color',
    # Matière
    'matière': 'material', 'matiere': 'material', 'tissu': 'material', 'material': 'material',
    # Discipline
    'discipline': 'discipline', 'usage': 'discipline',
    # Autres
    'gamme': 'gamme',
    'public': 'public', 'niveau': 'public',
    'personnalisation': 'personnalisation', 'broderie': 'personnalisation',
}

# --- Optimisation 1 : Compilation préalable des regex et mots-clés parasites en set ---
CLEAN_HTML_REGEX = re.compile(r'<[^>]+>')
WEIGHT_REGEX = re.compile(r'^\d+(\.\d+)?')
INVALID_TITLE_KEYWORDS = {
    'habituellement expédié', 'en stock', 'sur commande', 'rupture', 
    'auf lager', 'in stock', 'out of stock', 'bajo pedido'
}

def clean_html(text):
    if not text: return ""
    return " ".join(CLEAN_HTML_REGEX.sub(' ', html.unescape(str(text))).split())

def is_invalid_title(title_text):
    """Détecte si un titre est en réalité une phrase de stock (Recherche O(N) optimisée via any)."""
    if not title_text:
        return True
    low_text = title_text.lower()
    return any(keyword in low_text for keyword in INVALID_TITLE_KEYWORDS)

def extract_clean_title(item):
    """Extrait le vrai titre du produit en évitant les textes parasites de stock."""
    # Ordre de priorité des clés WooCommerce pour le titre
    candidates = [
        item.get('name'),
        item.get('title'),
        item.get('post_title'),
        item.get('slug', '').replace('-', ' ').title() if item.get('slug') else None
    ]
    
    for candidate in candidates:
        if candidate and isinstance(candidate, str):
            cleaned = clean_html(candidate)
            if cleaned and not is_invalid_title(cleaned):
                return cleaned
                
    # Fallback ultime (conserve le comportement par défaut)
    raw_name = item.get('name') or item.get('title') or f"Produit {item.get('id')}"
    return clean_html(raw_name)

def format_shipping_weight(raw_weight):
    """Assainit la valeur numérique du poids avant d'ajouter l'unité kg."""
    if not raw_weight:
        return ""
    # Optimisation 2 : Remplacement optimisé et utilisation du regex pré-compilé
    clean_val = str(raw_weight).replace(',', '.').strip()
    match = WEIGHT_REGEX.search(clean_val)
    if match:
        weight_num = float(match.group(0))
        if weight_num > 0:
            return f"{weight_num} kg"
    return ""

def get_exact_product_url(item):
    return item.get('permalink', '').strip() or item.get('guid', {}).get('rendered', '')

def extract_brand(item):
    for attr in item.get('attributes', []):
        if 'brand' in str(attr.get('name', '')).lower() or 'marque' in str(attr.get('name', '')).lower():
            return attr.get('options', [None])[0] or attr.get('option', '')
    brands = item.get('brands', [])
    return brands[0].get('name', '') if isinstance(brands, list) and brands else ""

def resolve_availability(stock_status, calculated_availability, calculated_date):
    """Centralisation de la logique de stock et de la date de réassort (J+15)."""
    if calculated_availability:
        availability = calculated_availability
    else:
        status_map = {'instock': 'in_stock', 'onbackorder': 'backorder', 'backorder': 'backorder'}
        availability = status_map.get(stock_status, 'out_of_stock')

    availability_date = calculated_date
    if availability in ['backorder', 'preorder'] and not availability_date:
        availability_date = (datetime.now() + timedelta(days=15)).strftime("%Y-%m-%dT00:00:00+0200")

    return availability, availability_date

def get_attribute_data(attributes, color, lang="fr_FR"):
    """Extraction optimisée des attributs avec fallbacks traduits."""
    data = {
        'size': None, 'color': color, 'material': None,
        'discipline': None, 'gamme': None, 'public': None,
        'personnalisation': None
    }

    # Optimisation 3 : Éviter l'évaluation de chaine vide multiple dans la boucle attributs
    for attr in attributes:
        name_raw = attr.get('name')
        if not name_raw: continue
        name = str(name_raw).lower().strip()
        
        val = attr.get('option') or (attr.get('options')[0] if attr.get('options') else '')

        if not val:
            continue

        for keyword, target_key in KEYWORD_MAPPING.items():
            if keyword in name and not data[target_key]:
                data[target_key] = val
                break

    # Valeurs de secours dynamiques selon la langue
    lang_fallbacks = FALLBACK_VALUES.get(lang, FALLBACK_VALUES['fr_FR'])
    if not data['color']:
        data['color'] = lang_fallbacks['color']
    if not data['size']:
        data['size'] = lang_fallbacks['size']

    return data

def process_product_item(item, lang="fr_FR"):
    # Données de base
    prod_id = str(item.get('id'))
    title = extract_clean_title(item)  # Application du nettoyage de titre
    description = clean_html(item.get('description') or item.get('short_description') or "")

    # Poids pour la livraison nettoyé et formaté
    shipping_weight = format_shipping_weight(item.get('weight'))

    # Stock et Disponibilité
    availability, availability_date = resolve_availability(
        item.get('stock_status', 'instock'), 
        item.get('calculated_availability'), 
        item.get('calculated_availability_date')
    )

    # Mapping direct des labels de stock
    labels = STOCK_LABELS.get(lang, STOCK_LABELS['fr_FR'])
    stock_status = item.get('stock_status', 'instock')
    label_key = 'onbackorder' if stock_status in ['onbackorder', 'backorder'] else ('instock' if stock_status == 'instock' else 'outofstock')

    # Attributs avec support de la langue pour les fallbacks
    attr_data = get_attribute_data(item.get('attributes', []), item.get('extracted_color'), lang)
    brand = extract_brand(item)

    # Extraction sécurisée des images (évite IndexError si la liste est vide)
    images = item.get('images', [])
    image_link = images[0].get('src', '') if images and isinstance(images, list) else ''
    additional_images = [img.get('src') for img in images[1:] if isinstance(img, dict) and img.get('src')] if len(images) > 1 else []

    return {
        'id': prod_id,
        'item_group_id': str(item.get('parent_id')) if item.get('parent_id') else None,
        'title': title, 'description': description,
        'link': get_exact_product_url(item),
        'image_link': image_link,
        'additional_images': additional_images,
        'availability': availability,
        'availability_date': availability_date,
        'price': f"{item.get('price', '0')} {CURRENCY_MAPPING.get(lang, 'EUR')}",
        'shipping_weight': shipping_weight,
        **attr_data,
        'gender': 'unisex', 'age_group': 'adult',
        'identifier_exists': 'yes' if brand else 'no',
        'mpn': str(item.get('sku') or prod_id),
        'brand': brand,
        'custom_label_0': attr_data['gamme'] or '',
        'custom_label_1': attr_data['discipline'] or '',
        'custom_label_2': attr_data['public'] or '',
        'custom_label_3': attr_data['personnalisation'] or '',
        'custom_label_4': labels[label_key]
    }
