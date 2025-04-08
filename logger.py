import logging
from datetime import datetime
import json
from functools import lru_cache



class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "logger_name": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_record['exc_info'] = self.formatException(record.exc_info)
        if hasattr(record, 'extra_data') and isinstance(record.extra_data, dict):
            log_record.update(record.extra_data)

        return json.dumps(log_record)
    


log_handler  = logging.StreamHandler()
log_handler.setFormatter(JsonFormatter())



logger = logging.getLogger("visitorbook")
logger.addHandler(log_handler)
logger.setLevel(logging.INFO)

logger.propagate = False


@lru_cache()
def get_logger(name):
    """
    Returns a logger with the specified name.
    """
    logger = logging.getLogger(name)
    logger.addHandler(log_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger