# reviews_fetcher.py
import io
import html
import logging
from woocommerce_fetcher import safe_api_get

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
            params={"per_page": 100, "page": page, "status": "approved"}
        )
        
        if not reviews:
            break
            
        all_reviews.extend(reviews)
        logger.info(f"-> Page {page} d'avis récupérée ({len(reviews)} avis)")
        page += 1
        
    logger.info(f"Total avis récupérés : {len(all_reviews)}")
    return all_reviews

def generate_reviews_xml(reviews, woo_url):
    """
    Génère le flux XML au format officiel Google Product Reviews.
    """
    buffer = io.StringIO()
    
    buffer.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    buffer.write('<feed xmlns:vc="http://www.w3.org/2007/XMLSchema-versioning"\n')
    buffer.write('      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n')
    buffer.write('      xsi:noNamespaceSchemaLocation="http://www.google.com/shopping/reviews/reviews_schema.xsd">\n')
    buffer.write('  <publisher>\n')
    buffer.write('    <name>Votre Boutique</name>\n')
    buffer.write(f'    <favicon>{woo_url}/favicon.ico</favicon>\n')
    buffer.write('  </publisher>\n')
    buffer.write('  <reviews>\n')
    
    for rev in reviews:
        review_id = rev.get('id')
        product_id = rev.get('product_id')
        rating = rev.get('rating', 5)
        reviewer_name = rev.get('reviewer', 'Anonyme')
        date_created = rev.get('date_created', '').replace('T', ' ')
        content = html.unescape(rev.get('review', ''))
        
        # Nettoyage du HTML dans le commentaire
        import re
        content_clean = re.sub(r'<[^>]+>', ' ', content).strip()

        buffer.write('    <review>\n')
        buffer.write(f'      <review_id>{review_id}</review_id>\n')
        buffer.write('      <reviewer>\n')
        buffer.write(f'        <name><![CDATA[{reviewer_name}]]></name>\n')
        buffer.write('      </reviewer>\n')
        buffer.write(f'      <review_timestamp>{date_created}</review_timestamp>\n')
        buffer.write('      <content><![CDATA[' + content_clean + ']]></content>\n')
        buffer.write('      <ratings>\n')
        buffer.write('        <overall min="1" max="5">' + str(rating) + '</overall>\n')
        buffer.write('      </ratings>\n')
        buffer.write('      <products>\n')
        buffer.write('        <product>\n')
        buffer.write('          <product_ids>\n')
        buffer.write(f'            <g_id>{product_id}</g_id>\n')
        buffer.write('          </product_ids>\n')
        buffer.write('        </product>\n')
        buffer.write('      </products>\n')
        buffer.write('    </review>\n')
        
    buffer.write('  </reviews>\n')
    buffer.write('</feed>')
    
    xml_content = buffer.getvalue()
    buffer.close()
    return xml_content
