import logging

logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] %(message)s',
                    datefmt='%m-%d %H:%M:%S',
                    filemode='a')

logger = logging.getLogger()
