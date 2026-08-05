# reviews_fetcher.py
import html
import re
import logging
from datetime import datetime, timezone
from woocommerce_fetcher import safe_api_get

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Regex pré-compilées pour le nettoyage
CLEAN_HTML_REGEX = re.compile(r'<[^>]+>')
EMAIL_REGEX = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
PHONE_REGEX = re.compile(r'(\+?\d{1,3}[-.\s]?)?(\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4}')


def fetch_all_product_reviews(wcapi):
    """
    Extrait l'ensemble des avis produits validés via l'API WooCommerce.
    """
    all_reviews = []
    page = 1

    logger.info("Début de l'extraction des avis produits...")

    while True:
        reviews = safe_api_get(
            wcapi,
            "products/reviews",
            params={"per_page": 100, "page": page, "status": "approved"},
        )

        if not reviews:
            break

        all_reviews.extend(reviews)
        logger.info(f"-> Page {page} d'avis récupérée ({len(reviews)} avis)")
        page += 1

    logger.info(f"Total avis récupérés : {len(all_reviews)}")
    return all_reviews


def format_iso_timestamp(date_string):
    """
    Convertit la date WooCommerce au format ISO 8601 strict (ex: 2026-08-05T10:00:00Z).
    """
    if not date_string:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        clean_date = str(date_string).replace("Z", "")
        dt = datetime.fromisoformat(clean_date)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sanitize_text(text):
    """
    Nettoie le HTML, échappe CDATA et masque les informations personnelles (PII)
    telles que les emails et numéros de téléphone.
    """
    if not text:
        return ""
    
    # Décodage HTML puis suppression des balises
    raw_clean = html.unescape(str(text))
    clean_text = CLEAN_HTML_REGEX.sub(" ", raw_clean)
    
    # Anonymisation des PII (Emails et Téléphones)
    clean_text = EMAIL_REGEX.sub("[email masqué]", clean_text)
    clean_text = PHONE_REGEX.sub("[téléphone masqué]", clean_text)
    
    # Nettoyage pour bloc CDATA
    clean_text = clean_text.replace("]]>", "]]&gt;").strip()
    return clean_text


def generate_reviews_xml(reviews, woo_url):
    """
    Génère le flux XML au format officiel Google Product Reviews (v2.3).
    """
    clean_woo_url = woo_url.rstrip("/")

    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>\n',
        '<feed xmlns:vc="http://www.w3.org/2007/XMLSchema-versioning"\n',
        '      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n',
        '      xsi:noNamespaceSchemaLocation="http://www.google.com/shopping/reviews/schema/product_reviews_schema.xsd">\n',
        "  <version>2.3</version>\n",
        "  <publisher>\n",
        "    <name>Votre Boutique</name>\n",
        f"    <favicon>{clean_woo_url}/favicon.ico</favicon>\n",
        "  </publisher>\n",
        "  <reviews>\n",
    ]

    for rev in reviews:
        review_id = rev.get("id")
        product_id = rev.get("product_id")
        
        # 1. Traitement strict du Rating (1 à 5 obligatoire)
        try:
            rating = int(rev.get("rating", 5))
            if rating < 1 or rating > 5:
                rating = 5
        except (ValueError, TypeError):
            rating = 5

        reviewer_name = sanitize_text(rev.get("reviewer", "Anonyme"))
        timestamp = format_iso_timestamp(rev.get("date_created", ""))

        content_clean = sanitize_text(rev.get("review", ""))
        if not content_clean or len(content_clean) < 2:
            content_clean = "Avis client certifié"

        # 2. Construction de l'URL du produit
        # WooCommerce ne renvoie pas toujours product_permalink dans l'API reviews, on sécurise
        product_permalink = rev.get("product_permalink")
        if not product_permalink or product_permalink == clean_woo_url:
            product_permalink = f"{clean_woo_url}/?p={product_id}"

        review_url = f"{product_permalink}#comment-{review_id}"
        product_sku = str(rev.get("product_sku") or product_id or "")

        xml_parts.append("    <review>\n")
        xml_parts.append(f"      <review_id>{review_id}</review_id>\n")
        xml_parts.append("      <reviewer>\n")
        xml_parts.append(f"        <name><![CDATA[{reviewer_name}]]></name>\n")
        xml_parts.append("      </reviewer>\n")
        xml_parts.append(f"      <review_timestamp>{timestamp}</review_timestamp>\n")
        xml_parts.append(f"      <content><![CDATA[{content_clean}]]></content>\n")
        
        # FIX GOOGLE v2.3 : PAS de CDATA à l'intérieur de <review_url>
        xml_parts.append("      <review_urls>\n")
        xml_parts.append(
            f'        <review_url type="singleton">{review_url}</review_url>\n'
        )
        xml_parts.append("      </review_urls>\n")
        
        xml_parts.append("      <ratings>\n")
        xml_parts.append(f'        <overall min="1" max="5">{rating}</overall>\n')
        xml_parts.append("      </ratings>\n")
        
        # FIX GOOGLE v2.3 : Structure stricte de <products>
        xml_parts.append("      <products>\n")
        xml_parts.append("        <product>\n")
        xml_parts.append("          <product_ids>\n")
        if product_sku:
            xml_parts.append("            <mpns>\n")
            xml_parts.append(f"              <mpn>{product_sku}</mpn>\n")
            xml_parts.append("            </mpns>\n")
            xml_parts.append("            <skus>\n")
            xml_parts.append(f"              <sku>{product_sku}</sku>\n")
            xml_parts.append("            </skus>\n")
        xml_parts.append("          </product_ids>\n")
        # PAS de CDATA à l'intérieur de <product_url>
        xml_parts.append(
            f"          <product_url>{product_permalink}</product_url>\n"
        )
        xml_parts.append("        </product>\n")
        xml_parts.append("      </products>\n")
        xml_parts.append("    </review>\n")

    xml_parts.append("  </reviews>\n")
    xml_parts.append("</feed>")

    return "".join(xml_parts)
