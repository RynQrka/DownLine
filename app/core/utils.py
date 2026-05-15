import hashlib
import re
import unicodedata

BASE62_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

def encode_base62(n: int) -> str:
    """Encodes a positive integer to Base62."""
    if n == 0:
        return BASE62_ALPHABET[0]
    
    arr = []
    while n:
        n, rem = divmod(n, 62)
        arr.append(BASE62_ALPHABET[rem])
    arr.reverse()
    return ''.join(arr)

def compute_media_id(channel_id: int, message_id: int) -> str:
    """
    Computes a deterministic 8-character Media ID.
    Formula: SHA256("{channel_id}:{message_id}") -> Base62 -> first 8 chars.
    """
    token = f"{channel_id}:{message_id}".encode()
    hash_hex = hashlib.sha256(token).hexdigest()
    
    # Convert hex hash to integer
    hash_int = int(hash_hex, 16)
    
    # Encode to Base62 and take first 8
    full_id = encode_base62(hash_int)
    return full_id[:8]

def sanitize_name(name: str) -> str:
    """
    Sanitizes a string for use as a filename or directory.
    - Normalizes Unicode to NFKD (separates accents).
    - Encodes to ASCII, ignoring non-ASCII characters.
    - Removes non-alphanumeric (except _ and -).
    - Truncates to 200 chars.
    """
    if not name:
        return "unknown"
    
    # Unicode normalization and ASCII transliteration
    name = unicodedata.normalize('NFKD', name)
    name = name.encode('ascii', 'ignore').decode('ascii')
    
    # Replace non-alphanumeric with underscore
    name = re.sub(r'[^a-zA-Z0-9_\-]', '_', name)
    # Collapse multiple underscores
    name = re.sub(r'_+', '_', name)
    # Strip leading/trailing underscores
    name = name.strip('_')
    
    return name[:200] or "unknown"
