import configparser
import datetime
import os
import time

from module.Logger import logger

LOGIN_FAILURE_PATH = "login_failures.ini"
MAX_LOGIN_ATTEMPTS = 3
LOCKOUT_DURATION = 86400


def _safe_get(config, section, option, default=''):
    try:
        return config.get(section, option)
    except Exception:
        return default


def get_client_ip():
    from flask import request
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    else:
        return request.remote_addr


def get_login_failures():
    if not os.path.exists(LOGIN_FAILURE_PATH):
        return {}
    failure_config = configparser.ConfigParser()
    failure_config.read(LOGIN_FAILURE_PATH)
    failures = {}
    for section in failure_config.sections():
        failures[section] = {
            'count': int(_safe_get(failure_config, section, 'count', '0')),
            'last_attempt': float(_safe_get(failure_config, section, 'last_attempt', '0')),
            'locked_until': float(_safe_get(failure_config, section, 'locked_until', '0'))
        }
    return failures


def save_login_failures(failures):
    failure_config = configparser.ConfigParser()
    for key, data in failures.items():
        if not failure_config.has_section(key):
            failure_config.add_section(key)
        failure_config.set(key, 'count', str(data['count']))
        failure_config.set(key, 'last_attempt', str(data['last_attempt']))
        failure_config.set(key, 'locked_until', str(data['locked_until']))
    with open(LOGIN_FAILURE_PATH, "w") as fp:
        failure_config.write(fp)


def is_locked(key, failures):
    if key not in failures:
        return False
    current_time = time.time()
    locked_until = failures[key]['locked_until']
    if locked_until > current_time:
        return True
    if locked_until > 0 and locked_until <= current_time:
        failures[key]['count'] = 0
        failures[key]['locked_until'] = 0
        save_login_failures(failures)
    return False


def record_login_failure(user, ip):
    failures = get_login_failures()
    current_time = time.time()
    user_key = f"user_{user}"
    ip_key = f"ip_{ip}"

    if user_key not in failures:
        failures[user_key] = {'count': 0, 'last_attempt': 0, 'locked_until': 0}
    failures[user_key]['count'] += 1
    failures[user_key]['last_attempt'] = current_time

    if ip_key not in failures:
        failures[ip_key] = {'count': 0, 'last_attempt': 0, 'locked_until': 0}
    failures[ip_key]['count'] += 1
    failures[ip_key]['last_attempt'] = current_time

    locked_keys = []
    if failures[user_key]['count'] >= MAX_LOGIN_ATTEMPTS:
        failures[user_key]['locked_until'] = current_time + LOCKOUT_DURATION
        locked_keys.append(('user', user))
    if failures[ip_key]['count'] >= MAX_LOGIN_ATTEMPTS:
        failures[ip_key]['locked_until'] = current_time + LOCKOUT_DURATION
        locked_keys.append(('ip', ip))

    save_login_failures(failures)
    if locked_keys:
        _send_lockout_notification(locked_keys, user, ip)
    return locked_keys


def _send_lockout_notification(locked_keys, user, ip):
    notification_user = os.environ.get("MARTIN_NOTIFICATION_USER", "")
    if not notification_user:
        return
    try:
        from util.ServerUtil import get_api
        message_api = get_api(notification_user, 0)
        lock_info = ", ".join(f"{lt[0]}: {lt[1]}" for lt in locked_keys)
        message = (
            f"🔒 Security Alert: Login Lockout\n\n"
            f"User: {user}\nIP: {ip}\nLocked: {lock_info}\n"
            f"Duration: 24 hours\n"
            f"Reason: {MAX_LOGIN_ATTEMPTS} consecutive failed login attempts\n"
            f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        message_api.send(message, is_report=True)
        logger.warning(f"Lockout notification sent for {lock_info}")
    except Exception as e:
        logger.error(f"Failed to send lockout notification: {str(e)}")


def reset_login_failures(user):
    failures = get_login_failures()
    user_key = f"user_{user}"
    if user_key in failures:
        failures[user_key]['count'] = 0
        failures[user_key]['locked_until'] = 0
        save_login_failures(failures)
