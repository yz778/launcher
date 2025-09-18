import logging
import queue
import re
import subprocess
import threading
import time
from typing import List, Optional

import pyperclip

from launcher.plugins.base import Plugin, SearchResult

logger = logging.getLogger(__name__)


class QalculatePlugin(Plugin):
    """Plugin for calculating mathematical expressions"""

    def __init__(self):
        super().__init__()
        self.prefixes = ["="]
        self.prefixes_only = False
        self._last_valid_result = None
        self._active_processes = set()
        self._qalc_process = None
        self._process_lock = threading.Lock()
        self._output_queue = queue.Queue()
        self._reader_thread = None
        self._cooldown_timer = None
        self._cooldown_seconds = 10
        self._qalc_timeout_seconds = 0.5
        self._qalc_response_seconds = 0.2

    def get_id(self) -> str:
        return "qalculate"

    def get_name(self) -> str:
        return "Qalculate"

    def get_description(self) -> str:
        return "Calculate expressions with Qalculate"

    def initialize(self, config) -> bool:
        """Initialize the plugin with the given configuration"""
        super().initialize(config)

        # Check if qalc is available before proceeding with initialization
        try:
            subprocess.run(
                ["qalc", "--version"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (
            FileNotFoundError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ):
            logger.warning(
                "qalc command not found or timed out. Qalculate plugin will be disabled."
            )
            return False

        return True

    def start(self) -> bool:
        """Plugin start - qalc session will be started lazily on first calculation"""
        return True

    def cleanup(self):
        """Cleanup method called during application shutdown"""
        self._cancel_cooldown_timer()
        self._stop_qalc_session()

    def __del__(self):
        """Destructor to ensure cleanup happens even if not explicitly called"""
        try:
            self.cleanup()
        except Exception:
            pass  # Ignore errors during destruction

    def _output_reader(self):
        """Thread function to read output from qalc process"""
        while self._qalc_process and self._qalc_process.poll() is None:
            try:
                line = self._qalc_process.stdout.readline()
                if line:
                    self._output_queue.put(line)
                else:
                    time.sleep(0.01)
            except Exception as e:
                logger.error(f"Error reading qalc output: {e}")
                break

    def _start_cooldown_timer(self):
        """Start or restart the cooldown timer"""
        self._cancel_cooldown_timer()
        self._cooldown_timer = threading.Timer(
            self._cooldown_seconds, self._on_cooldown_expired
        )
        self._cooldown_timer.start()

    def _cancel_cooldown_timer(self):
        """Cancel the current cooldown timer if it exists"""
        if self._cooldown_timer is not None:
            self._cooldown_timer.cancel()
            self._cooldown_timer = None

    def _on_cooldown_expired(self):
        """Called when the cooldown timer expires"""
        self._stop_qalc_session()

    def _start_qalc_session(self):
        """Start an interactive qalc session"""
        if self._qalc_process is None or self._qalc_process.poll() is not None:
            try:
                self._qalc_process = subprocess.Popen(
                    ["qalc", "-t", "-i"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,  # Line buffered
                    universal_newlines=True,
                )

                # Start the output reader thread
                self._reader_thread = threading.Thread(
                    target=self._output_reader, daemon=True
                )
                self._reader_thread.start()

                # Wait a moment for qalc to start up
                time.sleep(self._qalc_response_seconds)

                # Clear any startup messages
                while not self._output_queue.empty():
                    try:
                        self._output_queue.get_nowait()
                    except queue.Empty:
                        break

                logger.info("Started interactive qalc session")
            except Exception as e:
                logger.error(f"Failed to start qalc session: {e}")
                self._qalc_process = None

    def _stop_qalc_session(self):
        """Stop the interactive qalc session"""
        self._cancel_cooldown_timer()
        with self._process_lock:
            if self._qalc_process is not None:
                try:
                    # Try graceful termination first
                    self._qalc_process.terminate()
                    try:
                        self._qalc_process.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        # Force kill if graceful termination fails
                        self._qalc_process.kill()
                        self._qalc_process.wait(timeout=1.0)
                except Exception as e:
                    logger.info(f"Error stopping qalc session: {e}")
                finally:
                    self._qalc_process = None
                    self._reader_thread = None
                    # Clear the output queue
                    while not self._output_queue.empty():
                        try:
                            self._output_queue.get_nowait()
                        except queue.Empty:
                            break

    def _strip_ansi_codes(self, text: str) -> str:
        """Remove ANSI color codes from text"""
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        return ansi_escape.sub("", text)

    def _is_calculation(self, query: str) -> bool:
        """Check if the query looks like a calculation using simple heuristics"""
        if not query:
            return False

        # 1. Explicit calculation trigger
        if self.query_startswith_prefix(query):
            return True

        # 2. Starts with a number (most calculations do)
        if query[0].isdigit():
            return True

        # 3. Contains conversion keywords
        conversion_keywords = [" to ", " in ", " as ", " into "]
        if any(keyword in query.lower() for keyword in conversion_keywords):
            return True

        # 4. Contains function call pattern (something followed by parentheses)
        if "(" in query and ")" in query:
            return True

        return False

    def _calculate(self, expression: str) -> Optional[str]:
        """
        Calculate the result of the expression using interactive qalc session

        Returns None if calculation fails
        """

        with self._process_lock:
            if self._qalc_process is None or self._qalc_process.poll() is not None:
                self._start_qalc_session()

            if self._qalc_process is None:
                logger.error("Failed to start qalc session")
                return None

            try:
                # Clear any pending output
                while not self._output_queue.empty():
                    try:
                        self._output_queue.get_nowait()
                    except queue.Empty:
                        break

                # Send expression to qalc
                self._qalc_process.stdin.write(f"{expression}\n")
                self._qalc_process.stdin.flush()

                # Read the result with timeout
                start_time = time.time()
                while time.time() - start_time < self._qalc_timeout_seconds:
                    try:
                        line = self._output_queue.get(
                            timeout=self._qalc_response_seconds
                        )
                        clean_line = self._strip_ansi_codes(line.strip())

                        # Return first non-empty line that doesn't start with >
                        if clean_line and not clean_line.startswith(">"):
                            self._start_cooldown_timer()
                            return clean_line

                    except queue.Empty:
                        continue

                return None

            except Exception as e:
                logger.error(f"Error calculating with qalc: {e}")
                self._stop_qalc_session()
                return None

    def search(self, query: str) -> List[SearchResult]:
        """Search for calculations matching the query"""
        if not self._is_calculation(query):
            return []

        query = self.strip_prefixes(query)

        result = self._calculate(query)
        if result is None:
            if self._last_valid_result is not None:
                result = self._last_valid_result
            else:
                return []
        else:
            self._last_valid_result = result

        result = result.replace('"', "").replace("'", "")
        search_result = SearchResult(
            plugin_id=self.get_id(),
            item_id=query,
            name=query,
            description=result,
            icon_spec="theme://qalculate",
            score=100.0,
            hilight=None,
            metadata={"result": result},
        )

        return [search_result]

    def execute(self, result: SearchResult) -> bool:
        """Execute the calculation result - copy to clipboard or launch qalc based on modifiers"""
        if result.plugin_id != self.get_id():
            return False

        # Check if shift was pressed (for launching qalc)
        shift_pressed = result.metadata.get("shift_pressed", False)

        if shift_pressed:
            # Shift+Enter: Launch qalculate-gtk
            return self._launch_qalculate_gui(result)
        else:
            # Enter: Copy result to clipboard
            return self._copy_to_clipboard(result)

    def _launch_qalculate_gui(self, result: SearchResult) -> bool:
        """Launch qalculate-gtk with the expression"""
        query = result.name
        if not query:
            return False

        try:
            expression = self.strip_prefixes(query)

            # Use start_new_session to detach from parent process
            subprocess.Popen(
                ["qalculate-gtk", expression],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info(f"Launched qalculate-gtk with expression: {expression}")
            return True

        except FileNotFoundError:
            logger.error(
                "qalculate-gtk command not found. Please install qalculate-gtk."
            )
            return False

        except Exception as e:
            logger.error(f"Error launching qalculate-gtk: {e}")
            return False

    def _copy_to_clipboard(self, result: SearchResult) -> bool:
        """Copy the calculation result to clipboard using pyperclip"""
        calculation_result = result.metadata.get("result")
        if not calculation_result:
            return False

        try:
            pyperclip.copy(calculation_result)
            logger.info(f"Copied calculation result to clipboard: {calculation_result}")
            return True

        except Exception as e:
            logger.error(f"Error copying to clipboard: {e}")
            return False
