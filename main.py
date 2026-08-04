# main.py
import os
import io
import logging
from woocommerce import API
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from woocommerce_fetcher import fetch_all_products_with_variations
from feed_processor import process_product_item

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def cdata(value):
    """Encapsule une valeur dans un bloc CDATA sécurisé en nettoyant la fermeture de balise."""
    if not value:
        return ""
    safe_val = str(value).replace("]]>", "]]&gt;")
    return f"<![CDATA[{safe_val}]]>"

def generate_rss_xml(cleaned_products):
    """
    Génère un flux XML Google Shopping RSS 2.0 complet et optimisé
    pour supporter un grand nombre de déclinaisons sans surcharge mémoire.
    """
    woo_url = os.getenv('WOO_URL', '')
    buffer = io.StringIO()

    # En-tête XML standardisé Google Shopping
    buffer.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    buffer.write('<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">\n')
    buffer.write('  <channel>\n')
    buffer.write('    <title>Flux Produits WooCommerce Enrichi</title>\n')
    buffer.write(f'    <link>{woo_url}</link>\n')
    buffer.write('    <description>Flux automatique avec déclinaisons et attributs de personnalisation</description>\n')

    # Mappage des balises optionnelles (balise XML, clé dictionnaire, utilisation CDATA)
    optional_tags = [
        ('g:size', 'size', True),
        ('g:color', 'color', True),
        ('g:material', 'material', True),
        ('g:shipping_weight', 'shipping_weight', False),
        ('g:product_type', 'product_type', True)
    ]

    for prod in cleaned_products:
        buffer.write('      <item>\n')
        buffer.write(f'        <g:id>{prod["id"]}</g:id>\n')
        
        if prod.get('item_group_id'):
            buffer.write(f'        <g:item_group_id>{prod["item_group_id"]}</g:item_group_id>\n')

        buffer.write(f'        <title>{cdata(prod.get("title"))}</title>\n')
        buffer.write(f'        <description>{cdata(prod.get("description"))}</description>\n')
        buffer.write(f'        <link>{cdata(prod.get("link"))}</link>\n')
        buffer.write(f'        <g:image_link>{cdata(prod.get("image_link"))}</g:image_link>\n')

        # Galerie d'images secondaires
        for add_img in prod.get('additional_images', []):
            buffer.write(f'        <g:additional_image_link>{cdata(add_img)}</g:additional_image_link>\n')

        buffer.write(f'        <g:availability>{prod.get("availability", "out of stock")}</g:availability>\n')
        buffer.write(f'        <g:price>{prod.get("price", "0 EUR")}</g:price>\n')
        buffer.write(f'        <g:gender>{prod.get("gender", "unisex")}</g:gender>\n')
        buffer.write(f'        <g:age_group>{prod.get("age_group", "adult")}</g:age_group>\n')
        buffer.write(f'        <g:identifier_exists>{prod.get("identifier_exists", "no")}</g:identifier_exists>\n')

        # Attributs optionnels standards
        for xml_tag, key, use_cdata in optional_tags:
            val = prod.get(key)
            if val:
                formatted_val = cdata(val) if use_cdata else val
                buffer.write(f'        <{xml_tag}>{formatted_val}</{xml_tag}>\n')

        # Custom Labels Google Ads (custom_label_0 à 4)
        for i in range(5):
            val = prod.get(f'custom_label_{i}')
            if val:
                buffer.write(f'        <g:custom_label_{i}>{cdata(val)}</g:custom_label_{i}>\n')

        buffer.write('      </item>\n')

    buffer.write('  </channel>\n')
    buffer.write('</rss>')

    xml_content = buffer.getvalue()
    buffer.close()
    return xml_content

def upload_to_drive(xml_content, folder_id):
    """Téléverse ou met à jour le fichier XML sur Google Drive."""
    credentials_json = os.getenv("GDRIVE_SERVICE_ACCOUNT_JSON")
    if not credentials_json:
        raise ValueError("Secret GDRIVE_SERVICE_ACCOUNT_JSON manquant.")

    import json
    info = json.loads(credentials_json)
    creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/drive"])
    service = build("drive", "v3", credentials=creds)

    filename = "google_shopping_feed.xml"
    
    # Recherche du fichier existant
    query = f"'{folder_id}' in parents and name = '{filename}' and trashed = false"
    response = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    files = response.get('files', [])

    fh = io.BytesIO(xml_content.encode('utf-8'))
    media = MediaIoBaseUpload(fh, mimetype='application/xml', resumable=True)

    if files:
        file_id = files[0]['id']
        logger.info(f"Mise à jour du fichier existant sur Google Drive (ID: {file_id})...")
        service.files().update(fileId=file_id, media_body=media).execute()
    else:
        logger.info("Création d'un nouveau fichier sur Google Drive...")
        file_metadata = {'name': filename, 'parents': [folder_id]}
        service.files().create(body=file_metadata, media_body=media, fields='id').execute()

    logger.info("Fichier XML mis à jour avec succès sur Google Drive.")

def main():
    woo_url = os.getenv('WOO_URL')
    woo_ck = os.getenv('WOO_CK')
    woo_cs = os.getenv('WOO_CS')
    folder_id = os.getenv('GDRIVE_FOLDER_ID')

    if not all([woo_url, woo_ck, woo_cs, folder_id]):
        raise ValueError("Variables d'environnement WooCommerce ou Drive manquantes.")

    # 1. Initialisation de l'API WooCommerce
    wcapi = API(
        url=woo_url,
        consumer_key=woo_ck,
        consumer_secret=woo_cs,
        version="wc/v3",
        timeout=30
    )

    # 2. Extraction complète (Produits simples + Variations)
    raw_products = fetch_all_products_with_variations(wcapi)

    # 3. Traitement et enrichissement
    cleaned_products = [process_product_item(item) for item in raw_products]

    # 4. Génération XML
    xml_content = generate_rss_xml(cleaned_products)

    # 5. Envoi vers Google Drive
    upload_to_drive(xml_content, folder_id)

if __name__ == "__main__":
    main()
