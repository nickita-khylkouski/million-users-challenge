import socket, struct, threading, time
ls = socket.socket(); ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
ls.bind(("127.0.0.1", 8099)); ls.listen(4)
def server():
    c, _ = ls.accept()
    time.sleep(0.5)                 # let data arrive first
    c.recv(100)
    time.sleep(0.3)                 # then wait, like a stalled worker that read late
    info = c.getsockopt(socket.IPPROTO_TCP, socket.TCP_INFO, 256)
    print("optlen", len(info), "tcpi_last_data_recv(ms)", struct.unpack_from("<I", info, 52)[0],
          "tcpi_last_data_sent", struct.unpack_from("<I", info, 44)[0])
    c.close()
t = threading.Thread(target=server); t.start()
cs = socket.socket(); cs.connect(("127.0.0.1", 8099))
time.sleep(0.1); cs.sendall(b"x" * 50)
t.join(); cs.close(); ls.close()
