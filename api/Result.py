import json


class Result(object):
    def __init__(self, status, msg, data=None):
        self.status = status
        self.msg = msg
        self.data = data

    def response(self):
        return json.dumps(self.__dict__).encode('utf-8')
