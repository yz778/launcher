import logging
import shlex
from typing import List

from launcher.plugins.base import Plugin, SearchResult
from launcher.utils.process_manager import process_manager
from launcher.utils.scoring_system import calculate_match_score

logger = logging.getLogger(__name__)


class AskAIPlugin(Plugin):
    """
    Launcher plugin to ask AI questions using chat-perplexity.
    """

    def __init__(self):
        super().__init__()
        self.prefixes = ["\\"]
        self.track_history = "plugin"  # Keep history within plugin only

    def get_id(self) -> str:
        return "askai"

    def get_name(self) -> str:
        return "Ask AI"

    def get_description(self) -> str:
        return "Ask AI questions using Perplexity."

    def start(self) -> bool:
        return True

    def search(self, query: str) -> List[SearchResult]:
        if not self.query_startswith_prefix(query):
            return []

        question = self.strip_prefixes(query)

        if not question:
            # Show placeholder plus plugin history
            results = []

            # Add placeholder
            results.append(
                SearchResult(
                    plugin_id=self.get_id(),
                    item_id="",
                    name="Ask Perplexity AI...",
                    description="Type your question",
                    icon_spec="https://registry.npmmirror.com/@lobehub/icons-static-png/latest/files/dark/perplexity-color.png",
                    score=100.0,
                    hilight=None,
                    metadata={"question": ""},
                )
            )

            # Add plugin history
            history_results = self.get_plugin_history()
            results.extend(history_results)

            return results

        score_result = calculate_match_score(query, question, is_name=True)
        score = score_result[0] if score_result else 100.0

        result = SearchResult(
            plugin_id=self.get_id(),
            item_id=question,
            name=question,
            description="Ask Perplexity AI",
            icon_spec="https://registry.npmmirror.com/@lobehub/icons-static-png/latest/files/dark/perplexity-color.png",
            score=score,
            hilight=None,
            metadata={"question": question},
        )
        return [result]

    def execute(self, result: SearchResult) -> bool:
        # Handle both direct results and history results
        actual_result = result
        if result.plugin_id == "history":
            # This is a history result, extract the original
            original_result_dict = result.metadata.get("original_result")
            if (
                not original_result_dict
                or original_result_dict.get("plugin_id") != self.get_id()
            ):
                return False
            actual_result = SearchResult.from_dict(original_result_dict)
        elif result.plugin_id != self.get_id():
            return False

        question = actual_result.metadata.get("question")
        if not question:
            return False

        try:
            cmd_parts = ["chat-perplexity"] + shlex.split(question)
            logger.info(f"Executing chat-perplexity: {' '.join(cmd_parts)}")
            success = process_manager.launch_detached(cmd_parts)
            return success

        except Exception as e:
            logger.error(
                f"Error executing chat-perplexity with question {question}: {e}"
            )
            return False
