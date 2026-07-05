"""
Сигналы для автоматической синхронизации с Traccar
Временное решение через прямое подключение к БД
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings
from django.db import transaction
import psycopg2
from psycopg2.extras import RealDictCursor
import logging

from parahub.background import spawn
from .models import IoTDevice

logger = logging.getLogger(__name__)

# Конфигурация базы Traccar (пароль читается из настроек/переменных окружения)
TRACCAR_DB = {
    'host': 'localhost',
    'port': 5433,
    'database': 'traccar',
    'user': 'traccar',
    'password': getattr(settings, 'TRACCAR_DB_PASSWORD', ''),
}

@receiver(post_save, sender=IoTDevice)
def sync_device_to_traccar(sender, instance, created, **kwargs):
    """Автоматически создает устройство в Traccar при создании в Parahub"""

    # Только для трекеров
    if instance.device_type != 'TRACKER':
        return

    # Если уже есть traccar_device_id, пропускаем
    if instance.traccar_device_id:
        return

    # Capture values for the deferred thread
    device_pk = instance.pk
    device_name = instance.name
    unique_id = instance.device_id or str(instance.id)

    def do_sync():
        conn = None
        try:
            conn = psycopg2.connect(**TRACCAR_DB)
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute(
                "SELECT id FROM tc_devices WHERE uniqueid = %s",
                (unique_id,)
            )
            existing = cur.fetchone()

            if existing:
                traccar_id = existing['id']
                logger.info(f"Device {device_name} found in Traccar with ID {traccar_id}")
            else:
                cur.execute(
                    """INSERT INTO tc_devices (name, uniqueid, status, lastupdate)
                       VALUES (%s, %s, 'offline', NOW()) RETURNING id""",
                    (device_name, unique_id)
                )
                new_device = cur.fetchone()
                traccar_id = new_device['id']

                cur.execute(
                    """INSERT INTO tc_user_device (userid, deviceid)
                       SELECT id, %s FROM tc_users
                       WHERE administrator = true OR email IN ('andrey.perliev@gmail.com')
                       ON CONFLICT DO NOTHING""",
                    (traccar_id,)
                )
                conn.commit()
                logger.info(f"Device {device_name} created in Traccar with ID {traccar_id}")

            cur.close()

            # Re-fetch device to avoid stale instance data
            try:
                device = IoTDevice.objects.get(pk=device_pk)
                device.traccar_device_id = traccar_id
                device.connection_info['traccar_device_id'] = traccar_id
                device.connection_info['traccar_unique_id'] = unique_id
                device.save(update_fields=['traccar_device_id', 'connection_info'])
            except IoTDevice.DoesNotExist:
                logger.warning(f"IoTDevice {device_pk} deleted before Traccar sync completed")

        except Exception as e:
            logger.error(f"Failed to sync device {device_name} to Traccar: {e}")
        finally:
            if conn:
                conn.close()

    transaction.on_commit(lambda: spawn(do_sync))

@receiver(post_delete, sender=IoTDevice)
def delete_device_from_traccar(sender, instance, **kwargs):
    """Удаляет устройство из Traccar при удалении из Parahub"""

    if not instance.traccar_device_id:
        return

    # Capture values for the deferred thread
    traccar_device_id = instance.traccar_device_id
    device_name = instance.name

    def do_delete():
        conn = None
        try:
            conn = psycopg2.connect(**TRACCAR_DB)
            cur = conn.cursor()

            cur.execute(
                "DELETE FROM tc_user_device WHERE deviceid = %s",
                (traccar_device_id,)
            )
            cur.execute(
                "DELETE FROM tc_positions WHERE deviceid = %s",
                (traccar_device_id,)
            )
            cur.execute(
                "DELETE FROM tc_devices WHERE id = %s",
                (traccar_device_id,)
            )

            conn.commit()
            cur.close()
            logger.info(f"Device {device_name} deleted from Traccar")

        except Exception as e:
            logger.error(f"Failed to delete device {device_name} from Traccar: {e}")
        finally:
            if conn:
                conn.close()

    transaction.on_commit(lambda: spawn(do_delete))