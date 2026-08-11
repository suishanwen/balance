import base64
import fcntl
import hashlib
import os
import threading
from contextlib import contextmanager

from cryptography.fernet import Fernet

FERNET_PREFIX = 'FN:'
_process_file_lock = threading.RLock()


def _get_fernet():
    key = os.environ.get("MARTIN_FERNET_KEY", "")
    if not key:
        raise RuntimeError("MARTIN_FERNET_KEY 未配置")
    fernet_key = base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
    return Fernet(fernet_key)


@contextmanager
def exclusive_file_lock(path):
    """通过进程内锁和 flock 串行化同一密钥文件的完整读写事务"""
    with _process_file_lock:
        with open(f"{path}.lock", 'a') as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def get_enc(path):
    with open(path, 'r') as f:
        plaintext = f.read().encode('utf-8')
        return FERNET_PREFIX + _get_fernet().encrypt(plaintext).decode('utf-8')


def get_dec(path):
    with open(path, 'r') as f:
        data = f.read()
        if data.startswith(FERNET_PREFIX):
            return _get_fernet().decrypt(data[len(FERNET_PREFIX):].encode('utf-8')).decode('utf-8')
        return data


def write(code, path):
    try:
        with open(path, 'w') as f:
            f.write(code)
    except Exception as e:
        print(str(e))


def encrypt_f(path):
    write(get_enc(path), path)


def decrypt_f(path):
    write(get_dec(path), path)
