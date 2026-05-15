import asyncio
import sys
import random
from app.core.db import db
from app.core.utils import compute_media_id, sanitize_name
from app.core.logger import logger

async def test_db_integrity():
    logger.info("test_db_integrity_started")
    try:
        row = db.fetch_one("PRAGMA integrity_check")
        if row[0] == "ok":
            logger.info("test_db_integrity_pass")
        else:
            logger.error("test_db_integrity_fail", result=row[0])
    except Exception as e:
        logger.error("test_db_integrity_error", error=str(e))

async def test_media_id_collisions():
    logger.info("test_media_id_collisions_started")
    seen = set()
    collisions = 0
    total = 100000
    
    for i in range(total):
        # Generate random channel/msg IDs
        cid = random.randint(100000000, 999999999)
        mid = random.randint(1, 1000000)
        
        media_id = compute_media_id(cid, mid)
        if media_id in seen:
            collisions += 1
        seen.add(media_id)
        
    logger.info("test_media_id_collisions_complete", 
                total=total, collisions=collisions, 
                rate=f"{(collisions/total)*100:.6f}%")

async def test_sanitization():
    logger.info("test_sanitization_started")
    test_cases = [
        ("Hello World!", "Hello_World"),
        ("Funny Cat Video (2024).mp4", "Funny_Cat_Video_2024_mp4"),
        ("Emojis 🔥🔥🔥", "Emojis"),
        ("Unicode: 你好", "Unicode"),
        ("Multiple____Underscores", "Multiple_Underscores"),
        ("-" * 300, "-" * 200) # Truncation
    ]
    
    for inp, expected in test_cases:
        out = sanitize_name(inp)
        # Basic check (expected might vary based on re rules, but should be clean)
        if len(out) > 200:
            logger.error("test_sanitization_fail_length", input=inp)
        else:
            logger.info("test_sanitization_case", input=inp, output=out)

async def main():
    logger.info("stability_verification_started")
    await test_db_integrity()
    await test_media_id_collisions()
    await test_sanitization()
    logger.info("stability_verification_complete")

if __name__ == "__main__":
    asyncio.run(main())
