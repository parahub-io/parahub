from django.conf import settings
from django.shortcuts import render
from django.contrib.auth.decorators import login_required


@login_required
def iot_devices_view(request):
    """Отображение страницы с IoT устройствами"""
    return render(request, 'iot_devices.html', {
        'traccar_public_host': settings.TRACCAR_PUBLIC_HOST,
    })