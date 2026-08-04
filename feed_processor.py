# feed_processor.py
import html
import re

# Configuration centralisée des alias d'attributs (facile à enrichir)
ATTRIBUTE_MAP = {
    'color': ['couleur kimono', 'couleur ceinture', 'couleur', 'color'],
    'size': ['taille kimono', 'taille ceinture', 'taille', 'size'],
    'material': ['tissus kimono', 'tissus ceinture', 'tissu', 'tissus', 'matière', 'matiere', 'material'],
    'gamme': ['gamme', 'range'],
    'work_type': ['type de travail', 'discipline', 'usage'],
    'public': ['public', 'cible'],
    'customization': ['personnalisation', 'customisation', 'broderie'],
    'karate_weight': ['poids karate-gi', 'poids karaté-gi'],
    'gender': ['genre', 'gender', 'sexe'],
    'age_group': ['tranche d\'âge', 'age group', 'age']
}

def clean_html(raw_html):
    """Supprime les balises HTML et décode proprement les entités (ex: &nbsp;, &amp;)."""
    if not raw_html:
        return ""
    text = re.sub(r'<[^>]+>', ' ', raw_html)
    text = html.unescape(text)
    return " ".join(text.split())

def build_attributes_dict(item):
    """Indexe tous les attributs de l'item et du parent en une seule passe."""
    attr_dict = {}
    
    # 1. Attributs du parent
    for attr in item.get('parent_attributes', []):
        name = attr.get('name', '').strip().lower()
        options = attr.get('options', [])
        if options:
            attr_dict[name] = ", ".join(options)
            
    # 2. Attributs de la variation / produit (écrasent le parent si présent)
    for attr in item.get('attributes', []):
        name = attr.get('name', '').strip().lower()
        option = attr.get('option')
        if option:
            attr_dict[name] = option
        elif attr.get('options'):
            attr_dict[name] = ", ".join(attr['options'])
            
    return attr_dict

def extract_attribute_by_keywords(attr_dict, keywords):
    """Recherche ultra-rapide par mot-clé dans la table d'attributs indexée."""
    for attr_name, attr_value in attr_dict.items():
        if any(kw in attr_name for kw in keywords):
            return attr_value
    return ""

def process_product_item(item):
    """Transforme l'objet produit/variation WooCommerce en dictionnaire pour le flux XML."""
    is_variation = 'parent_id' in item
    parent_id = item.get('parent_id')
    
    item_id = str(item['id'])
    base_title = item.get('parent_name') if is_variation else item.get('name', '')
    
    # Gestion des images
    images = item.get('images', [])
    image_link = images[0]['src'] if images else ""
    if not image_link and is_variation and item.get('parent_images'):
        image_link = item['parent_images'][0]['src']
        
    additional_images = [img['src'] for img in images[1:]] if len(images) > 1 else []

    # 1. Indexation unique des attributs
    attr_dict = build_attributes_dict(item)
    
    # 2. Extraction groupée via la carte d'attributs
    extracted = {
        key: extract_attribute_by_keywords(attr_dict, keywords) 
        for key, keywords in ATTRIBUTE_MAP.items()
    }

    # Poids d'expédition
    weight_raw = item.get('weight', '')
    shipping_weight = f"{weight_raw} kg" if weight_raw and weight_raw != "ND" else ""

    # Fil d'ariane Catégories
    categories = item.get('categories', [])
    product_type = " > ".join([cat['name'] for cat in categories]) if categories else ""

    return {
        'id': item_id,
        'item_group_id': str(parent_id) if is_variation else "",
        'title': clean_html(base_title),
        'description': clean_html(item.get('parent_description') if is_variation else item.get('description', '')),
        'link': item.get('permalink', ''),
        'image_link': image_link,
        'additional_images': additional_images,
        'availability': 'in stock' if item.get('stock_status') == 'instock' else 'out of stock',
        'price': f"{item.get('price', '0')} EUR",
        'gender': extracted['gender'] or 'unisex',
        'age_group': extracted['age_group'] or 'adult',
        'size': extracted['size'],
        'color': extracted['color'],
        'material': extracted['material'],
        'shipping_weight': shipping_weight,
        'product_type': product_type,
        
        # Custom Labels Google Ads
        'custom_label_0': extracted['gamme'],
        'custom_label_1': extracted['work_type'],
        'custom_label_2': extracted['public'],
        'custom_label_3': extracted['customization'],
        'custom_label_4': extracted['karate_weight'],
        
        'identifier_exists': 'no'
    }
