import logging
import os
import signal
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ProcessManager:
    def __init__(self):
        self._active = {}

    def _sigchld_handler(self, signum, frame):
        """Reap child processes to avoid zombies."""
        while True:
            try:
                pid, _ = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    break
                self._active.pop(pid, None)
            except ChildProcessError:
                break
            except Exception as e:
                logger.error(f"SIGCHLD handler error: {e}")
                break

    def launch_detached(
        self, cmd_parts: List[str], env: Optional[Dict[str, str]] = None
    ) -> bool:
        try:
            if os.fork() > 0:
                # Parent: return success
                return True
            os.setsid()
            if os.fork() > 0:
                os._exit(0)

            # Child process setup
            os.chdir("/")
            os.umask(0)
            with open("/dev/null", "r") as f:
                os.dup2(f.fileno(), 0)
            with open("/dev/null", "a+") as f:
                os.dup2(f.fileno(), 1)
                os.dup2(f.fileno(), 2)

            if env is None:
                env = os.environ.copy()

            os.execvpe(cmd_parts[0], cmd_parts, env)
        except Exception as e:
            logger.error(f"Error launching detached process: {e}")
            os._exit(1)  # if child
        return False


process_manager = ProcessManager()
