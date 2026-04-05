from django.db import models
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwcrypto import jwk
import uuid
from django.utils import timezone


class RSAKeyPair(models.Model):
    """RSA Key pair for signing JWT tokens."""
    kid = models.CharField(max_length=64, unique=True, default=uuid.uuid4)
    private_key_pem = models.TextField()
    public_key_pem = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f"RSA Key {self.kid}"
    
    @classmethod
    def generate_keypair(cls):
        """Generate new RSA key pair."""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        return cls.objects.create(
            private_key_pem=private_pem.decode('utf-8'),
            public_key_pem=public_pem.decode('utf-8')
        )
    
    def get_jwk(self):
        """Get JWK representation of the public key."""
        key = jwk.JWK()
        key.import_key(self.public_key_pem.encode('utf-8'))
        return key
    
    def get_private_key(self):
        """Get private key object."""
        return serialization.load_pem_private_key(
            self.private_key_pem.encode('utf-8'),
            password=None
        )
    
    @classmethod
    def get_active_key(cls):
        """Get current active key for signing."""
        return cls.objects.filter(is_active=True).first()
    
    @classmethod
    def get_or_create_active_key(cls):
        """Get active key or create new one if none exists."""
        key = cls.get_active_key()
        if not key:
            key = cls.generate_keypair()
        return key
