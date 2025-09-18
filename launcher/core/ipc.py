import logging
import os
import socket
import tempfile
import threading
from typing import Callable, Optional

from gi.repository import GLib
from xdg_base_dirs import xdg_runtime_dir

logger = logging.getLogger(__name__)


class IPCManager:
    """
    Unified IPC and Singleton Manager.

    Handles singleton enforcement by checking for a running instance and provides
    a generic command interface for IPC.
    """

    def __init__(self, app_name: str = "launcher"):
        self.app_name = app_name
        self.socket_path = self._get_socket_path(app_name)
        self.server_socket: Optional[socket.socket] = None
        self.server_thread: Optional[threading.Thread] = None
        self._running = False
        self.handlers = {}

    @staticmethod
    def _get_socket_path(app_name: str) -> str:
        """Construct the path for the IPC socket."""
        runtime_dir = xdg_runtime_dir()
        sockname = f"{app_name}.sock"
        if runtime_dir and os.path.exists(runtime_dir):
            return os.path.join(runtime_dir, sockname)
        # Fallback for systems without XDG_RUNTIME_DIR
        return os.path.join(tempfile.gettempdir(), sockname)

    def register_handler(self, command: str, handler: Callable):
        """
        Register a command handler.

        Args:
            command: Command name (e.g., "THEME").
            handler: Function to call when the command is received.
        """
        self.handlers[command.upper()] = handler

    def start_server(self) -> bool:
        """Start the IPC server."""
        # Clean up any stale socket file first
        try:
            os.unlink(self.socket_path)
        except OSError:
            pass  # Ignore if the file doesn't exist

        try:
            self._running = True
            self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server_socket.bind(self.socket_path)
            self.server_socket.listen(5)

            self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self.server_thread.start()

            logger.info(f"IPC server started on {self.socket_path}")
            return True

        except Exception as e:
            logger.error(f"Error starting IPC server: {e}")
            self._running = False
            return False

    def stop_server(self):
        """Stop the IPC server."""
        if not self._running:
            return

        self._running = False

        if self.server_socket:
            try:
                # This unblocks the blocking accept() call in the server thread
                self.server_socket.shutdown(socket.SHUT_RDWR)
                self.server_socket.close()
            except (OSError, socket.error):
                pass  # Ignore errors on shutdown
            self.server_socket = None

        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=0.5)

        # Final cleanup of the socket file
        try:
            os.unlink(self.socket_path)
        except OSError:
            pass

        logger.info("IPC server stopped")

    def _server_loop(self):
        """Server loop to handle incoming connections."""
        while self._running and self.server_socket:
            try:
                client_socket, _ = self.server_socket.accept()
                try:
                    data = client_socket.recv(1024).decode("utf-8").strip()
                    response = self._handle_command(data)
                    client_socket.send(response.encode("utf-8"))
                except Exception as e:
                    logger.error(f"Error handling client connection: {e}")
                    client_socket.send(b"ERROR: Internal server error")
                finally:
                    client_socket.close()
            except OSError:
                # This can happen when the socket is closed by stop_server()
                break
            except Exception as e:
                if self._running:
                    logger.error(f"Error in IPC server loop: {e}")
                break

    def _handle_command(self, command_line: str) -> str:
        """
        Parse and handle a received command.
        """

        logger.info(f"Received IPC command {command_line}")

        try:
            parts = command_line.strip().split(maxsplit=1)
            if not parts:
                return "ERROR: Empty command"

            command = parts[0].upper()
            args = parts[1] if len(parts) > 1 else ""

            if command == "PING":
                return "PONG"

            if command in self.handlers:
                result_holder = {"result": None}
                done_event = threading.Event()

                def execute_handler():
                    try:
                        result_holder["result"] = self.handlers[command](args)
                    except Exception as e:
                        logger.error(f"Error executing handler for {command}: {e}")
                        result_holder["result"] = f"ERROR: Handler exception: {e}"
                    finally:
                        done_event.set()
                    return False  # Remove from idle queue

                GLib.idle_add(execute_handler)

                # Wait for handler to finish (with timeout for safety)
                if not done_event.wait(timeout=2.0):
                    logger.error(f"Timeout waiting for handler for {command}")
                    return "ERROR: Handler timeout"
                response = result_holder["result"]
                if response is None:
                    response = "OK"
                if not response.endswith("\n"):
                    response += "\n"
                return response
            else:
                return f"ERROR: Unknown command: {command}"

        except Exception as e:
            logger.error(f"Error processing command '{command_line}': {e}")
            return f"ERROR: {str(e)}"

    @staticmethod
    def send_command(app_name: str, command: str, timeout: float = 0.5) -> bool:
        """
        Send a command to a running instance.

        Returns:
            True if the command was sent and acknowledged, False otherwise.
        """
        socket_path = IPCManager._get_socket_path(app_name)
        if not os.path.exists(socket_path):
            return False

        try:
            client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client_socket.settimeout(timeout)
            client_socket.connect(socket_path)
            client_socket.send(command.encode("utf-8"))
            response = client_socket.recv(1024).decode("utf-8").strip()
            client_socket.close()

            if response.startswith("OK"):
                return True
            else:
                logger.error(f"IPC command '{command}' failed: {response}")
                return False

        except (ConnectionRefusedError, FileNotFoundError, socket.timeout):
            # This is the expected failure case if no server is listening
            return False
        except Exception as e:
            logger.error(f"Error sending IPC command '{command}': {e}")
            return False
