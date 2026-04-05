"""
JWT authentication helpers for Parahub
"""

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from typing import Optional

Account = get_user_model()


def verify_jwt_token(token: str) -> Optional[Account]:
    """
    Verify a JWT token and return the associated user
    """
    try:
        # Decode the JWT token
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=['HS256'],
            options={"verify_exp": True}
        )
        
        # Get user ID from payload
        user_id = payload.get('user_id')
        if not user_id:
            return None
        
        # Get the user
        try:
            user = Account.objects.get(id=user_id)
            return user
        except Account.DoesNotExist:
            return None
            
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, jwt.DecodeError):
        return None