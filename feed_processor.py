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

CLEAN_HTML_REGEX = re.compile(r'<[^>]+>')

def clean_html(text):
    if not text: return ""
    return " ".join(CLEAN_HTML_REGEX.sub(' ', html.unescape(str(text))).split())

def get_exact_product_url(item):
    return item.get('permalink', '').strip() or item.get('guid', {}).get('rendered', '')

def extract_brand(item):
    for attr in item.get('attributes', []):
        if 'brand' in str(attr.get('name', '')).lower() or 'marque' in str(attr.get('name', '')).lower():
            return attr.get('options', [None])[0] or attr.get('option', '')
    brands = item.get('brands', [])
    return brands[0].get('name', '') if isinstance(brands, list) and brands else ""

def resolve_availability(stock_status, calculated_availability, calculated_date):
    """Optimisation 2 : Centralisation de la logique de stock."""
    if calculated_availability:
        availability = calculated_availability
    else:
        status_map = {'instock': 'in_stock', 'onbackorder': 'backorder', 'backorder': 'backorder'}
        availability = status_map.get(stock_status, 'out_of_stock')

    availability_date = calculated_date
    if availability in ['backorder', 'preorder'] and not availability_date:
        availability_date = (datetime.now() + timedelta(days=15)).strftime("%Y-%m-%dT00:00:00+0200")
    
    return availability, availability_date

def get_attribute_data(attributes, color):
    """Optimisation 1 : Helper pour extraire les attributs."""
    data = {'size': None, 'color': color, 'material': None, 'discipline': None, 'gamme': None, 'public': None, 'personnalisation': None}
    
    for attr in attributes:
        name = str(attr.get('name', '')).lower()
        val = attr.get('option', '')
        if 'taille' in name or 'size' in name: data['size'] = val
        elif ('couleur' in name or 'color' in name) and not data['color']: data['color'] = val
        elif 'matière' in name or 'tissu' in name or 'material' in name: data['material'] = val
        elif 'discipline' in name or 'usage' in name: data['discipline'] = val
        elif 'gamme' in name: data['gamme'] = val
        elif 'public' in name or 'niveau' in name: data['public'] = val
        elif 'personnalisation' in name or 'broderie' in name: data['personnalisation'] = val
    return data

def process_product_item(item, lang="fr_FR"):
    # Données de base
    prod_id = str(item.get('id'))
    title = clean_html(item.get('name', ''))
    description = clean_html(item.get('description') or item.get('short_description') or "")
    
    # Stock et Disponibilité
    availability, availability_date = resolve_availability(
        item.get('stock_status', 'instock'), 
        item.get('calculated_availability'), 
        item.get('calculated_availability_date')
    )

    # Optimisation 3 : Mapping direct des labels
    labels = STOCK_LABELS.get(lang, STOCK_LABELS['fr_FR'])
    stock_status = item.get('stock_status', 'instock')
    label_key = 'onbackorder' if stock_status in ['onbackorder', 'backorder'] else ('instock' if stock_status == 'instock' else 'outofstock')
    
    # Attributs
    attr_data = get_attribute_data(item.get('attributes', []), item.get('extracted_color'))
    brand = extract_brand(item)

    return {
        'id': prod_id,
        'item_group_id': str(item.get('parent_id')) if item.get('parent_id') else None,
        'title': title, 'description': description,
        'link': get_exact_product_url(item),
        'image_link': item.get('images', [{}])[0].get('src', ''),
        'additional_images': [img.get('src') for img in item.get('images', [])[1:] if img.get('src')],
        'availability': availability,
        'availability_date': availability_date,
        'price': f"{item.get('price', '0')} {CURRENCY_MAPPING.get(lang, 'EUR')}",
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
