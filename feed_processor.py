# feed_processor.py
from datetime import datetime, timedelta
import html
import re

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

KEYWORD_MAPPING = {
    'taille': 'size', 'size': 'size', 'groesse': 'size', 'grösse': 'size', 'pa_taille': 'size', 'pa_size': 'size',
    'couleur': 'color', 'color': 'color', 'farbe': 'color', 'pa_couleur': 'color', 'pa_color': 'color', 'pa_farbe': 'color',
    'matière': 'material', 'matiere': 'material', 'tissu': 'material', 'material': 'material',
    'discipline': 'discipline', 'usage': 'discipline',
    'gamme': 'gamme',
    'public': 'public', 'niveau': 'public',
    'personnalisation': 'personnalisation', 'broderie': 'personnalisation',
}

# Optimisation 1 : Pré-compilation stricte pour des performances maximales
CLEAN_HTML_REGEX = re.compile(r'<[^>]+>')
WEIGHT_REGEX = re.compile(r'^\d+(\.\d+)?')
# Regex optimisée pour détecter rapidement les titres invalides de type "statut de stock"
INVALID_TITLE_REGEX = re.compile(
    r'(habituellement expédié|en stock|sur commande|rupture|auf lager|in stock|out of stock|bajo pedido)',
    re.IGNORECASE
)

def clean_html(text):
    """Optimisation 2 : Echappement uniquement si le texte contient du HTML."""
    if not text: return ""
    text_str = str(text)
    if '<' in text_str or '&' in text_str:
        return " ".join(CLEAN_HTML_REGEX.sub(' ', html.unescape(text_str)).split())
    return " ".join(text_str.split())

def is_invalid_title(title_text):
    if not title_text:
        return True
    return bool(INVALID_TITLE_REGEX.search(title_text))

def extract_clean_title(item):
    """Extrait le titre du produit en priorité depuis le parent pour homogénéiser la série."""
    parent_name = item.get('parent_name')
    if parent_name:
        cleaned_parent = clean_html(parent_name)
        if cleaned_parent and not is_invalid_title(cleaned_parent):
            return cleaned_parent

    # L'utilisation d'un générateur retarde l'évaluation (Lazy evaluation) pour gagner en vitesse
    candidates = (
        item.get('name'),
        item.get('title'),
        item.get('post_title'),
        item.get('slug', '').replace('-', ' ').title() if item.get('slug') else None
    )
    
    for candidate in candidates:
        if candidate and isinstance(candidate, str):
            cleaned = clean_html(candidate)
            if cleaned and not is_invalid_title(cleaned):
                return cleaned
                
    raw_name = item.get('name') or item.get('title') or f"Produit {item.get('id')}"
    return clean_html(raw_name)

def format_shipping_weight(raw_weight):
    if not raw_weight:
        return ""
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
    """Optimisation 3 : Résolution rapide de la marque et sortie prématurée."""
    for attr in item.get('attributes', []):
        name = str(attr.get('name', '')).lower()
        if 'brand' in name or 'marque' in name:
            options = attr.get('options')
            if options and isinstance(options, list):
                return options[0]
            return attr.get('option', '')
            
    brands = item.get('brands')
    if brands and isinstance(brands, list):
        return brands[0].get('name', '')
    return ""

def resolve_availability(stock_status, calculated_availability, calculated_date):
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
    data = {
        'size': None, 'color': color, 'material': None,
        'discipline': None, 'gamme': None, 'public': None,
        'personnalisation': None
    }

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

    lang_fallbacks = FALLBACK_VALUES.get(lang, FALLBACK_VALUES['fr_FR'])
    if not data['color']:
        data['color'] = lang_fallbacks['color']
    if not data['size']:
        data['size'] = lang_fallbacks['size']

    return data

def process_product_item(item, lang="fr_FR"):
    prod_id = str(item.get('id'))
    title = extract_clean_title(item)  
    description = clean_html(item.get('description') or item.get('short_description') or "")

    shipping_weight = format_shipping_weight(item.get('weight'))

    availability, availability_date = resolve_availability(
        item.get('stock_status', 'instock'), 
        item.get('calculated_availability'), 
        item.get('calculated_availability_date')
    )

    labels = STOCK_LABELS.get(lang, STOCK_LABELS['fr_FR'])
    stock_status = item.get('stock_status', 'instock')
    label_key = 'onbackorder' if stock_status in ['onbackorder', 'backorder'] else ('instock' if stock_status == 'instock' else 'outofstock')

    attr_data = get_attribute_data(item.get('attributes', []), item.get('extracted_color'), lang)
    brand = extract_brand(item)

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
