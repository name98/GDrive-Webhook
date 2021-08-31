import pytz
import sqlite3 as lite
import requests as requests1
import io
import shutil
import os
import pickle
import redis
import sys

from google.auth.transport.requests import Request
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from rq import Queue

# OAuth 2.0 Client ID credential file
CREDENTIAL_FILE = ''
SCOPES = ['https://www.googleapis.com/auth/drive',
          'https://www.googleapis.com/auth/drive.file',
          'https://www.googleapis.com/auth/drive.readonly',
          'https://www.googleapis.com/auth/drive.metadata.readonly',
          'https://www.googleapis.com/auth/drive.appdata',
          'https://www.googleapis.com/auth/drive.metadata',
          'https://www.googleapis.com/auth/drive.photos.readonly']
# ID родительской папки
FOLDER_ID = ''

# Flask и Redis Queue
app = Flask(__name__)
r = redis.Redis()
q = Queue(connection=r, default_timeout=6000)

# БД
db_connection = None
cursor = None

# ID изменений
credentials = None
start_page_token = 0

# Статус
is_started = False


def get_timestamp():
    dt = datetime.now(pytz.timezone('Europe/Moscow'))

    return dt.strftime("%Y-%m-%d %H:%M:%S")


@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    # Получение уведомлений от GDrive
    global start_page_token
    if request.method == 'GET':
        return '<h1> This is a webhook listener!</h1>'

    if request.method == 'POST':
        headers = request.headers
        print(headers)
        print(request.data)
        if 'X-Goog-Resource-State' in headers.keys():
            state = str(request.headers['X-Goog-Resource-State'])
            if state != 'sync':
                job = q.enqueue(retrieve_all_changes_v3, start_page_token)
                insert_log(f"Changes {job.id} added to queue at {job.enqueued_at}. "
                           f"{len(q)} changes in queue. Current page token {start_page_token}")
                start_page_token = get_page_token()
                insert_log(f"Next page token {start_page_token}")

        else:
            insert_log("HEADERS: " + str(request.headers))
            insert_log("BODY: " + str(request.get_data()))

        http_status = jsonify({'status': 'success'}), 200

    else:
        http_status = '', 400

    return http_status


def auth():
    # Получение credential для работы Google API
    credential = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            credential = pickle.load(token)
    if not credential or not credential.valid:
        if credential \
                and credential.expired \
                and credential.refresh_token:
            credential.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIAL_FILE, SCOPES)
            credential = flow.run_local_server()
        with open('token.pickle', 'wb') as token:
            pickle.dump(credential, token)

    return credential


def init_file(file_id):
    # Инициализация файла
    file_params = get_file_params(file_id)

    if file_params is not None:
        print(f"File params:\n{file_params}")

        if file_params['trashed'] is False \
                and is_video(file_params['mimeType']) \
                and is_parent(file_params['parents']) \
                and is_new_file(file_id):
            file_param_id = str(file_params['id'])
            file_param_title = str(file_params['title'])

            return {
                'file_id': file_param_id,
                'file_title': file_param_title
            }

    return None


def get_page_token():
    # Получение ID последних изменений
    try:
        token_service = build('drive', 'v3', credentials=credentials)
        response = token_service.changes().getStartPageToken().execute()
        return response.get('startPageToken')
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        insert_log(f"Error while getting page token: {start_page_token} {str(e)} {str(fname)} {str(exc_tb.tb_lineno)}")


def is_parent(parents):
    # Проверка родительской папки файла
    for parent in parents:
        if 'id' in parent.keys():
            if str(parent['id']) == str(FOLDER_ID):
                return True
    return False


def is_video(mime_type):
    # Проверка формата файла
    x = str(mime_type).find("video")
    return int(x) != -1


def download_file(file_id, title):
    # Скачивание файла
    drive_service = build('drive', 'v3', credentials=credentials)
    download_request = drive_service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, download_request, chunksize=204800)
    done = False
    try:
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        with open(title, 'wb') as f:
            shutil.copyfileobj(fh, f)
        return True

    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        insert_log(f"Error while downloading: "
                   f"file {file_id} "
                   f"{str(e)} {str(fname)} {str(exc_tb.tb_lineno)}")

        return False


def get_file_params(file_id):
    # Получение сведений о файле
    get_file_url = "https://www.googleapis.com/drive/v2/files/" + file_id
    header = {
        'Authorization': f'Bearer ' + str(credentials.token),
        'Content-Type': 'application/json',
    }
    response = requests1.get(url=get_file_url, headers=header)
    data = response.json()

    if 'title' in data.keys() \
            and 'labels' in data.keys() \
            and 'trashed' in data['labels'].keys() \
            and 'mimeType' in data.keys() \
            and 'parents' in data.keys() \
            and 'id' in data.keys():

        return {
            'title': data['title'],
            'parents': data['parents'],
            'trashed': data['labels']['trashed'],
            'mimeType': data['mimeType'],
            'id': data['id']
        }
    else:
        return None


def start_downloading(download_files_param):
    # Загрузка полученных файлов
    for download_file_param in download_files_param:
        is_downloaded = download_file(file_id=download_file_param['file_id'], title=download_file_param['file_title'])
        if is_downloaded is True:
            insert_video_db(file_id=download_file_param['file_id'], title=download_file_param['file_title'])
            insert_log("FILE DOWNLOADED: " + download_file_param['file_title'])
            print("FILE DOWNLOADED: " + download_file_param['file_title'])
    return


def create_db():
    # Создыние таблиц VIDEOS, LOGS
    # Запускается при открытии страницы /start
    try:
        cursor.execute('''CREATE TABLE VIDEOS
                     ([generated_id] INTEGER PRIMARY KEY,
                     [VVIDEO_FILE_ID] text, [TTITLE] text, 
                     [DDate] timestamp)''')
        cursor.execute('''CREATE TABLE LOGS
                     ([generated_id] INTEGER PRIMARY KEY,
                     [LLOG] text, [DDate] timestamp)''')
        db_connection.commit()
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        insert_log(
            f"ERROR: {start_page_token} {str(e)} {str(fname)} {str(exc_tb.tb_lineno)}")

    return


def insert_video_db(file_id, title):
    # Запись новых данных в таблицу VIDEOS
    sqlite_insert_with_param = """INSERT INTO VIDEOS
                              ('VVIDEO_FILE_ID', 'TTITLE', 'DDate') 
                              VALUES (?, ?, ?);"""
    joining_date = datetime.now()
    data_tuple = (file_id, title, joining_date)
    cursor.execute(sqlite_insert_with_param, data_tuple)
    db_connection.commit()
    return cursor.lastrowid


def is_new_file(file_id):
    # Проверка что файл не был скачан ранее
    cursor.execute('''SELECT 1 FROM VIDEOS AS V WHERE V.VVIDEO_FILE_ID=\'''' + str(file_id) + '''\'''')
    rows = cursor.fetchall()
    if len(rows) != 0:
        print(f"The file with this ID ({file_id}) has already been downloaded.")

    return len(rows) == 0


def insert_log(log):
    # Добавление новых данных в таблицу LLOGS
    sqlite_insert_with_param = """INSERT INTO LOGS
                                  ('LLOG', 'DDate') 
                                  VALUES (?, ?);"""
    joining_date = datetime.now()
    data_tuple = (log, joining_date)
    cursor.execute(sqlite_insert_with_param, data_tuple)
    db_connection.commit()
    return cursor.lastrowid


def initial_setup():
    # Первоначальные настройки, инициализация глобальных переменных
    # Авторизация токена
    # Создание БД, таблиц
    global credentials, start_page_token, \
        db_connection, cursor
    credentials = auth()
    try:
        start_page_token = get_page_token()
        db_connection = lite.connect('WEBHOOK_DATA_BASE',
                                     check_same_thread=False)
        cursor = db_connection.cursor()
        create_db()
        insert_log(f"{get_timestamp()} -- Started!")
        insert_log(f"Start page token - {start_page_token}")
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        insert_log(f"ERROR: {str(e)} {str(fname)} {str(exc_tb.tb_lineno)}")
    return


def init_db():
    # Создание/Открытие БД
    global db_connection, cursor
    db_connection = lite.connect('WEBHOOK_DATA_BASE',
                                 check_same_thread=False)
    cursor = db_connection.cursor()


@app.route("/start")
def start():
    # Вызов функции настройки данных
    global is_started
    if is_started is False:
        initial_setup()
        is_started = True
        return "Started"
    else:
        return "Already started"


@app.route('/googledd30d2a17c531dad.html')
def admin():
    # Подтвеждение домена
    return render_template('googledd30d2a17c531dad.html')


@app.route('/files')
def files():
    # Вывод скачанных файлов
    cursor.execute("SELECT * FROM VIDEOS")
    data = cursor.fetchall()
    return render_template('downloaded_files.html', data=data)


@app.route('/logs')
def logs():
    # Вывод логов
    cursor.execute("SELECT * FROM LOGS")
    data = cursor.fetchall()
    return render_template('logs.html', data=data)


def retrieve_all_changes_v3(page_token):
    # Обработка полученных изменений в GDrive
    global credentials
    init_db()
    credentials = auth()

    try:
        request_url = 'https://www.googleapis.com/drive/v3/changes?pageToken='
        headers = {
            'Authorization': f'Bearer ' + str(credentials.token),
            'Content-Type': 'application/json',
        }
        response = requests1.get(url=request_url + str(page_token), headers=headers)
        data = response.json()
        filed_ids = []
        download_file_params = []

        if 'changes' in data.keys():
            changes = data['changes']
            for change in changes:

                if ('removed' in change.keys() and change['removed'] == False) \
                        and 'fileId' in change.keys():
                    download_file_param = init_file(change['fileId'])

                    if download_file_param is not None:
                        download_file_params.append(download_file_param)
                    filed_ids.append(change['fileId'])

            if len(download_file_params) != 0:
                start_downloading(download_file_params)

    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()

        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        insert_log(
            f"Error while fetching changes: page token {start_page_token} {str(e)} {str(fname)} {str(exc_tb.tb_lineno)}")

    return


if __name__ == "__main__":
    app.run()