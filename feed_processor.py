# feed_processor.py
import html
import re

def clean_html(text):
    """Nettoie le HTML et les espaces superflus."""
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', ' ', str(text))
    return " ".join(clean.split())

def process_product_item(item):
    """
    Traite un produit simple ou une variante WooCommerce 
    et extrait toutes les métadonnées pour Google Shopping.
    """
    prod_id = str(item.get('id'))
    parent_id = item.get('parent_id')
    item_group_id = str(parent_id) if parent_id else None

    title = clean_html(item.get('name', ''))
    description = clean_html(item.get('description', ''))
    link = item.get('permalink', '')
    
    # --- Images ---
    images = item.get('images', [])
    image_link = images[0].get('src') if images else ""
    additional_images = [img.get('src') for img in images[1:] if img.get('src')]

    # --- Prix ---
    price_val = item.get('price', '0')
    price = f"{price_val} EUR" if price_val else "0 EUR"

    # --- Option 3 : Stock & Availability ---
    stock_status = item.get('stock_status', 'instock')
    if stock_status == 'instock':
        availability = 'in_stock'
        custom_stock_label = 'En Stock'
    elif stock_status == 'onbackorder':
        availability = 'backorder'
        custom_stock_label = 'Sur Commande'
    else:
        availability = 'out of stock'
        custom_stock_label = 'Rupture'

    # --- Option 1 : Identification sans GTIN (MPN / Brand / SKU) ---
    sku = item.get('sku') or prod_id  # UGS unique de la variante ou du produit
    mpn = str(sku)
    brand = "VotreMarque"  # Remplacez "VotreMarque" par le nom officiel de votre marque

    # --- Attributs & Déclinaisons (Taille, Couleur, Matière, etc.) ---
    attributes = item.get('attributes', [])
    size = None
    color = None
    material = None
    discipline = None
    gamme = None
    public = None
    personnalisation = None

    for attr in attributes:
        name = attr.get('name', '').lower()
        option = attr.get('option', '')

        if 'taille' in name or 'size' in name:
            size = option
        elif 'couleur' in name or 'color' in name:
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
        'price': price,
        'size': size,
        'color': color,
        'material': material,
        'gender': 'unisex',
        'age_group': 'adult',
        
        # Option 1 : Identification MPN / Brand / GTIN
        'identifier_exists': 'no',
        'mpn': mpn,
        'brand': brand,

        # Custom Labels Google Ads (custom_label_0 à 4)
        'custom_label_0': gamme or '',
        'custom_label_1': discipline or '',
        'custom_label_2': public or '',
        'custom_label_3': personnalisation or '',
        # Option 3 : Segment Stock dans Custom Label 4
        'custom_label_4': custom_stock_label 
    }
