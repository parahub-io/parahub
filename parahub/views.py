from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.http import HttpResponse
from django.core.cache import cache
import logging
import json

logger = logging.getLogger(__name__)


def landing_page(request):
    # Отображаем главную страницу для всех пользователей
    # Авторизованные пользователи увидят персонализированный контент
    context = {
        'user': request.user,
        'is_authenticated': request.user.is_authenticated
    }
    return render(request, 'landing.html', context)


def profile_view(request):
    # Временно убираем @login_required для демо-режима
    # @login_required будет восстановлен после интеграции с proper auth
    return render(request, 'profile.html', {
        'user': request.user if request.user.is_authenticated else None
    })


def direct_logout(request):
    """Direct logout without confirmation page"""
    logout(request)
    return redirect('landing')


def mobile_oauth_complete(request):
    """
    Called after OAuth finishes in the system browser.
    The user is authenticated here (session cookie set by allauth in Chrome).
    We generate JWT tokens, store them in Redis keyed by state, and show
    a "return to app" page. The app polls /api/v1/auth/mobile/poll/ to get them.
    """
    state = request.GET.get('state', '')
    if not state:
        return HttpResponse('Missing state parameter', status=400)

    cache_key = f"mobile_auth:{state}"
    pending = cache.get(cache_key)
    if pending != "pending":
        return HttpResponse('State expired or invalid', status=410)

    if not request.user.is_authenticated:
        # OAuth failed or user cancelled — clean up
        cache.delete(cache_key)
        return HttpResponse('Authentication failed. Please try again in the app.', status=401)

    # Generate JWT tokens for the authenticated user
    from parahub.auth import create_tokens_for_user
    tokens = create_tokens_for_user(request.user)

    # Check if this is a new OAuth user
    is_new_user = request.session.get('is_new_oauth_user', False)

    # Store tokens in Redis for the app to pick up
    result = {
        'status': 'complete',
        'access_token': tokens['access_token'],
        'refresh_token': tokens['refresh_token'],
        'expires_in': tokens['expires_in'],
        'user_id': str(request.user.id),
        'username': request.user.username,
        'is_new_user': is_new_user,
    }
    cache.set(cache_key, result, timeout=60)  # available for 60s

    logger.info(f"[MobileOAuth] Tokens ready for user {request.user.username}, state={state[:8]}...")

    # Simple HTML page telling user to return to the app
    html = '''<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Parahub</title>
<style>
  body{font-family:system-ui,sans-serif;display:flex;align-items:center;
       justify-content:center;min-height:100vh;margin:0;background:#fafafa;color:#333}
  .card{text-align:center;padding:2rem}
  .check{font-size:3rem;margin-bottom:1rem}
  p{color:#666;margin-top:.5rem}
</style>
</head><body>
<div class="card">
  <div class="check">&#10003;</div>
  <h2>Authentication successful</h2>
  <p>You can close this tab and return to the app.</p>
</div>
</body></html>'''
    return HttpResponse(html)