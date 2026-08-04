# gdrive_uploader.py
import os
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def upload_feed_to_gdrive(file_path, folder_id, service_account_json_str):
    """
    Téléverse ou remplace le fichier XML dans le dossier Google Drive spécifié.
    Résout les erreurs de quota des Comptes de Service.
    """
    scopes = ['https://www.googleapis.com/auth/drive']
    account_info = json.loads(service_account_json_str)
    creds = Credentials.from_service_account_info(account_info, scopes=scopes)
    service = build('drive', 'v3', credentials=creds)

    filename = os.path.basename(file_path)
    safe_filename = filename.replace("'", "\\'")

    # Recherche du fichier dans le dossier spécifié
    query = f"'{folder_id}' in parents and name = '{safe_filename}' and trashed = false"
    
    results = service.files().list(
        q=query, 
        pageSize=1, 
        fields="files(id)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    
    items = results.get('files', [])

    media = MediaFileUpload(
        file_path, 
        mimetype='application/xml', 
        resumable=True
    )

    if items:
        # Fichier existant -> Mise à jour (Consomme le quota du propriétaire initial)
        file_id = items[0]['id']
        updated_file = service.files().update(
            fileId=file_id, 
            media_body=media, 
            fields='id',
            supportsAllDrives=True
        ).execute()
        print(f"Fichier Google Drive mis à jour avec succès (ID: {updated_file.get('id')})")
    else:
        # Si le fichier n'est pas trouvé dans le dossier
        raise Exception(
            f"Le fichier '{filename}' n'existe pas encore dans le dossier Google Drive.\n"
            "Pour éviter les erreurs de quota du Compte de Service, veuillez créer/téléverser un fichier vide nommé "
            f"'{filename}' directement dans votre dossier Google Drive, puis relancez le workflow."
        )
