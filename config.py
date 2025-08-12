import os
from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings(BaseSettings):
    """Application settings and configuration."""
    
    # Application
    app_name: str = "MeetMate"
    app_version: str = "1.0.0"
    debug: bool = os.getenv("DEBUG", "False").lower() == "true"
    secret_key: str = os.getenv("SECRET_KEY", "your-secret-key-here")
    
    # OpenAI Configuration
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    
    # Google Calendar API
    google_calendar_credentials_path: str = os.getenv("GOOGLE_CALENDAR_CREDENTIALS_PATH", "credentials/google_calendar.json")
    google_calendar_token_path: str = os.getenv("GOOGLE_CALENDAR_TOKEN_PATH", "credentials/google_token.json")
    
    # Microsoft Graph API (for Outlook)
    microsoft_client_id: str = os.getenv("MICROSOFT_CLIENT_ID", "")
    microsoft_client_secret: str = os.getenv("MICROSOFT_CLIENT_SECRET", "")
    microsoft_tenant_id: str = os.getenv("MICROSOFT_TENANT_ID", "")
    
    # AssemblyAI
    assemblyai_api_key: str = os.getenv("ASSEMBLYAI_API_KEY", "")
    
    # Database Configuration
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./meetmate.db")
    database_host: str = os.getenv("DATABASE_HOST", "localhost")
    database_port: int = int(os.getenv("DATABASE_PORT", "5432"))
    database_name: str = os.getenv("DATABASE_NAME", "meetmate_db")
    database_user: str = os.getenv("DATABASE_USER", "")
    database_password: str = os.getenv("DATABASE_PASSWORD", "")
    
    # Email Configuration
    smtp_server: str = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    email_username: str = os.getenv("EMAIL_USERNAME", "")
    email_password: str = os.getenv("EMAIL_PASSWORD", "")
    email_from: str = os.getenv("EMAIL_FROM", "")
    
    # File Storage
    upload_directory: str = os.getenv("UPLOAD_DIRECTORY", "uploads/")
    temp_directory: str = os.getenv("TEMP_DIRECTORY", "temp/")
    export_directory: str = os.getenv("EXPORT_DIRECTORY", "exports/")
    
    # Meeting Settings
    default_meeting_duration: int = int(os.getenv("DEFAULT_MEETING_DURATION", "60"))
    buffer_time: int = int(os.getenv("BUFFER_TIME", "15"))
    max_meeting_duration: int = int(os.getenv("MAX_MEETING_DURATION", "480"))
    
    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "extra": "ignore"
    }

# Global settings instance
settings = Settings()

# Create necessary directories
def create_directories():
    """Create necessary directories if they don't exist."""
    directories = [
        settings.upload_directory,
        settings.temp_directory,
        settings.export_directory,
        "credentials",
        "logs"
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)

# Initialize directories when module is imported
create_directories() 