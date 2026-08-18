# reviews_fetcher.py
import html
import logging
import re
from datetime import datetime, timezone
from xml.sax.saxutils import escape
from woocommerce_fetcher import safe_api_get

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Regex et constantes pré-compilées pour le nettoyage et l'optimisation
CLEAN_HTML_REGEX = re.compile(r"<[^>]+>")
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_REGEX = re.compile(r"(\+?\d{1,3}[-.\s]?)?(\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4}")
GTIN_KEYS = {"gtin", "ean", "_gtin", "_ean", "barcode"}  # Set pour recherche O(1)


def fetch_all_product_reviews(wcapi):
    """Extrait l'ensemble des avis produits validés via l'API WooCommerce."""
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
    """Convertit la date WooCommerce au format ISO 8601 strict."""
    if not date_string:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        clean_date = str(date_string).replace("Z", "")
        dt = datetime.fromisoformat(clean_date)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sanitize_text(text):
    """Nettoie le HTML, échappe CDATA et masque les PII (emails et téléphones)."""
    if not text:
        return ""

    raw_clean = html.unescape(str(text))
    clean_text = CLEAN_HTML_REGEX.sub(" ", raw_clean)

    # Anonymisation PII
    clean_text = EMAIL_REGEX.sub("[email masqué]", clean_text)
    clean_text = PHONE_REGEX.sub("[téléphone masqué]", clean_text)

    clean_text = clean_text.replace("]]>", "]]&gt;").strip()
    return clean_text


def extract_gtin_from_review(rev):
    """Tente de récupérer un code EAN/GTIN depuis la payload de l'avis si présent."""
    return next(
        (
            str(meta.get("value", "")).strip()
            for meta in rev.get("meta_data", [])
            if str(meta.get("key", "")).lower() in GTIN_KEYS and str(meta.get("value", "")).strip()
        ),
        None,
    )


def extract_brand_from_review(rev):
    """Extrait le nom de la marque associé à l'avis si disponible."""
    return str(rev.get("product_brand") or rev.get("brand") or "").strip()


def generate_reviews_xml(reviews, woo_url):
    """Génère le flux XML au format officiel Google Product Reviews (v2.4)."""
    clean_woo_url = woo_url.rstrip("/")

    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>\n',
        '<feed xmlns:vc="http://www.w3.org/2007/XMLSchema-versioning"\n',
        '      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n',
        '      xsi:noNamespaceSchemaLocation="http://www.google.com/shopping/reviews/schema/product/2.4/product_reviews.xsd">\n',
        "  <version>2.4</version>\n",
        "  <publisher>\n",
        "    <name>Karate-Gi</name>\n",
        f"    <favicon>{clean_woo_url}/favicon.ico</favicon>\n",
        "  </publisher>\n",
        "  <reviews>\n",
    ]

    for rev in reviews:
        review_id = str(rev.get("id"))
        product_id = str(rev.get("product_id", ""))

        # 1. Normalisation de la note
        try:
            rating = int(rev.get("rating", 5))
            if not 1 <= rating <= 5:
                rating = 5
        except (ValueError, TypeError):
            rating = 5

        reviewer_name = sanitize_text(rev.get("reviewer", "Anonyme"))
        timestamp = format_iso_timestamp(rev.get("date_created", ""))

        content_clean = sanitize_text(rev.get("review", ""))
        if not content_clean or len(content_clean) < 2:
            content_clean = "Avis client certifié"

        # 2. Nom et URL du produit
        product_name = sanitize_text(rev.get("product_name", ""))
        product_permalink = rev.get("product_permalink")
        if not product_permalink or "boutique" in product_permalink:
            product_permalink = f"{clean_woo_url}/?p={product_id}"

        safe_product_url = escape(product_permalink)
        safe_review_url = escape(f"{product_permalink}#comment-{review_id}")

        # 3. Extraction des identifiants
        product_sku = str(rev.get("product_sku") or "").strip()
        gtin = extract_gtin_from_review(rev)
        brand = extract_brand_from_review(rev)

        # 4. Construction des blocs optionnels pour le XML
        gtin_block = f"""            <gtins>
              <gtin>{escape(gtin)}</gtin>
            </gtins>\n""" if gtin else ""

        mpn_block = f"""            <mpns>
              <mpn>{escape(product_sku)}</mpn>
            </mpns>\n""" if product_sku else ""

        brand_block = f"""            <brands>
              <brand><![CDATA[{brand}]]></brand>
            </brands>\n""" if brand else ""
            
        product_name_block = f"          <product_name><![CDATA[{product_name}]]></product_name>\n" if product_name else ""
        sku_element = f"              <sku>{escape(product_sku)}</sku>\n" if product_sku else ""

        # 5. Injection dans le bloc XML de l'avis (f-string multiligne pour la performance)
        review_xml = f"""    <review>
      <review_id>{review_id}</review_id>
      <reviewer>
        <name><![CDATA[{reviewer_name}]]></name>
      </reviewer>
      <review_timestamp>{timestamp}</review_timestamp>
      <content><![CDATA[{content_clean}]]></content>
      <review_urls>
        <review_url type="singleton">{safe_review_url}</review_url>
      </review_urls>
      <ratings>
        <overall min="1" max="5">{rating}</overall>
      </ratings>
      <products>
        <product>
          <product_ids>
{gtin_block}{mpn_block}            <skus>
{sku_element}              <sku>{product_id}</sku>
            </skus>
{brand_block}          </product_ids>
{product_name_block}          <product_url>{safe_product_url}</product_url>
        </product>
      </products>
    </review>\n"""

        xml_parts.append(review_xml)

    xml_parts.append("  </reviews>\n")
    xml_parts.append("</feed>")

    return "".join(xml_parts)
