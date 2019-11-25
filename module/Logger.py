import logging

logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] %(message)s',
                    datefmt='%m-%d %H:%M:%S',
                    filemode='a')

logger = logging.getLogger()


def logger_join(*args):
    data = list(map(lambda x: str(x), args))
    msg = " ".join(data)
    logger.info(msg)
