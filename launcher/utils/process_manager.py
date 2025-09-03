#!/usr/bin/env python3

import logging
import os
import signal
import subprocess
import threading
import time
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)


class ProcessManager:
    """
    Manages child processes to prevent zombie processes.

    This class handles proper cleanup of child processes by:
    1. Using double-fork technique for true daemon processes
    2. Setting up signal handlers to reap zombie processes
    3. Tracking active processes and cleaning them up
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        self._active_processes = {}
        self._cleanup_thread = None
        self._shutdown = False
        self._setup_signal_handlers()
        self._start_cleanup_thread()

    def _setup_signal_handlers(self):
        """Set up signal handlers to reap zombie processes."""
        try:
            # Handle SIGCHLD to reap zombie processes
            signal.signal(signal.SIGCHLD, self._sigchld_handler)
        except (OSError, ValueError) as e:
            logger.warning(f"Could not set up SIGCHLD handler: {e}")

    def _sigchld_handler(self, signum, frame):
        """Handle SIGCHLD signal to reap zombie processes."""
        try:
            while True:
                try:
                    pid, status = os.waitpid(-1, os.WNOHANG)
                    if pid == 0:
                        break

                    if pid in self._active_processes:
                        del self._active_processes[pid]

                except OSError:
                    break
        except Exception as e:
            logger.error(f"Error in SIGCHLD handler: {e}")

    def _start_cleanup_thread(self):
        """Start background thread to clean up processes."""
        if self._cleanup_thread is None or not self._cleanup_thread.is_alive():
            self._cleanup_thread = threading.Thread(
                target=self._cleanup_worker, daemon=True, name="ProcessCleanup"
            )
            self._cleanup_thread.start()

    def _cleanup_worker(self):
        """Background worker to periodically clean up finished processes."""
        while not self._shutdown:
            try:
                self._cleanup_finished_processes()
                time.sleep(5)  # Check every 5 seconds
            except Exception as e:
                logger.error(f"Error in cleanup worker: {e}")
                time.sleep(1)

    def _cleanup_finished_processes(self):
        """Clean up any finished processes."""
        finished_pids = []

        for pid, info in list(self._active_processes.items()):
            try:
                # Check if process is still running
                os.kill(pid, 0)
            except OSError:
                # Process is dead, mark for removal
                finished_pids.append(pid)

        for pid in finished_pids:
            if pid in self._active_processes:
                del self._active_processes[pid]

    def launch_detached(
        self, cmd_parts: List[str], env: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Launch a process completely detached from the parent.

        Uses double-fork technique to create a true daemon process that won't
        become a zombie when it exits.

        Args:
            cmd_parts: Command and arguments as a list
            env: Environment variables (optional)
            cwd: Working directory (optional)

        Returns:
            True if launch was successful, False otherwise
        """
        try:
            # First fork
            pid = os.fork()
            if pid > 0:
                # Parent process - wait for intermediate child
                os.waitpid(pid, 0)
                return True

            # First child - become session leader and fork again
            os.setsid()

            # Second fork
            pid = os.fork()
            if pid > 0:
                # First child exits, leaving second child orphaned
                os._exit(0)

            # Second child - this becomes the daemon process
            self._setup_daemon_process()

            # Execute the actual command
            if env is None:
                env = os.environ.copy()
                # Remove GDK_BACKEND to prevent issues with GUI apps
                env.pop("GDK_BACKEND", None)

            os.execvpe(cmd_parts[0], cmd_parts, env)

        except Exception as e:
            logger.error(f"Error launching detached process {cmd_parts}: {e}")
            if os.getpid() != os.getppid():  # We're in a child process
                os._exit(1)
            return False

    def _setup_daemon_process(self):
        """Set up the daemon process environment."""
        try:
            # Change working directory to root to avoid keeping directories busy
            os.chdir("/")

            # Set file creation mask
            os.umask(0)

            # Redirect standard file descriptors to /dev/null
            with open("/dev/null", "r") as dev_null_r:
                os.dup2(dev_null_r.fileno(), 0)  # stdin

            with open("/dev/null", "w") as dev_null_w:
                os.dup2(dev_null_w.fileno(), 1)  # stdout
                os.dup2(dev_null_w.fileno(), 2)  # stderr

        except Exception as e:
            logger.error(f"Error setting up daemon process: {e}")

    def launch_tracked(
        self,
        cmd_parts: List[str],
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ) -> Optional[subprocess.Popen]:
        """
        Launch a process that will be tracked for cleanup.

        Use this for processes that you might want to monitor or clean up later.

        Args:
            cmd_parts: Command and arguments as a list
            env: Environment variables (optional)
            cwd: Working directory (optional)

        Returns:
            Popen object if successful, None otherwise
        """
        try:
            if env is None:
                env = os.environ.copy()
                env.pop(
                    "GDK_BACKEND", None
                )  # Remove GDK_BACKEND to prevent issues with GUI apps

            process = subprocess.Popen(
                cmd_parts,
                env=env,
                cwd=cwd,
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Track the process
            self._active_processes[process.pid] = {
                "process": process,
                "cmd": cmd_parts,
                "start_time": time.time(),
            }

            return process

        except Exception as e:
            logger.error(f"Error launching tracked process {cmd_parts}: {e}")
            return None

    def get_active_process_count(self) -> int:
        """Get the number of active tracked processes."""
        return len(self._active_processes)

    def cleanup_all(self):
        """Clean up all tracked processes."""
        self._shutdown = True

        # Terminate all tracked processes
        for pid, info in list(self._active_processes.items()):
            try:
                process = info["process"]
                if process.poll() is None:  # Still running
                    process.terminate()

                    # Give it a moment to terminate gracefully
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        # Force kill if it doesn't terminate
                        process.kill()
                        process.wait()

            except Exception as e:
                logger.error(f"Error cleaning up process {pid}: {e}")

        self._active_processes.clear()
        logger.info("Process manager cleanup completed")


process_manager = ProcessManager()
