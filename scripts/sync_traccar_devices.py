#!/usr/bin/env python
"""
Скрипт для ручной синхронизации устройств между Parahub и Traccar
Временное решение пока API аутентификация не исправлена
"""

import os
import sys
import django
import psycopg2
from psycopg2.extras import RealDictCursor

# Настройка Django
sys.path.append('/opt/parahub')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'parahub.settings')
django.setup()

from iot.models import IoTDevice

# Подключение к базе Traccar
from django.conf import settings as django_settings

TRACCAR_DB = {
    'host': 'localhost',
    'port': 5435,
    'database': 'traccar',
    'user': 'traccar',
    'password': django_settings.TRACCAR_DB_PASSWORD,
}

def sync_devices():
    """Синхронизирует все устройства без traccar_device_id"""
    
    # Подключаемся к базе Traccar
    conn = psycopg2.connect(**TRACCAR_DB)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Получаем устройства без traccar_device_id
    devices = IoTDevice.objects.filter(
        device_type='TRACKER',
        traccar_device_id__isnull=True
    )
    
    print(f"Найдено {devices.count()} устройств для синхронизации")
    
    for device in devices:
        unique_id = device.device_id or str(device.id)
        
        # Проверяем, есть ли уже в Traccar
        cur.execute(
            "SELECT id FROM tc_devices WHERE uniqueid = %s",
            (unique_id,)
        )
        existing = cur.fetchone()
        
        if existing:
            # Устройство уже есть, обновляем ID
            device.traccar_device_id = existing['id']
            device.connection_info['traccar_device_id'] = existing['id']
            device.connection_info['traccar_unique_id'] = unique_id
            device.save()
            print(f"✓ {device.name}: найдено в Traccar с ID {existing['id']}")
        else:
            # Создаем новое устройство
            cur.execute(
                """INSERT INTO tc_devices (name, uniqueid, status, lastupdate) 
                   VALUES (%s, %s, 'offline', NOW()) RETURNING id""",
                (device.name, unique_id)
            )
            new_device = cur.fetchone()
            device_id = new_device['id']
            
            # Привязываем к пользователям
            cur.execute(
                """INSERT INTO tc_user_device (userid, deviceid) 
                   SELECT id, %s FROM tc_users 
                   WHERE email IN ('admin@localhost', 'andrey.perliev@gmail.com')
                   ON CONFLICT DO NOTHING""",
                (device_id,)
            )
            
            # Обновляем в Parahub
            device.traccar_device_id = device_id
            device.connection_info['traccar_device_id'] = device_id
            device.connection_info['traccar_unique_id'] = unique_id
            device.save()
            
            conn.commit()
            print(f"✓ {device.name}: создано в Traccar с ID {device_id}")
    
    cur.close()
    conn.close()
    print("Синхронизация завершена")

if __name__ == '__main__':
    sync_devices()