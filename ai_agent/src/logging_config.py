# logging_config.py
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "standard": {"format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"},
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "stream": "ext://sys.stdout",  # force stdout
        },
    },
    "loggers": {
        "": {  # root logger (your app)
            "handlers": ["stdout"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn": {
            "handlers": ["stdout"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.error": {
            "handlers": ["stdout"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.access": {
            "handlers": ["stdout"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
