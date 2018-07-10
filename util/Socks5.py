import socks
import socket


def open_socks():
    socks.set_default_proxy(socks.SOCKS5, "localhost", 1086)
    socket.socket = socks.socksocket
