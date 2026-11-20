
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import cloudinary
import cloudinary.api
import cloudinary.uploader

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"


def check_cloudinary():
    if not ENV_FILE.exists():
        print("[ERROR] .env file not found:", ENV_FILE)
        return False

    # Load .env values, overriding old environment variables
    load_dotenv(ENV_FILE, override=True)

    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
    api_key = os.getenv("CLOUDINARY_API_KEY")
    api_secret = os.getenv("CLOUDINARY_API_SECRET")

    if not all([cloud_name, api_key, api_secret]):
        print("[ERROR] Missing Cloudinary credentials.")
        print("Check CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY,")
        print("and CLOUDINARY_API_SECRET in your .env file.")
        return False

    if os.getenv("CLOUDINARY_URL"):
        print("[WARNING] CLOUDINARY_URL is also configured.")
        print("This script ignores it. Remove it from .env and Render.")

    cloudinary.config(
        cloud_name=cloud_name.strip(),
        api_key=api_key.strip(),
        api_secret=api_secret.strip(),
        secure=True,
    )

    print("[INFO] Cloud Name:", cloud_name)
    print("[INFO] API Key configured:", bool(api_key))
    print("[INFO] API Secret configured:", bool(api_secret))

    try:
        result = cloudinary.api.ping(timeout=30)
        print("[SUCCESS] Cloudinary connection successful!")
        print(result)
        return True

    except Exception as error:
        print("[ERROR] Cloudinary connection failed:")
        print(str(error).replace(api_secret, "[REDACTED]")
              .replace(api_key, "[REDACTED]"))
        return False


if __name__ == "__main__":
    success = check_cloudinary()
    sys.exit(0 if success else 1)
