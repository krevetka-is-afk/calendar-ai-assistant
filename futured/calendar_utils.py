"""
Утилиты для работы с Google Calendar
"""
import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import pandas as pd
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from app.core.config import SCOPES, CREDENTIALS_FILE, TOKEN_FILE, DATA_FILE, DEFAULT_CALENDAR_ID, EVENT_FETCH_DAYS, MAX_EVENTS


class GoogleCalendarService:
    """Сервис для работы с Google Calendar"""
    
    def __init__(self):
        self.service = None
        self.credentials = None
    
    def get_service(self):
        """Получение сервиса Google Calendar"""
        try:
            creds = None
            
            # Проверяем наличие сохраненного токена
            if os.path.exists(TOKEN_FILE):
                try:
                    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
                except Exception:
                    creds = None
            
            # Если токен недействителен или отсутствует
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not os.path.exists(CREDENTIALS_FILE):
                        raise FileNotFoundError(f"Файл {CREDENTIALS_FILE} не найден")
                    
                    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                    creds = flow.run_local_server(port=0)
                
                # Сохраняем токен
                with open(TOKEN_FILE, 'w') as token:
                    token.write(creds.to_json())
            
            self.credentials = creds
            self.service = build('calendar', 'v3', credentials=creds)
            return self.service
            
        except Exception as e:
            raise Exception(f"Ошибка получения сервиса Google Calendar: {str(e)}")
    
    def get_user_email(self, service) -> str:
        """Получение email пользователя"""
        try:
            calendar_list = service.calendarList().list().execute()
            for calendar in calendar_list.get('items', []):
                if calendar.get('primary'):
                    return calendar.get('id')
            return "unknown@example.com"
        except Exception:
            return "unknown@example.com"
    
    def get_calendars(self, service) -> Dict[str, str]:
        """Получение списка календарей"""
        try:
            calendar_list = service.calendarList().list().execute()
            calendars = {}
            for calendar in calendar_list.get('items', []):
                calendars[calendar['summary']] = calendar['id']
            return calendars
        except Exception as e:
            raise Exception(f"Ошибка получения календарей: {str(e)}")
    
    def create_event(self, service, summary: str, start_dt: datetime, end_dt: datetime, 
                    description: str = "", attendees: List[str] = None, 
                    calendar_id: str = DEFAULT_CALENDAR_ID) -> Optional[str]:
        """Создание события в календаре"""
        try:
            event = {
                'summary': summary,
                'description': description,
                'start': {
                    'dateTime': start_dt.isoformat(),
                    'timeZone': 'Europe/Moscow',
                },
                'end': {
                    'dateTime': end_dt.isoformat(),
                    'timeZone': 'Europe/Moscow',
                },
            }
            
            if attendees:
                event['attendees'] = [{'email': email} for email in attendees]
            
            created = service.events().insert(calendarId=calendar_id, body=event).execute()
            return created.get('htmlLink', None)
            
        except Exception as e:
            raise Exception(f"Ошибка создания события: {str(e)}")
    
    def fetch_events(self, service, calendar_ids: Dict[str, str], user_email: str) -> List[Dict]:
        """Загрузка событий из календарей"""
        now = datetime.now()
        time_min = (now - timedelta(days=EVENT_FETCH_DAYS)).isoformat() + 'Z'
        time_max = (now + timedelta(days=EVENT_FETCH_DAYS)).isoformat() + 'Z'

        all_events = []
        for name, calendar_id in calendar_ids.items():
            events = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=MAX_EVENTS,
                singleEvents=True,
                orderBy='startTime'
            ).execute().get('items', [])

            for event in events:
                start = event['start'].get('dateTime') or event['start'].get('date')
                end = event['end'].get('dateTime') or event['end'].get('date')
                summary = event.get('summary', '[Без названия]')
                description = event.get('description', '')
                attendees_raw = event.get('attendees', [])
                attendees = [a.get("email") for a in attendees_raw if 'email' in a]
                
                if start and end:
                    all_events.append({
                        "calendar": name,
                        "start": start,
                        "end": end,
                        "summary": summary,
                        "description": description,
                        "attendees": attendees
                    })

        json_data = [{
            "user": user_email,
            "events": all_events
        }]

        # Безопасная запись в calendar_data.json
        self._safe_write_data(json_data)
        return json_data
    
    def find_conflicts(self, service, calendar_id: str, start_dt: datetime, end_dt: datetime) -> List[Dict]:
        """Поиск конфликтов в календаре"""
        try:
            start_utc = start_dt.astimezone(timezone.utc).isoformat()
            end_utc = end_dt.astimezone(timezone.utc).isoformat()
            events = service.events().list(
                calendarId=calendar_id,
                timeMin=start_utc,
                timeMax=end_utc,
                singleEvents=True
            ).execute().get("items", [])
            return events
        except Exception as e:
            raise Exception(f"Ошибка поиска конфликтов: {str(e)}")
    
    def _safe_write_data(self, json_data: List[Dict]):
        """Безопасная запись данных в файл"""
        try:
            # Удаляем calendar_data.json если это директория
            if os.path.exists(DATA_FILE) and os.path.isdir(DATA_FILE):
                shutil.rmtree(DATA_FILE)
            
            # Удаляем файл если он существует (для перезаписи)
            if os.path.exists(DATA_FILE) and os.path.isfile(DATA_FILE):
                os.remove(DATA_FILE)
            
            # Создаем новый файл
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            raise Exception(f"Ошибка записи в {DATA_FILE}: {str(e)}")
    
    def load_events_data(self) -> Optional[List[Dict]]:
        """Загрузка данных событий из файла"""
        try:
            if os.path.exists(DATA_FILE):
                if os.path.isdir(DATA_FILE):
                    shutil.rmtree(DATA_FILE)
                    return None
                elif os.path.isfile(DATA_FILE) and os.path.getsize(DATA_FILE) > 0:
                    with open(DATA_FILE, "r", encoding="utf-8") as f:
                        return json.load(f)
            return None
        except Exception as e:
            raise Exception(f"Ошибка чтения {DATA_FILE}: {str(e)}")


def normalize_datetime(datetime_str: str) -> datetime:
    """Нормализация datetime строки"""
    if 'T' in datetime_str:  # datetime с временем
        dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
        return dt.replace(tzinfo=None)  # Конвертируем в локальное время без timezone
    else:  # только дата
        return datetime.fromisoformat(datetime_str)


def process_events_for_analysis(events: List[Dict]) -> pd.DataFrame:
    """Обработка событий для анализа"""
    records = []
    for e in events:
        # Нормализуем datetime объекты
        start_str = e["start"]
        end_str = e["end"]
        
        start_dt = normalize_datetime(start_str)
        end_dt = normalize_datetime(end_str)
        
        weekday = start_dt.weekday()
        hour = start_dt.hour
        duration_min = (end_dt - start_dt).total_seconds() / 60
        
        records.append({
            "calendar": e["calendar"],
            "summary": e["summary"],
            "start": start_dt,
            "end": end_dt,
            "weekday": weekday,
            "hour": hour,
            "duration_min": duration_min
        })
    
    return pd.DataFrame(records)
