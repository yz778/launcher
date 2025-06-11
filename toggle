#!/usr/bin/env python3
import os
import socket
import sys


def get_launcher_dir():
    """Get the real launcher directory, resolving symlinks"""
    script_path = os.path.realpath(__file__)
    return os.path.dirname(script_path)


def get_python_executable():
    """Get the correct Python executable (venv if available, fallback to system)"""
    launcher_dir = get_launcher_dir()
    venv_python = os.path.join(launcher_dir, ".venv", "bin", "python")

    if os.path.exists(venv_python):
        return venv_python
    else:
        return sys.executable


def ultra_fast_toggle():
    """Ultra-fast toggle implementation with minimal overhead"""
    socket_path = "/tmp/launcher.sock"

    # Fastest possible check - just try to connect
    if os.path.exists(socket_path):
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(0.05)  # 50ms timeout
            sock.connect(socket_path)
            sock.send(b"SHOW")
            sock.recv(8)  # Just check for response
            sock.close()
            return  # Success - exit immediately
        except:
            pass  # Fall through to start launcher

    # No instance running, start the main launcher
    launcher_dir = get_launcher_dir()
    launcher_path = os.path.join(launcher_dir, "main.py")
    python_executable = get_python_executable()
    os.chdir(launcher_dir)
    os.execv(python_executable, [python_executable, launcher_path] + sys.argv[1:])


if __name__ == "__main__":
    ultra_fast_toggle()
