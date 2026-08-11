from util.ServerUtil import get_ms

ALIVE_USERS = {}


def keep_user_alive(user):
    ALIVE_USERS[user] = {'version': get_ms()}


def compare_ts(now, version):
    return now - version < 15 * 1000


def is_user_alive(user):
    user_info = ALIVE_USERS.get(user)
    if user_info is None:
        return False
    version = user_info['version']
    now = get_ms()
    return compare_ts(now, version)


def get_alive_users():
    users = []
    now = get_ms()
    for user in ALIVE_USERS:
        if compare_ts(now, ALIVE_USERS.get(user).get('version')):
            users.append({'user': user, 'version': ALIVE_USERS.get(user).get('version')})
    return users
