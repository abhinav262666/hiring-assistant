import logging
import logging.config
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from qdrant_client import QdrantClient
import mongoengine


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # Required environment variables
    openai_api_key: str
    eleven_labs_api_key: str
    mistral_api_key: str
    mongo_url: str
    qdrant_url: str
    embedding_model: str
    DENSE_VECTOR_SIZE: str
    litellm_proxy_url: str
    litellm_proxy_api_key: str

    # Logging configuration
    log_level: str = "INFO"
    log_dir: str = "logs"

    def setup_loggers(self):
        """Setup centralized loggers for different components"""
        # Create logs directory if it doesn't exist
        Path(self.log_dir).mkdir(exist_ok=True)

        # Logging configuration
        log_config = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "detailed": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                },
                "simple": {"format": "[%(levelname)s] %(message)s"},
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "simple",
                    "level": self.log_level,
                },
                "backend_file": {
                    "class": "logging.FileHandler",
                    "filename": f"{self.log_dir}/backend.log",
                    "formatter": "detailed",
                    "level": self.log_level,
                },
                "db_file": {
                    "class": "logging.FileHandler",
                    "filename": f"{self.log_dir}/database.log",
                    "formatter": "detailed",
                    "level": self.log_level,
                },
                "ai_file": {
                    "class": "logging.FileHandler",
                    "filename": f"{self.log_dir}/ai_agents.log",
                    "formatter": "detailed",
                    "level": self.log_level,
                },
            },
            "loggers": {
                "backend": {
                    "handlers": ["console", "backend_file"],
                    "level": self.log_level,
                    "propagate": False,
                },
                "database": {
                    "handlers": ["console", "db_file"],
                    "level": self.log_level,
                    "propagate": False,
                },
                "ai_agents": {
                    "handlers": ["console", "ai_file"],
                    "level": self.log_level,
                    "propagate": False,
                },
            },
        }

        # Apply configuration
        logging.config.dictConfig(log_config)

        # Create logger instances
        self.backend_logger = logging.getLogger("backend")
        self.db_logger = logging.getLogger("database")
        self.ai_logger = logging.getLogger("ai_agents")

        # Initialize database clients as None (will be set during app startup)
        self.mongo_client = None
        self.qdrant_client = None

    def initialize_databases(self):
        """Initialize MongoDB and Qdrant database connections"""
        try:
            # Initialize MongoEngine
            mongoengine.connect(host=self.mongo_url)
            self.mongo_client = mongoengine.connection.get_connection()
            self.db_logger.info("✅ MongoDB connection established successfully")

            # Initialize Qdrant client
            self.qdrant_client = QdrantClient(url=self.qdrant_url)
            # Test connection
            self.qdrant_client.get_collections()
            self.db_logger.info("✅ Qdrant connection established successfully")

        except Exception as e:
            self.db_logger.error(f"❌ Database initialization failed: {e}")
            raise


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
