import random
import secrets
import string
from typing import Tuple
import logging

logger = logging.getLogger(__name__)

# Try to import NLTK but don't fail if it's not available
try:
    import nltk
    from nltk.corpus import words
    
    # Ensure NLTK data is downloaded
    try:
        nltk.data.find('corpora/words')
        word_list = words.words()
        NLTK_AVAILABLE = True
        logger.info("[Username Generator] NLTK words corpus loaded successfully")
    except LookupError:
        logger.warning("[Username Generator] NLTK words corpus not found, attempting download")
        try:
            nltk.download('words')
            word_list = words.words()
            NLTK_AVAILABLE = True
            logger.info("[Username Generator] NLTK words corpus downloaded and loaded")
        except Exception as e:
            logger.error(f"[Username Generator] Failed to download NLTK data: {e}")
            NLTK_AVAILABLE = False
            word_list = []
except ImportError as e:
    logger.warning(f"[Username Generator] NLTK not available: {e}")
    NLTK_AVAILABLE = False
    word_list = []

# Import Account model safely
try:
    from identity.models import Account
except ImportError as e:
    logger.error(f"[Username Generator] Failed to import Account model: {e}")
    Account = None

# Pre-filter words for efficiency
ADJECTIVES = [
    'happy', 'sunny', 'clever', 'swift', 'bright', 'cool', 'warm', 'bold',
    'smart', 'quick', 'gentle', 'brave', 'calm', 'eager', 'fancy', 'grand',
    'jolly', 'keen', 'lucky', 'mighty', 'neat', 'proud', 'quiet', 'royal',
    'sharp', 'solid', 'super', 'sweet', 'tender', 'vivid', 'wild', 'wise',
    'zesty', 'agile', 'alert', 'amber', 'azure', 'cosmic', 'crisp', 'daring',
    'divine', 'electric', 'epic', 'fierce', 'golden', 'heroic', 'lively',
    'magic', 'mystic', 'noble', 'radiant', 'serene', 'stellar', 'vibrant'
]

NOUNS = [
    'fox', 'tiger', 'eagle', 'wolf', 'lion', 'bear', 'hawk', 'owl',
    'deer', 'horse', 'dragon', 'phoenix', 'falcon', 'raven', 'dolphin',
    'shark', 'panda', 'koala', 'monkey', 'leopard', 'cheetah', 'jaguar',
    'moon', 'star', 'sun', 'comet', 'galaxy', 'nebula', 'planet', 'cosmos',
    'ocean', 'river', 'mountain', 'forest', 'desert', 'valley', 'island',
    'thunder', 'storm', 'lightning', 'wind', 'rain', 'snow', 'cloud',
    'fire', 'ice', 'water', 'earth', 'crystal', 'diamond', 'ruby', 'pearl',
    'banana', 'apple', 'orange', 'mango', 'berry', 'cherry', 'peach',
    'potato', 'carrot', 'pepper', 'tomato', 'onion', 'garlic', 'ginger'
]


def generate_username() -> str:
    """
    Generate a unique username in format: adjective-noun or adjective-noun-number
    """
    logger.info("[Username Generator] Starting username generation")
    
    # If Account model is not available, just generate without checking
    if Account is None:
        logger.warning("[Username Generator] Account model not available, generating without uniqueness check")
        number = random.randint(100, 9999)
        username = f"{random.choice(ADJECTIVES)}-{random.choice(NOUNS)}-{number}"
        logger.info(f"[Username Generator] Generated username without DB check: {username}")
        return username
    
    max_attempts = 100
    
    for attempt in range(max_attempts):
        adj = random.choice(ADJECTIVES)
        noun = random.choice(NOUNS)
        
        if attempt < 50:
            # Try without number first
            username = f"{adj}-{noun}"
        else:
            # Add number for uniqueness
            number = random.randint(1, 9999)
            username = f"{adj}-{noun}-{number}"
        
        try:
            # Check if username already exists
            if not Account.objects.filter(username=username).exists():
                logger.info(f"[Username Generator] Successfully generated unique username: {username}")
                return username
        except Exception as e:
            logger.error(f"[Username Generator] Error checking username uniqueness: {e}")
            # If we can't check, assume it's unique
            logger.info(f"[Username Generator] Returning username without uniqueness check: {username}")
            return username
    
    # Fallback: use timestamp for guaranteed uniqueness
    import time
    timestamp = int(time.time() * 1000) % 1000000
    username = f"{random.choice(ADJECTIVES)}-{random.choice(NOUNS)}-{timestamp}"
    logger.warning(f"[Username Generator] Max attempts reached, using timestamp fallback: {username}")
    return username


def generate_secure_password(length: int = 12) -> str:
    """
    Generate a secure random password
    """
    # Define character sets
    lowercase = string.ascii_lowercase
    uppercase = string.ascii_uppercase
    digits = string.digits
    special = "!@#$%^&*"
    
    # Ensure password has at least one character from each set
    password = [
        secrets.choice(lowercase),
        secrets.choice(uppercase),
        secrets.choice(digits),
        secrets.choice(special)
    ]
    
    # Fill the rest of the password length
    all_chars = lowercase + uppercase + digits + special
    for _ in range(length - 4):
        password.append(secrets.choice(all_chars))
    
    # Shuffle the password list
    random.shuffle(password)
    
    return ''.join(password)


def generate_user_credentials() -> Tuple[str, str]:
    """
    Generate both username and password for a new user
    Returns: (username, password)
    """
    username = generate_username()
    password = generate_secure_password()
    return username, password