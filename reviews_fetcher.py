# reviews_fetcher.py
import html
import re
import logging
from datetime import datetime, timezone
from woocommerce_fetcher import safe_api_get

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Regex pré-compilée pour nettoyer le HTML
CLEAN_HTML_REGEX = re.compile(r'<[^>]+>')


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
        clean_date = date_string.replace("Z", "")
        dt = datetime.fromisoformat(clean_date)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean_cdata(text):
    """
    Échappe la séquence ']]>' pour éviter de casser la structure XML CDATA.
    """
    if not text:
        return ""
    return str(text).replace("]]>", "]]&gt;")


def generate_reviews_xml(reviews, woo_url):
    """
    Génère le flux XML au format officiel Google Product Reviews (v2.3).
    """
    clean_woo_url = woo_url.rstrip("/")

    # En-tête XML
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
        rating = rev.get("rating", 5)
        reviewer_name = clean_cdata(rev.get("reviewer", "Anonyme"))

        timestamp = format_iso_timestamp(rev.get("date_created", ""))

        content_raw = html.unescape(rev.get("review", ""))
        content_clean = CLEAN_HTML_REGEX.sub(" ", content_raw).strip()
        if not content_clean:
            content_clean = "Avis client"
        content_clean = clean_cdata(content_clean)

        product_permalink = rev.get("product_permalink", clean_woo_url)
        review_url = f"{product_permalink}#comment-{review_id}"
        product_sku = rev.get("product_sku", str(product_id))

        xml_parts.append("    <review>\n")
        xml_parts.append(f"      <review_id>{review_id}</review_id>\n")
        xml_parts.append("      <reviewer>\n")
        xml_parts.append(f"        <name><![CDATA[{reviewer_name}]]></name>\n")
        xml_parts.append("      </reviewer>\n")
        xml_parts.append(f"      <review_timestamp>{timestamp}</review_timestamp>\n")
        xml_parts.append(f"      <content><![CDATA[{content_clean}]]></content>\n")
        xml_parts.append("      <review_urls>\n")
        xml_parts.append(
            f'        <review_url type="singleton"><![CDATA[{review_url}]]></review_url>\n'
        )
        xml_parts.append("      </review_urls>\n")
        xml_parts.append("      <ratings>\n")
        xml_parts.append(f"        <overall min=\"1\" max=\"5\">{rating}</overall>\n")
        xml_parts.append("      </ratings>\n")
        xml_parts.append("      <products>\n")
        xml_parts.append("        <product>\n")
        xml_parts.append("          <product_ids>\n")
        if product_sku:
            xml_parts.append("            <mpns>\n")
            xml_parts.append(f"              <mpn><![CDATA[{product_sku}]]></mpn>\n")
            xml_parts.append("            </mpns>\n")
        xml_parts.append("          </product_ids>\n")
        xml_parts.append(
            f"          <product_url><![CDATA[{product_permalink}]]></product_url>\n"
        )
        xml_parts.append("        </product>\n")
        xml_parts.append("      </products>\n")
        xml_parts.append("    </review>\n")

    xml_parts.append("  </reviews>\n")
    xml_parts.append("</feed>")

    return "".join(xml_parts)
