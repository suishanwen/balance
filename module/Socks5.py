def open_socks():
    import socks
    import socket
    socks.set_default_proxy(socks.SOCKS5, "localhost", 1086)
    socket.socket = socks.socksocket
