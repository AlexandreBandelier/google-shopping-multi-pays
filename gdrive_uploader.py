import os
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def upload_feed_to_gdrive(file_path, folder_id, service_account_json_str):
    """
    Téléverse ou remplace le fichier XML dans le dossier Google Drive spécifié.
    """
    scopes = ['https://www.googleapis.com/auth/drive.file']
    account_info = json.loads(service_account_json_str)
    creds = Credentials.from_service_account_info(account_info, scopes=scopes)
    service = build('drive', 'v3', credentials=creds)

    filename = os.path.basename(file_path)

    # 1. Chercher si le fichier existe déjà dans le dossier pour le remplacer
    query = f"'{folder_id}' in parents and name = '{filename}' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])

    media = MediaFileUpload(file_path, mimetype='application/xml')

    if items:
        # Fichier existant -> Mise à jour
        file_id = items[0]['id']
        service.files().update(fileId=file_id, media_body=media).execute()
        print(f"Fichier Google Drive mis à jour (ID: {file_id})")
    else:
        # Nouveau fichier -> Création
        file_metadata = {
            'name': filename,
            'parents': [folder_id]
        }
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        print(f"Fichier téléversé sur Google Drive (ID: {file.get('id')})")
