from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os
import logging
import logging.config
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Required environment variables
    openai_api_key: str
    eleven_labs_api_key: str
    mistral_api_key: str
    mongo_url: str
    qdrant_url: str

    # Logging configuration
    log_level: str = "INFO"
    log_dir: str = "logs"

    def setup_loggers(self):
        """Setup centralized loggers for different components"""
        # Create logs directory if it doesn't exist
        Path(self.log_dir).mkdir(exist_ok=True)

        # Logging configuration
        log_config = {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'detailed': {
                    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                },
                'simple': {
                    'format': '[%(levelname)s] %(message)s'
                }
            },
            'handlers': {
                'console': {
                    'class': 'logging.StreamHandler',
                    'formatter': 'simple',
                    'level': self.log_level,
                },
                'backend_file': {
                    'class': 'logging.FileHandler',
                    'filename': f'{self.log_dir}/backend.log',
                    'formatter': 'detailed',
                    'level': self.log_level,
                },
                'db_file': {
                    'class': 'logging.FileHandler',
                    'filename': f'{self.log_dir}/database.log',
                    'formatter': 'detailed',
                    'level': self.log_level,
                },
                'ai_file': {
                    'class': 'logging.FileHandler',
                    'filename': f'{self.log_dir}/ai_agents.log',
                    'formatter': 'detailed',
                    'level': self.log_level,
                },
            },
            'loggers': {
                'backend': {
                    'handlers': ['console', 'backend_file'],
                    'level': self.log_level,
                    'propagate': False,
                },
                'database': {
                    'handlers': ['console', 'db_file'],
                    'level': self.log_level,
                    'propagate': False,
                },
                'ai_agents': {
                    'handlers': ['console', 'ai_file'],
                    'level': self.log_level,
                    'propagate': False,
                },
            },
        }

        # Apply configuration
        logging.config.dictConfig(log_config)

        # Create logger instances
        self.backend_logger = logging.getLogger('backend')
        self.db_logger = logging.getLogger('database')
        self.ai_logger = logging.getLogger('ai_agents')


# Create a global instance that validates on import
try:
    senv = Settings()
except Exception as e:
    print(f"❌ Environment validation failed: {e}")
    print("Please ensure all required environment variables are set:")
    print("- OPENAI_API_KEY")
    print("- ELEVEN_LABS_API_KEY")
    print("- MISTRAL_API_KEY")
    print("- MONGO_URL")
    print("- QDRANT_URL")
    raise SystemExit(1)
