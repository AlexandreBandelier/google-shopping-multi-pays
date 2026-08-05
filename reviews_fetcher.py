# reviews_fetcher.py
import html
import logging
import re
from datetime import datetime, timezone
from xml.sax.saxutils import escape
from woocommerce_fetcher import safe_api_get

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Regex pré-compilées pour le nettoyage
CLEAN_HTML_REGEX = re.compile(r"<[^>]+>")
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_REGEX = re.compile(
    r"(\+?\d{1,3}[-.\s]?)?(\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4}"
)


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
  """Convertit la date WooCommerce au format ISO 8601 strict (ex: 2026-08-05T10:00:00Z)."""
  if not date_string:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
  try:
    clean_date = str(date_string).replace("Z", "")
    dt = datetime.fromisoformat(clean_date)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
  except Exception:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sanitize_text(text):
  """Nettoie le HTML, échappe CDATA et masque les informations personnelles (PII) telles que les emails et numéros de téléphone."""
  if not text:
    return ""

  raw_clean = html.unescape(str(text))
  clean_text = CLEAN_HTML_REGEX.sub(" ", raw_clean)

  # Anonymisation PII
  clean_text = EMAIL_REGEX.sub("[email masqué]", clean_text)
  clean_text = PHONE_REGEX.sub("[téléphone masqué]", clean_text)

  clean_text = clean_text.replace("]]>", "]]&gt;").strip()
  return clean_text


def generate_reviews_xml(reviews, woo_url):
  """Génère le flux XML au format officiel Google Product Reviews (v2.3) révisé."""
  clean_woo_url = woo_url.rstrip("/")
  brand_name = "VotreMarque"  # Remplacez par le nom exact de votre marque

  xml_parts = [
      '<?xml version="1.0" encoding="UTF-8"?>\n',
      '<feed xmlns:vc="http://www.w3.org/2007/XMLSchema-versioning"\n',
      '      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n',
      '      xsi:noNamespaceSchemaLocation="http://www.google.com/shopping/reviews/schema/product_reviews_schema.xsd">\n',
      "  <version>2.3</version>\n",
      "  <publisher>\n",
      f"    <name>{escape(brand_name)}</name>\n",
      f"    <favicon>{clean_woo_url}/favicon.ico</favicon>\n",
      "  </publisher>\n",
      "  <reviews>\n",
  ]

  for rev in reviews:
    review_id = str(rev.get("id"))
    product_id = str(rev.get("product_id", ""))

    # 1. Normalisation du Rating
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

    # 2. Construction de l'URL Produit et Avis
    product_permalink = rev.get("product_permalink")
    if not product_permalink or "boutique" in product_permalink:
      product_permalink = f"{clean_woo_url}/?p={product_id}"

    # Échappement des caractères spéciaux dans les URLs (ex: & -> &amp;)
    safe_product_url = escape(product_permalink)
    safe_review_url = escape(f"{product_permalink}#comment-{review_id}")

    product_sku = str(rev.get("product_sku") or "")

    xml_parts.append("    <review>\n")
    xml_parts.append(f"      <review_id>{review_id}</review_id>\n")
    xml_parts.append("      <reviewer>\n")
    xml_parts.append(f"        <name><![CDATA[{reviewer_name}]]></name>\n")
    xml_parts.append("      </reviewer>\n")
    xml_parts.append(f"      <review_timestamp>{timestamp}</review_timestamp>\n")
    xml_parts.append(f"      <content><![CDATA[{content_clean}]]></content>\n")

    # Structure URL révisée sans CDATA mais échappée XML
    xml_parts.append("      <review_urls>\n")
    xml_parts.append(
        f'        <review_url type="singleton">{safe_review_url}</review_url>\n'
    )
    xml_parts.append("      </review_urls>\n")

    xml_parts.append("      <ratings>\n")
    xml_parts.append(f'        <overall min="1" max="5">{rating}</overall>\n')
    xml_parts.append("      </ratings>\n")

    # Structure Produit complète (Marque + SKUs + MPNs + ID WooCommerce)
    xml_parts.append("      <products>\n")
    xml_parts.append("        <product>\n")
    xml_parts.append("          <product_ids>\n")

    # Ajout de la marque (Requis par Google si MPN/SKU présent)
    xml_parts.append("            <brands>\n")
    xml_parts.append(f"              <brand>{escape(brand_name)}</brand>\n")
    xml_parts.append("            </brands>\n")

    xml_parts.append("            <skus>\n")
    if product_sku:
      xml_parts.append(f"              <sku>{escape(product_sku)}</sku>\n")
    # Backup ID produit principal
    xml_parts.append(f"              <sku>{product_id}</sku>\n")
    xml_parts.append("            </skus>\n")

    if product_sku:
      xml_parts.append("            <mpns>\n")
      xml_parts.append(f"              <mpn>{escape(product_sku)}</mpn>\n")
      xml_parts.append("            </mpns>\n")

    xml_parts.append("          </product_ids>\n")
    xml_parts.append(f"          <product_url>{safe_product_url}</product_url>\n")
    xml_parts.append("        </product>\n")
    xml_parts.append("      </products>\n")
    xml_parts.append("    </review>\n")

  xml_parts.append("  </reviews>\n")
  xml_parts.append("</feed>")

  return "".join(xml_parts)
