#!/usr/bin/env python3
"""
Скрипт для настройки авторизации Google Calendar на хосте
"""

import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']

def setup_google_auth():
    """Настройка авторизации Google Calendar"""
    
    print("🔧 Настройка авторизации Google Calendar")
    print("=" * 50)
    
    # Проверка наличия credentials.json
    if not os.path.exists('../../credentials.json'):
        print("❌ Файл credentials.json не найден!")
        print("\n📋 Инструкции:")
        print("1. Перейдите в Google Cloud Console")
        print("2. Создайте OAuth 2.0 credentials")
        print("3. Скачайте JSON файл и переименуйте в credentials.json")
        print("4. Поместите файл в корень проекта")
        return False
    
    try:
        print("✅ credentials.json найден")
        
        # Создание flow для авторизации
        print("\n🔐 Запуск авторизации...")
        flow = InstalledAppFlow.from_client_secrets_file('../../credentials.json', SCOPES)
        
        # Запуск локального сервера для авторизации
        print("🌐 Откроется браузер для авторизации...")
        creds = flow.run_local_server(port=0)
        
        # Тестирование подключения
        print("\n🧪 Тестирование подключения...")
        service = build('calendar', 'v3', credentials=creds)
        
        # Получение информации о пользователе
        profile = service.calendarList().get(calendarId='primary').execute()
        user_email = profile['id']
        
        print(f"✅ Авторизация успешна!")
        print(f"👤 Пользователь: {user_email}")
        
        # Получение списка календарей
        calendars = service.calendarList().list().execute().get('items', [])
        print(f"📅 Доступно календарей: {len(calendars)}")
        
        for cal in calendars[:5]:  # Показываем первые 5
            print(f"   - {cal['summary']}")
        
        if len(calendars) > 5:
            print(f"   ... и еще {len(calendars) - 5} календарей")
        
        print("\n🎉 Настройка завершена успешно!")
        print("Теперь вы можете использовать приложение.")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        print("\n🔧 Возможные решения:")
        print("1. Проверьте правильность credentials.json")
        print("2. Убедитесь, что Google Calendar API включен")
        print("3. Проверьте настройки OAuth consent screen")
        print("4. Добавьте ваш email в test users")
        return False

def check_credentials():
    """Проверка существующих credentials"""
    
    print("\n🔍 Проверка существующих credentials...")
    
    # Проверяем стандартные места хранения токенов
    token_paths = [
        os.path.expanduser('~/.credentials/'),
        os.path.expanduser('~/.config/google/'),
        './token.json'
    ]
    
    for path in token_paths:
        if os.path.exists(path):
            print(f"✅ Найдены credentials в: {path}")
            return True
    
    print("❌ Существующие credentials не найдены")
    return False

if __name__ == "__main__":
    print("🚀 Smart Calendar Assistant - Настройка авторизации")
    print("=" * 60)
    
    # Проверяем существующие credentials
    if check_credentials():
        print("\n💡 Обнаружены существующие credentials")
        response = input("Хотите настроить новые? (y/N): ")
        if response.lower() != 'y':
            print("✅ Используем существующие credentials")
            exit(0)
    
    # Настройка авторизации
    success = setup_google_auth()
    
    if success:
        print("\n📋 Следующие шаги:")
        print("1. Перезапустите приложение: docker-compose restart")
        print("2. Откройте http://localhost:8501")
        print("3. Нажмите 'Войти через Google'")
    else:
        print("\n❌ Настройка не завершена")
        print("См. файл GOOGLE_SETUP.md для подробных инструкций") 