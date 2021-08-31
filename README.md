# GDrive Webhook

The Drive API provides push notifications that let you watch for changes to resources. You can use this feature to improve the performance of your application. It allows you to eliminate the extra network and compute costs involved with polling resources to determine if they have changed. Whenever a watched resource changes, the Drive API notifies your application. I implemented this task in the Python programming language. Web Framework - [Flask](https://ru.wikipedia.org/wiki/Flask_(%D0%B2%D0%B5%D0%B1-%D1%84%D1%80%D0%B5%D0%B9%D0%BC%D0%B2%D0%BE%D1%80%D0%BA))

# Implementation

To create a webhook, you need a web server with a valid [SSL](https://ru.wikipedia.org/wiki/SSL) certificate, domain name, [OAuth client ID](https://developers.google.com/identity/protocols/oauth2/).
As a server, I used my computer using the [ngrok](https://ngrok.com/) tool. With a paid subscription, I managed to get an SSL certificate and a temporary domain.
Before creating a webhook, you need to go through [domain verification](https://console.developers.google.com/).
#### Connecting Google API:
````
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
````
#### Creating a webhook (Method I):
````
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
````
#### Creating a webhook (Method II):
````
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
````

#### Launching webhook:
````
credentials = auth()
service = build('drive', 'v3', credentials=credentials)
channel_id = str(uuid.uuid4())
channel_type = "web_hook"

# Your domen
channel_address = "https://............/webhook"

# expiration_i - Webhook lifetime
# The maximum webhook life is 7 days
# 1644872150000 = Mon Feb 14 2022 20:55:50 GMT+0000, Milliseconds
expiration_i = 1644872150000

# Getting startID
response = service.changes().getStartPageToken().execute()
page_token = response.get('startPageToken')

# Launch with POST request
# push = watch_changes_by_request(channel_id=channel_id, channel_type=channel_type, 
# channel_address=channel_address, page_token=page_token, expiration_i=expiration_i)

# Launch with GService
# push = watch_changes_by_service(service=service, channel_id=channel_id, 
# channel_type=channel_type, channel_address=channel_address, expiration_i=expiration_i)
print(push)
````
The web service is implemented using the Flask framework. A request with data comes to the specified domain. This webhook listener implements downloading video files in a specific folder.

