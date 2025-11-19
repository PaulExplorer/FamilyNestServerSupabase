from dotenv import load_dotenv
import os

load_dotenv()

from app import create_app

app = create_app()

is_dev = os.environ.get("ENV", "production") == "development"

if __name__ == "__main__":
    app.run(port=3000, debug=is_dev, host="0.0.0.0")
