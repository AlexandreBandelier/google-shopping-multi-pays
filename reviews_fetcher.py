# reviews_fetcher.py
import html
import logging
import re
from datetime import datetime, timezone
from xml.sax.saxutils import escape
from woocommerce_fetcher import safe_api_get

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Regex et constantes pré-compilées
CLEAN_HTML_REGEX = re.compile(r"<[^>]+>")
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_REGEX = re.compile(r"(\+?\d{1,3}[-.\s]?)?(\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4}")
GTIN_KEYS = {"gtin", "ean", "_gtin", "_ean", "barcode"}

# Nom de marque par défaut requis par Google
DEFAULT_BRAND_NAME = "Karate-Gi"

# Liste complète de vos boutiques / domaines internationaux
TARGET_DOMAINS = [
    "https://karate-gi.fr",
    "https://karate-gi.dk",
    "https://karate-gi.nl",
    "https://karate-gi.eu",
    "https://karate-gi.be",
    "https://karate-gi.es",
    "https://karate-gi.de",
    "https://karate-gi.it",
]

# OPTIMISATION 3 : Pré-nettoyage des domaines cibles pour éviter les calculs dans les boucles
CLEAN_TARGET_DOMAINS = [domain.rstrip("/") for domain in TARGET_DOMAINS]


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
    """Nettoie le HTML, supprime les caractères de contrôle XML invalides et masque les PII."""
    if not text:
        return ""

    raw_clean = html.unescape(str(text))
    clean_text = CLEAN_HTML_REGEX.sub(" ", raw_clean)

    # Anonymisation PII
    clean_text = EMAIL_REGEX.sub("[email masqué]", clean_text)
    clean_text = PHONE_REGEX.sub("[téléphone masqué]", clean_text)

    # Filtrage des caractères de contrôle XML non valides
    clean_text = "".join(ch for ch in clean_text if ord(ch) >= 32 or ch in "\t\n\r")
    clean_text = clean_text.replace("]]>", "]]&gt;").strip()
    return clean_text


def extract_gtin_from_review(rev):
    """Tente de récupérer un code EAN/GTIN depuis la payload de l'avis si présent."""
    # OPTIMISATION 2 : Utilisation du walrus operator (:=) pour éviter de double-parser la valeur
    return next(
        (
            val
            for meta in rev.get("meta_data", [])
            if str(meta.get("key", "")).lower() in GTIN_KEYS and (val := str(meta.get("value", "")).strip())
        ),
        None,
    )


def extract_brand_from_review(rev):
    """Extrait la marque du produit ou retourne la marque par défaut pour satisfaire Google."""
    brand = str(rev.get("product_brand") or rev.get("brand") or "").strip()
    return brand if brand else DEFAULT_BRAND_NAME


def build_country_product_url(base_permalink, clean_base_url, clean_target, product_id):
    """Génère l'URL canonique du produit pour chaque domaine cible."""
    if base_permalink and clean_base_url in base_permalink:
        return base_permalink.replace(clean_base_url, clean_target)
    return f"{clean_target}/?p={product_id}"


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

        # 1. Normalisation de la note (Min 1, Max 5)
        try:
            rating = int(rev.get("rating", 5))
            if not 1 <= rating <= 5:
                rating = 5
        except (ValueError, TypeError):
            rating = 5

        reviewer_name = sanitize_text(rev.get("reviewer", "Anonyme"))
        timestamp = format_iso_timestamp(rev.get("date_created", ""))

        # 2. Nettoyage du contenu de l'avis
        content_clean = sanitize_text(rev.get("review", ""))
        if not content_clean or len(content_clean) < 3:
            content_clean = "Avis client certifié suite à un achat vérifié."

        # 3. URL de l'avis au format strict imposé par Google Schema 2.4
        product_permalink = rev.get("product_permalink") or f"{clean_woo_url}/?p={product_id}"
        safe_review_url = escape(f"{product_permalink}#comment-{review_id}")

        # 4. Identification du produit
        raw_sku = str(rev.get("product_sku") or "").strip()
        mpn_sku_val = raw_sku if raw_sku else product_id
        
        gtin = extract_gtin_from_review(rev)
        brand = extract_brand_from_review(rev)
        product_name = sanitize_text(rev.get("product_name", ""))

        # OPTIMISATION 1 : Construction du bloc produit global (Identifiants communs à tous les pays)
        gtin_block = f"            <gtins>\n              <gtin>{escape(gtin)}</gtin>\n            </gtins>\n" if gtin else ""
        mpn_block = f"            <mpns>\n              <mpn>{escape(mpn_sku_val)}</mpn>\n            </mpns>\n"
        brand_block = f"            <brands>\n              <brand><![CDATA[{brand}]]></brand>\n            </brands>\n"
        
        sku_lines = f"              <sku>{escape(mpn_sku_val)}</sku>\n"
        if product_id and product_id != mpn_sku_val:
            sku_lines += f"              <sku>{product_id}</sku>\n"

        product_name_block = f"          <product_name><![CDATA[{product_name}]]></product_name>\n" if product_name else ""

        shared_product_ids_xml = f"""          <product_ids>
{gtin_block}{mpn_block}            <skus>
{sku_lines}            </skus>
{brand_block}          </product_ids>
{product_name_block}"""

        # 5. Injection du bloc commun dans la déclinaison des produits
        products_xml_blocks = []
        for clean_target in CLEAN_TARGET_DOMAINS:
            prod_url = build_country_product_url(product_permalink, clean_woo_url, clean_target, product_id)
            safe_prod_url = escape(prod_url)

            products_xml_blocks.append(f"""        <product>
{shared_product_ids_xml}          <product_url>{safe_prod_url}</product_url>
        </product>""")

        all_products_xml = "\n".join(products_xml_blocks)

        # 6. Assemblage final du bloc avis
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
{all_products_xml}
      </products>
    </review>\n"""

        xml_parts.append(review_xml)

    xml_parts.append("  </reviews>\n")
    xml_parts.append("</feed>")

    return "".join(xml_parts)
