# gdrive_uploader.py
import os
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def upload_feed_to_gdrive(file_path, folder_id, service_account_json_str):
    """
    Téléverse ou remplace le fichier XML dans le dossier Google Drive spécifié.
    Optimisé pour la résilience réseau et la vitesse d'exécution.
    """
    scopes = ['https://www.googleapis.com/auth/drive.file']
    account_info = json.loads(service_account_json_str)
    creds = Credentials.from_service_account_info(account_info, scopes=scopes)
    service = build('drive', 'v3', credentials=creds)

    filename = os.path.basename(file_path)

    # 1. OPTIMISATION : Échappement des caractères spéciaux dans la recherche
    safe_filename = filename.replace("'", "\\'")
    query = f"'{folder_id}' in parents and name = '{safe_filename}' and trashed = false"

    # 2. OPTIMISATION : Requête légère (pageSize=1, fields stricts)
    results = service.files().list(
        q=query, 
        pageSize=1, 
        fields="files(id)"
    ).execute()
    
    items = results.get('files', [])

    # 3. OPTIMISATION : Upload résilient en mode 'resumable'
    media = MediaFileUpload(
        file_path, 
        mimetype='application/xml', 
        resumable=True
    )

    if items:
        # Fichier existant -> Mise à jour
        file_id = items[0]['id']
        updated_file = service.files().update(
            fileId=file_id, 
            media_body=media, 
            fields='id'
        ).execute()
        print(f"Fichier Google Drive mis à jour (ID: {updated_file.get('id')})")
    else:
        # Nouveau fichier -> Création
        file_metadata = {
            'name': filename,
            'parents': [folder_id]
        }
        created_file = service.files().create(
            body=file_metadata, 
            media_body=media, 
            fields='id'
        ).execute()
        print(f"✅ Fichier téléversé sur Google Drive (ID: {created_file.get('id')})")
