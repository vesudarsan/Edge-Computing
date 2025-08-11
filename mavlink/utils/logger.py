import logging
import sys

def setup_logger(name=None,log_level=logging.INFO):
   
    logger = logging.getLogger(name)
    if not logger.handlers:  # Avoid duplicate handlers
        logger.setLevel(log_level)

        formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')

        # Console handler
        #ch = logging.StreamHandler()
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatter)
        ch.setLevel(log_level)

        logger.addHandler(ch)

        logger.propagate = False

    return logger
