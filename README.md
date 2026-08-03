# google-shopping-multi-pays
Flux Google Shopping multi-pays (fiches-produits différentes) avec correction des erreurs automatique mis à jour quotidiennement

- Le flux Google Shopping précédent se mettait à jour régulièrement, mais :
1) 550 erreurs (produits non affichés) sur 7000 fiches-produits
2) Activé uniquement sur le marché français, et pas sur tous les marchés européens de l'entreprise (.de, .es, .it, etc.)
3) Peu de champs rempli (manque la majorité des images, la catégorie, les labels, etc.)


Extraction légère par batchs via l'API REST Read-Only (pour le flux complet) :
Au lieu de faire télécharger un gros fichier à GitHub Actions, le script Python interroge directement l'API REST de WooCommerce par pages de 100 produits (pagination), en arrière-plan.

Mises à jour événementielles pour le stock et le prix (Webhooks WooCommerce) :
Lorsqu'un produit tombe à 0 en stock ou change de prix sur le site, WooCommerce envoie immédiatement une mini-notification (Webhook) à un petit script ou serveur relais léger. Ce relais met à jour uniquement ce produit précis sur Google Merchant Center via la Content API.
