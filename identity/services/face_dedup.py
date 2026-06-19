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


# Below this face-to-image height ratio we issue a soft quality warning:
# dlib embeddings degrade when the face is small, raising false-match risk.
# Not a hard block — dlib can still produce a usable embedding from small faces,
# and we'd rather not gate WoT verification on composition rules.
MIN_FACE_HEIGHT_RATIO = 0.15


def extract_embedding(image_bytes: bytes) -> tuple[np.ndarray, list[str]]:
    """
    Extract 128-d face embedding from image bytes.

    Returns (embedding, warnings). Warnings are non-blocking quality hints.
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

    warnings: list[str] = []
    top, right, bottom, left = face_locations[0]
    face_height = bottom - top
    image_height = image_array.shape[0]
    if image_height > 0 and face_height / image_height < MIN_FACE_HEIGHT_RATIO:
        warnings.append(
            "Face is small in the frame — embedding quality may be reduced, "
            "which can cause false matches against other profiles. "
            "A closer, sharper photo of your face will give the most reliable verification."
        )

    return encodings[0], warnings


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


# LSH (Locality-Sensitive Hashing) for approximately-stable face fingerprints.
#
# Why not SHA256(embedding): face embeddings are not byte-identical across photos
# of the same person — they drift in 128-d space (Euclidean distance ~0.3-0.5 for
# same face). A cryptographic hash of those bytes changes completely each upload,
# making the "fingerprint" useless as a recognizable biometric signature.
#
# LSH via random hyperplanes preserves similarity: P(bit match) = 1 - θ/π where θ is
# the angle between embeddings. For typical same-person pairs (cos≈0.85, θ≈32°),
# P(match per bit) ≈ 0.82. With 16 bits, most uploads of the same face produce
# fingerprints differing by 0-3 bits — visually recognizable as "the same".
# Different people typically share only ~8/16 bits (chance level).
#
# 16 bits = 65536 buckets. Enough for users to recognize their own fingerprint
# across re-uploads; not a unique identifier — uniqueness checks use the full
# 128-d embedding via check_duplicate().
_LSH_BITS = 16
_LSH_PROJECTIONS: np.ndarray | None = None


def _get_lsh_projections() -> np.ndarray:
    """Fixed random hyperplanes seeded for determinism across server restarts.

    Seed (42) MUST NOT change — every existing fingerprint depends on it.
    Changing the seed silently invalidates all previously-displayed fingerprints.
    """
    global _LSH_PROJECTIONS
    if _LSH_PROJECTIONS is None:
        rng = np.random.default_rng(42)
        _LSH_PROJECTIONS = rng.standard_normal((_LSH_BITS, 128))
    return _LSH_PROJECTIONS


def compute_face_fingerprint(embedding: np.ndarray) -> str:
    """16-bit LSH fingerprint of a face embedding, formatted as 'XX XX' hex.

    Approximately stable across photos of the same face — same person typically
    produces fingerprints differing by 0-3 bits (most hex chars unchanged).
    Different people produce fingerprints with no recognizable similarity.

    NOT cryptographic and NOT a unique identifier. It is a human-readable
    biometric signature designed for the user to recognize their own face across
    re-uploads. Uniqueness checks must use the full 128-d embedding.
    """
    projections = _get_lsh_projections()
    bits = (projections @ embedding) >= 0
    value = 0
    for b in bits:
        value = (value << 1) | int(b)
    hex_str = f"{value:04X}"
    return f"{hex_str[:2]} {hex_str[2:]}"


def face_fingerprint_from_bytes(embedding_bytes: bytes) -> str:
    """Convenience wrapper: deserialize stored bytes then fingerprint."""
    return compute_face_fingerprint(deserialize_embedding(embedding_bytes))


def fingerprint_hamming_distance(fp1: str, fp2: str) -> int:
    """Number of differing bits between two LSH fingerprints (0-16).

    Same-person interpretation:
      0-3 bits  → almost certainly same face
      4-7 bits  → ambiguous
      8+ bits   → different face
    """
    v1 = int(fp1.replace(' ', ''), 16)
    v2 = int(fp2.replace(' ', ''), 16)
    return bin(v1 ^ v2).count('1')
