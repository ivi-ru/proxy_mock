import logging


def configure_logger():
    uvicorn_logger = logging.getLogger("uvicorn")
    logger = uvicorn_logger.getChild("proxy_mock")

    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
    for handler in uvicorn_logger.handlers:
        handler.setFormatter(formatter)

    logger.setLevel(logging.DEBUG)
    return logger


app_logger = configure_logger()
