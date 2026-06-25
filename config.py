import os
from dotenv import load_dotenv

# Load environment variables from a .env file if present
load_dotenv()

# Groq API Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "your-key-here")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Toggle to use Mock LLM (realistic offline responses) or Real Groq LLM
USE_MOCK_LLM = os.getenv("USE_MOCK_LLM", "False").lower() in ("true", "1", "yes")

# Browser Settings
HEADLESS_BROWSER = os.getenv("HEADLESS_BROWSER", "True").lower() in ("true", "1", "yes")

# Logging Configuration
LOG_TO_FILE = os.getenv("LOG_TO_FILE", "True").lower() in ("true", "1", "yes")
LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
