import datetime
import os
import time

from module.Logger import logger
from tool.xpl_monitor import monitor
from util.ServerUtil import get_today_ts

TASK_INI_FILE = "task.ini"


def load_task_status():
    """从 task.ini 加载任务状态"""
    task_status = {"h8": True}
    today_ts = get_today_ts()

    try:
        if os.path.exists(TASK_INI_FILE):
            import configparser
            config = configparser.ConfigParser()
            config.read(TASK_INI_FILE, encoding='utf-8')

            if 'task' in config:
                saved_ts = config.getint('task', 'today_ts', fallback=0)

                # 如果是同一天，读取已执行的任务
                if saved_ts == today_ts:
                    executed_hours = config.get('task', 'executed_hours', fallback='').split(',')
                    for hour in executed_hours:
                        if hour.strip():
                            task_status[hour.strip()] = False
                    logger.info(f"Loaded task status from {TASK_INI_FILE}, executed: {executed_hours}")
                else:
                    logger.info(f"New day detected (saved: {saved_ts}, current: {today_ts}), reset all tasks")
    except Exception as e:
        logger.warning(f"Failed to load task status: {e}")

    return task_status, today_ts


def save_task_status(today_ts, executed_hours):
    """保存任务状态到 task.ini"""
    try:
        import configparser
        config = configparser.ConfigParser()

        config['task'] = {
            'today_ts': str(today_ts),
            'executed_hours': ','.join(executed_hours)
        }

        with open(TASK_INI_FILE, 'w', encoding='utf-8') as f:
            config.write(f)
    except Exception as e:
        logger.warning(f"Failed to save task status: {e}")


def daily_task(task):
    try:
        task()
    except Exception as e:
        logger.warning(f"daily task failed: {e}")


def start_job():
    # 加载任务状态
    task, today_ts = load_task_status()
    executed_hours = [k for k in task if not task[k]]

    while True:
        hour = datetime.datetime.now().hour
        current_ts = get_today_ts()

        # 检查日期是否变化
        if current_ts > today_ts:
            logger.info("Day changed, resetting all tasks")
            for i in task:
                task[i] = True
            executed_hours = []
            today_ts = current_ts
            save_task_status(today_ts, executed_hours)

        k = f"h{hour}"
        if task.get(k):
            logger.info(f"Executing task: {k}")
            if k == 'h8':
                daily_task(monitor)

            # 标记任务已执行
            task[k] = False
            if k not in executed_hours:
                executed_hours.append(k)

            # 保存状态
            save_task_status(today_ts, executed_hours)
            logger.info(f"Task {k} completed, executed hours: {executed_hours}")

        time.sleep(10)
