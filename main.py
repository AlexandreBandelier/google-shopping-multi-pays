# main.py
import io
import json
import logging
import os

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from woocommerce import API

from feed_processor import process_product_item
from reviews_fetcher import fetch_all_product_reviews, generate_reviews_xml
from woocommerce_fetcher import fetch_all_products_with_variations

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURATION GLOBALE DES MULTI-DOMAINES ET FLUX ---
DOMAIN_CONFIG = {
    "fr_FR": {"domain": "https://karate-gi.fr", "file": "Shopping Graph_feed.xml"},
    "fr_BE": {"domain": "https://karate-gi.be", "file": "Shopping Graph_feed_BE.xml"},
    "es_ES": {"domain": "https://karate-gi.es", "file": "Shopping Graph_feed_ES.xml"},
    "de_DE": {"domain": "https://karate-gi.de", "file": "Shopping Graph_feed_DE.xml"},
    "it_IT": {"domain": "https://karate-gi.it", "file": "Shopping Graph_feed_IT.xml"},
    "nl_NL": {"domain": "https://karate-gi.nl", "file": "Shopping Graph_feed_NL.xml"},
    "da_DK": {"domain": "https://karate-gi.dk", "file": "Shopping Graph_feed_DK.xml"},
    "en_GB": {"domain": "https://karate-gi.eu", "file": "Shopping Graph_feed_EU.xml"},
}


def cdata(value):
    """Encapsule une valeur dans un bloc CDATA sécurisé en nettoyant la fermeture de balise."""
    if not value:
        return ""
    safe_val = str(value).replace("]]>", "]]&gt;")
    return f"<![CDATA[{safe_val}]]>"


def generate_rss_xml(cleaned_products, lang="fr_FR"):
    """
    Génère un flux XML Google Shopping RSS 2.0 complet et optimisé.
    Utilise le domaine spécifique à la langue configuré dans DOMAIN_CONFIG.
    """
    domain_info = DOMAIN_CONFIG.get(lang, {"domain": os.getenv("WOO_URL", "https://karate-gi.fr")})
    channel_link = domain_info["domain"]

    buffer = io.StringIO()

    # En-tête XML standardisé Google Shopping
    buffer.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    buffer.write('<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">\n')
    buffer.write("  <channel>\n")
    buffer.write(f"    <title>Flux Produits WooCommerce - {lang}</title>\n")
    buffer.write(f"    <link>{channel_link}</link>\n")
    buffer.write(
        "    <description>Flux automatique avec déclinaisons et attributs de"
        " personnalisation</description>\n"
    )

    # Mappage des balises optionnelles standards
    optional_tags = [
        ("g:size", "size", True),
        ("g:color", "color", True),
        ("g:material", "material", True),
        ("g:shipping_weight", "shipping_weight", False),
        ("g:product_type", "product_type", True),
    ]

    for prod in cleaned_products:
        buffer.write("      <item>\n")
        buffer.write(f'        <g:id>{prod["id"]}</g:id>\n')

        if prod.get("item_group_id"):
            buffer.write(
                f'        <g:item_group_id>{prod["item_group_id"]}</g:item_group_id>\n'
            )

        buffer.write(f'        <title>{cdata(prod.get("title"))}</title>\n')
        buffer.write(
            f'        <description>{cdata(prod.get("description"))}</description>\n'
        )
        buffer.write(f'        <link>{cdata(prod.get("link"))}</link>\n')
        buffer.write(
            f'        <g:image_link>{cdata(prod.get("image_link"))}</g:image_link>\n'
        )

        # Galerie d'images secondaires
        for add_img in prod.get("additional_images", []):
            buffer.write(
                f'        <g:additional_image_link>{cdata(add_img)}</g:additional_image_link>\n'
            )

        # Statut de disponibilité
        availability = prod.get("availability", "in stock")
        buffer.write(f"        <g:availability>{availability}</g:availability>\n")

        if availability == "backorder" and prod.get("availability_date"):
            buffer.write(
                f'        <g:availability_date>{prod.get("availability_date")}</g:availability_date>\n'
            )

        buffer.write(f'        <g:price>{prod.get("price", "0 EUR")}</g:price>\n')
        buffer.write(f'        <g:gender>{prod.get("gender", "unisex")}</g:gender>\n')
        buffer.write(f'        <g:age_group>{prod.get("age_group", "adult")}</g:age_group>\n')
        buffer.write(
            f'        <g:identifier_exists>{prod.get("identifier_exists", "no")}</g:identifier_exists>\n'
        )

        # Balises MPN et Marque
        if prod.get("mpn"):
            buffer.write(f'        <g:mpn>{cdata(prod.get("mpn"))}</g:mpn>\n')
        if prod.get("brand"):
            buffer.write(f'        <g:brand>{cdata(prod.get("brand"))}</g:brand>\n')

        # Attributs optionnels standards
        for xml_tag, key, use_cdata in optional_tags:
            val = prod.get(key)
            if val:
                formatted_val = cdata(val) if use_cdata else val
                buffer.write(f"        <{xml_tag}>{formatted_val}</{xml_tag}>\n")

        # Custom Labels Google Ads (custom_label_0 à 4)
        for i in range(5):
            val = prod.get(f"custom_label_{i}")
            if val:
                buffer.write(
                    f"        <g:custom_label_{i}>{cdata(val)}</g:custom_label_{i}>\n"
                )

        buffer.write("      </item>\n")

    buffer.write("  </channel>\n")
    buffer.write("</rss>")

    xml_content = buffer.getvalue()
    buffer.close()
    return xml_content


def upload_to_drive(xml_content, folder_id, target_filename="Shopping Graph_feed.xml"):
    """Téléverse ou met à jour un fichier XML spécifique sur Google Drive."""
    credentials_json = os.getenv("GDRIVE_SERVICE_ACCOUNT_JSON")
    if not credentials_json:
        raise ValueError("Secret GDRIVE_SERVICE_ACCOUNT_JSON manquant.")

    info = json.loads(credentials_json)
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build("drive", "v3", credentials=creds)

    query = (
        f"'{folder_id}' in parents and name = '{target_filename}' and trashed = false"
    )
    response = (
        service.files()
        .list(q=query, spaces="drive", fields="files(id, name)")
        .execute()
    )
    files = response.get("files", [])

    fh = io.BytesIO(xml_content.encode("utf-8"))
    media = MediaIoBaseUpload(fh, mimetype="application/xml", resumable=True)

    if files:
        file_id = files[0]["id"]
        logger.info(
            f"Mise à jour du fichier existant sur Google Drive ({target_filename} - ID: {file_id})..."
        )
        service.files().update(fileId=file_id, media_body=media).execute()
    else:
        logger.info(
            f"Création d'un nouveau fichier sur Google Drive ({target_filename})..."
        )
        file_metadata = {"name": target_filename, "parents": [folder_id]}
        service.files().create(
            body=file_metadata, media_body=media, fields="id"
        ).execute()

    logger.info(f"Fichier {target_filename} mis à jour avec succès sur Google Drive.")


def main():
    woo_url = os.getenv("WOO_URL")
    woo_ck = os.getenv("WOO_KEY")
    woo_cs = os.getenv("WOO_SECRET")
    folder_id = os.getenv("GDRIVE_FOLDER_ID")

    target_lang = os.getenv("TARGET_LANG")
    target_file = os.getenv("TARGET_FILE")
    generate_reviews_only = os.getenv("GENERATE_REVIEWS_ONLY")

    missing_vars = [
        var
        for var, val in {
            "WOO_URL": woo_url,
            "WOO_KEY": woo_ck,
            "WOO_SECRET": woo_cs,
            "GDRIVE_FOLDER_ID": folder_id,
        }.items()
        if not val
    ]

    if missing_vars:
        raise ValueError(
            f"Variables d'environnement manquantes : {', '.join(missing_vars)}"
        )

    wcapi = API(
        url=woo_url,
        consumer_key=woo_ck,
        consumer_secret=woo_cs,
        version="wc/v3",
        timeout=60,
    )

    # CAS A : Avis Clients Uniquement
    if generate_reviews_only == "true":
        logger.info("=== Début de l'extraction du flux Avis Clients ===")
        try:
            raw_reviews = fetch_all_product_reviews(wcapi)
            xml_reviews = generate_reviews_xml(raw_reviews, woo_url)
            upload_to_drive(
                xml_reviews, folder_id, target_filename="product_reviews_feed.xml"
            )
        except Exception as e:
            logger.error(f"Erreur lors du traitement des avis clients : {e}")
            raise e
        return

    # CAS B : Job Matrix GitHub Actions (Une langue spécifique)
    if target_lang:
        filename = target_file or DOMAIN_CONFIG.get(target_lang, {}).get("file", "Shopping Graph_feed.xml")
        logger.info(f"=== Début de l'extraction Matrix ({target_lang}) -> {filename} ===")
        try:
            raw_products = fetch_all_products_with_variations(wcapi, lang=target_lang)
            cleaned_products = [
                process_product_item(item, lang=target_lang) for item in raw_products
            ]

            if cleaned_products:
                sample_prod = cleaned_products[0]
                logger.info(
                    f"PERMALINK TEST [{target_lang}] -> ID: {sample_prod.get('id')} |"
                    f" URL: {sample_prod.get('link')}"
                )

            xml_content = generate_rss_xml(cleaned_products, lang=target_lang)
            upload_to_drive(xml_content, folder_id, target_filename=filename)
        except Exception as e:
            logger.error(
                f"Erreur lors de l'extraction pour la langue {target_lang} : {e}"
            )
            raise e
        return

    # CAS C : Exécution globale séquentielle (Toutes les langues configurées)
    logger.info("=== Exécution globale séquentielle (Toutes les langues) ===")
    for lang_code, config in DOMAIN_CONFIG.items():
        filename = config["file"]
        logger.info(f"=== Début de l'extraction pour la langue : {lang_code.upper()} ===")
        try:
            raw_products = fetch_all_products_with_variations(wcapi, lang=lang_code)
            cleaned_products = [
                process_product_item(item, lang=lang_code) for item in raw_products
            ]
            xml_content = generate_rss_xml(cleaned_products, lang=lang_code)
            upload_to_drive(xml_content, folder_id, target_filename=filename)
        except Exception as e:
            logger.error(
                f"Erreur lors du traitement de la langue {lang_code.upper()} : {e}"
            )

    # Extraction & Génération du Flux Avis Clients à la fin du process global
    logger.info("=== Début de l'extraction des avis clients ===")
    try:
        raw_reviews = fetch_all_product_reviews(wcapi)
        xml_reviews = generate_reviews_xml(raw_reviews, woo_url)
        upload_to_drive(
            xml_reviews, folder_id, target_filename="product_reviews_feed.xml"
        )
    except Exception as e:
        logger.error(f"Erreur lors du traitement des avis clients : {e}")


if __name__ == "__main__":
    main()
