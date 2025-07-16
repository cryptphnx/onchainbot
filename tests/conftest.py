"""
Global fixtures and patches for async tests.
"""
import socket

# Patch socketpair to avoid PermissionError in restricted environments
_orig_socketpair = socket.socketpair
def socketpair(family=None, type=socket.SOCK_STREAM, proto=0):
    try:
        return _orig_socketpair(family, type, proto)
    except (PermissionError, TypeError):
        # fallback to AF_INET sockets when AF_UNIX is not allowed
        sock1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        return sock1, sock2

socket.socketpair = socketpair
