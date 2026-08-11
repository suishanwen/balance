import io
import os
import stat
import threading


# 同步保护行情配置更新和原子发布，确保交易进程读取到当前 tick 的完整快照
market_lock = threading.RLock()


def write_snapshot(config, path):
    """同步写入完整行情快照，并通过原子替换避免读方看到半文件"""
    with market_lock:
        buffer = io.StringIO()
        config.write(buffer)
        temp_path = f"{path}.tmp"
        try:
            file_mode = stat.S_IMODE(os.stat(path).st_mode)
        except FileNotFoundError:
            file_mode = None
        with open(temp_path, "w") as file:
            file.write(buffer.getvalue())
        if file_mode is not None:
            os.chmod(temp_path, file_mode)
        os.replace(temp_path, path)
