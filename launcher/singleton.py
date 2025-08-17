#!/usr/bin/env python3

from typing import Optional, Callable
from xdg_base_dirs import xdg_runtime_dir
import logging
import os
import socket
import tempfile
import threading

logger = logging.getLogger(__name__)


class SingletonManager:
    """Manages singleton behavior for the launcher application"""

    __slots__ = (
        "app_name",
        "socket_path",
        "server_socket",
        "show_callback",
        "rescan_callback",
        "server_thread",
        "_running",
    )

    def __init__(self, app_name: str = "launcher"):
        self.app_name = app_name
        uid = os.getuid()
        runtime_dir = xdg_runtime_dir()
        if runtime_dir and os.path.exists(runtime_dir):
            self.socket_path = os.path.join(runtime_dir, f"{app_name}-{uid}.sock")
        else:
            # Fallback for systems without XDG_RUNTIME_DIR
            self.socket_path = os.path.join(
                tempfile.gettempdir(), f"{app_name}-{uid}.sock"
            )
        self.server_socket: Optional[socket.socket] = None
        self.show_callback: Optional[Callable] = None
        self.rescan_callback: Optional[Callable] = None
        self.server_thread: Optional[threading.Thread] = None
        self._running = False

    def is_running(self) -> bool:
        """Check if another instance is already running"""
        if not os.path.exists(self.socket_path):
            return False

        try:
            client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client_socket.settimeout(0.05)
            client_socket.connect(self.socket_path)
            # Send a test message to make sure the server is responsive
            client_socket.send(b"PING")
            response = client_socket.recv(16)
            client_socket.close()
            return response == b"PONG"
        except (ConnectionRefusedError, FileNotFoundError, socket.timeout):
            # Socket file exists but no one is listening or not responsive - clean it up
            try:
                os.unlink(self.socket_path)
            except OSError:
                pass
            return False
        except Exception as e:
            logger.error(f"Error checking if instance is running: {e}")
            return False

    def send_show_command(self) -> bool:
        """Send show command to existing instance"""
        if not self.is_running():
            return False

        try:
            client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client_socket.settimeout(0.05)
            client_socket.connect(self.socket_path)
            client_socket.send(b"SHOW")
            response = client_socket.recv(16)
            client_socket.close()
            return response == b"OK"
        except Exception as e:
            logger.error(f"Error sending show command: {e}")
            return False

    def send_rescan_command(self, plugin_id: str = None) -> bool:
        """Send rescan command to existing instance"""
        if not self.is_running():
            return False

        try:
            client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client_socket.settimeout(0.05)
            client_socket.connect(self.socket_path)

            if plugin_id:
                client_socket.send(f"RESCAN:{plugin_id}".encode())
            else:
                client_socket.send(b"RESCAN")

            response = client_socket.recv(16)
            client_socket.close()
            return response == b"OK"
        except Exception as e:
            logger.error(f"Error sending rescan command: {e}")
            return False

    def start_server(
        self, show_callback: Callable, rescan_callback: Callable = None
    ) -> bool:
        """Start the singleton server to listen for show and rescan commands"""
        if self.is_running():
            logger.info("Another instance is already running")
            return False

        self.show_callback = show_callback
        self.rescan_callback = rescan_callback

        # Clean up any stale socket file
        try:
            os.unlink(self.socket_path)
        except OSError:
            pass

        try:
            self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server_socket.bind(self.socket_path)
            self.server_socket.listen(1)
            self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self.server_thread.start()
            self._running = True

            logger.info(f"Singleton server started on {self.socket_path}")
            return True

        except Exception as e:
            logger.error(f"Error starting singleton server: {e}")
            return False

    def _server_loop(self):
        """Server loop to handle incoming connections"""
        while self._running and self.server_socket:
            try:
                client_socket, address = self.server_socket.accept()
                try:
                    data = client_socket.recv(1024)
                    if data == b"SHOW" and self.show_callback:
                        # Call show callback on main thread
                        try:
                            from gi.repository import GLib

                            GLib.idle_add(self.show_callback)
                            client_socket.send(b"OK")
                        except ImportError:
                            # GLib not available, call directly
                            self.show_callback()
                            client_socket.send(b"OK")
                    elif data == b"RESCAN" and self.rescan_callback:
                        # Call rescan callback for all plugins
                        try:
                            from gi.repository import GLib

                            GLib.idle_add(lambda: self.rescan_callback())
                            client_socket.send(b"OK")
                        except ImportError:
                            self.rescan_callback()
                            client_socket.send(b"OK")
                    elif data.startswith(b"RESCAN:") and self.rescan_callback:
                        # Call rescan callback for specific plugin
                        plugin_id = data[7:].decode()  # Remove "RESCAN:" prefix
                        try:
                            from gi.repository import GLib

                            GLib.idle_add(lambda: self.rescan_callback(plugin_id))
                            client_socket.send(b"OK")
                        except ImportError:
                            self.rescan_callback(plugin_id)
                            client_socket.send(b"OK")
                    elif data == b"PING":
                        # Respond to ping to confirm we're alive
                        client_socket.send(b"PONG")
                    else:
                        client_socket.send(b"UNKNOWN")
                except Exception as e:
                    logger.error(f"Error handling client connection: {e}")
                finally:
                    client_socket.close()

            except OSError:
                # Socket was closed
                break
            except Exception as e:
                logger.error(f"Error in server loop: {e}")
                break

    def stop_server(self):
        """Stop the singleton server"""
        self._running = False

        # Force socket to close immediately to unblock accept()
        if self.server_socket:
            try:
                self.server_socket.shutdown(socket.SHUT_RDWR)
                self.server_socket.close()
            except Exception:
                pass
            self.server_socket = None

        # Join thread with shorter timeout since socket is already closed
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=0.1)

        # Clean up socket file
        try:
            os.unlink(self.socket_path)
        except OSError:
            pass

        logger.info("Singleton server stopped")
