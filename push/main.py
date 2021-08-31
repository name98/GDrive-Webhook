import uuid
import os
import pickle
import json
import requests as req

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive',
          'https://www.googleapis.com/auth/drive.photos.readonly']
CREDENTIALS_FILE = ''


def auth():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server()
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return creds


def watch_changes_by_service(service, channel_id, channel_type, expiration_i, channel_address, channel_token=None,
                             channel_params=None):
    body = {
        'id': channel_id,
        'type': channel_type,
        'address': channel_address,
        "expiration": f"{expiration_i}"
    }
    response = service.changes().getStartPageToken().execute()
    page_token = response.get('startPageToken')
    if channel_token:
        body['token'] = channel_token
    if channel_params:
        body['params'] = channel_params
    return service.changes().watch(body=body, pageToken=page_token).execute()


def watch_file_by_service(service, file_id, channel_id, channel_type, channel_address,
                          channel_token=None, channel_params=None):
    body = {
        'id': channel_id,
        'type': channel_type,
        'address': channel_address
    }
    if channel_token:
        body['token'] = channel_token
    if channel_params:
        body['params'] = channel_params

    return service.files().watch(fileId=file_id, body=body).execute()


def stop_channel(service, channel_id, resource_id):
    body = {
        'id': channel_id,
        'resourceId': resource_id
    }
    return service.channels().stop(body=body).execute()


def watch_changes_by_request(channel_id, channel_type, channel_address, page_token, expiration_i):
    token = credentials.token
    header = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    body = {
        "id": channel_id,
        "type": f"{channel_type}",
        "address": f"{channel_address}",
        "expiration": f"{expiration_i}"
    }
    k = req.post(url=f'https://www.googleapis.com/drive/v3/changes/watch?pageToken={page_token}',
                 data=json.dumps(body), headers=header)
    return k.json()


credentials = auth()
service = build('drive', 'v3', credentials=credentials)
channel_id = str(uuid.uuid4())
channel_type = "web_hook"

# Домен
channel_address = "https://............/webhook"

# Срок исполнения WEBHOOK (макс. 7 дней)
# 1644872150000 = Mon Feb 14 2022 20:55:50 GMT+0000, Milliseconds
expiration_i = 1644872150000

# Начальный ID изменений
response = service.changes().getStartPageToken().execute()
page_token = response.get('startPageToken')

# Запуск с помощью запроса POST
# push = watch_changes_by_request(channel_id=channel_id, channel_type=channel_type, 
#                                channel_address=channel_address, page_token=page_token, expiration_i=expiration_i)

# Запуск с помощью GService
# push = watch_changes_by_service(service=service, channel_id=channel_id, 
#                                 channel_type=channel_type, channel_address=channel_address, expiration_i=expiration_i)

# Оставить WEBHOOK
# push = stop_channel(service=service, channel_id='fa281db2-247b-4103-bc74-a04ccc6c9482', 
#                    resource_id="7M8ZPBRpCC0g2nrK296goVzllI0")

print(push)
