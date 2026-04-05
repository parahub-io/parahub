"""
Face deduplication service for WoT Sybil defense.

Uses face_recognition (dlib) to extract 128-dimensional face embeddings
and compare them for duplicate detection across verified profiles.
"""

import hashlib
import logging

import numpy as np

logger = logging.getLogger(__name__)

# Euclidean distance threshold: < 0.6 = same person (dlib standard)
SIMILARITY_THRESHOLD = 0.6

# If old vs new embedding distance > this, photo changed significantly
RECONFIRMATION_THRESHOLD = 0.4


def extract_embedding(image_bytes: bytes) -> np.ndarray | None:
    """
    Extract 128-d face embedding from image bytes.

    Returns None if no face or multiple faces detected.
    Raises ValueError with descriptive message on error.
    """
    import face_recognition

    image_array = face_recognition.load_image_file(
        __import__('io').BytesIO(image_bytes)
    )

    face_locations = face_recognition.face_locations(image_array, model='hog')

    if len(face_locations) == 0:
        raise ValueError("No face detected in the photo. Please upload a clear photo of your face.")

    if len(face_locations) > 1:
        raise ValueError("Multiple faces detected. Please upload a photo with only your face.")

    encodings = face_recognition.face_encodings(image_array, face_locations)
    if not encodings:
        raise ValueError("Could not extract face features. Please try a different photo.")

    return encodings[0]


def serialize_embedding(embedding: np.ndarray) -> bytes:
    """numpy float64 array -> float32 bytes for BinaryField (512 bytes)."""
    return embedding.astype(np.float32).tobytes()


def deserialize_embedding(data: bytes) -> np.ndarray:
    """BinaryField bytes -> numpy float64 array."""
    return np.frombuffer(data, dtype=np.float32).astype(np.float64)


def embedding_distance(emb1: bytes, emb2: bytes) -> float:
    """Euclidean distance between two serialized embeddings."""
    a = deserialize_embedding(emb1)
    b = deserialize_embedding(emb2)
    return float(np.linalg.norm(a - b))


def check_duplicate(new_embedding_bytes: bytes, exclude_profile_id: str = None) -> dict | None:
    """
    Check if face embedding matches any existing verified profile.

    Returns {"profile_id": str, "distance": float} of closest match
    if distance < SIMILARITY_THRESHOLD, else None.
    """
    from identity.models import ProfileVerificationPhoto

    qs = ProfileVerificationPhoto.objects.filter(
        profile__is_verified_wot=True,
        biometric_consent=True,
    ).exclude(
        face_embedding=b''
    ).select_related('profile')

    if exclude_profile_id:
        qs = qs.exclude(profile_id=exclude_profile_id)

    # Also exclude profiles from the same account (own pseudonymous profiles)
    if exclude_profile_id:
        from identity.models import Profile
        try:
            account_id = Profile.objects.filter(id=exclude_profile_id).values_list('account_id', flat=True).first()
            if account_id:
                qs = qs.exclude(profile__account_id=account_id)
        except Exception:
            pass

    new_emb = deserialize_embedding(new_embedding_bytes)
    closest = None
    min_distance = float('inf')

    for vp in qs.iterator():
        try:
            existing_emb = deserialize_embedding(bytes(vp.face_embedding))
            dist = float(np.linalg.norm(new_emb - existing_emb))
            if dist < min_distance:
                min_distance = dist
                closest = vp
        except Exception as e:
            logger.warning(f"Failed to compare embedding for profile {vp.profile_id}: {e}")
            continue

    if closest and min_distance < SIMILARITY_THRESHOLD:
        logger.warning(
            f"Face duplicate detected: distance={min_distance:.4f}, "
            f"matched profile={closest.profile_id}"
        )
        return {"profile_id": closest.profile_id, "distance": min_distance}

    return None


def is_significant_change(old_embedding: bytes, new_embedding: bytes) -> bool:
    """True if embeddings differ enough to require re-confirmation."""
    dist = embedding_distance(old_embedding, new_embedding)
    return dist > RECONFIRMATION_THRESHOLD


def compute_photo_hash(image_bytes: bytes) -> str:
    """SHA256 hash of photo bytes."""
    return hashlib.sha256(image_bytes).hexdigest()
