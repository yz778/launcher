from ..base import Plugin, SearchResult
from datetime import datetime, time
from launcher.utils.scoring_system import calculate_match_score
from typing import Dict, List, Any, Optional
import logging
import pytz
import re

logger = logging.getLogger(__name__)


class TimezonePlugin(Plugin):
    """Plugin for converting times between timezones"""

    defaults = {
        "track_history": True,
    }

    # Compiled regex patterns for performance
    _TIME_PATTERNS = [
        re.compile(r"\d{1,2}:\d{2}"),  # HH:MM format
        re.compile(r"\d{1,2}am"),  # 5am format
        re.compile(r"\d{1,2}pm"),  # 5pm format
        re.compile(r"\d{3,4}"),  # 1300, 0800 format
        re.compile(r"\d{1,2}\s*[a-z]+"),  # 5pst format (space optional)
        re.compile(r"now"),  # now keyword
    ]

    _PARSE_PATTERNS = [
        re.compile(r"(\d{1,2}:\d{2})\s*([a-z]+)", re.IGNORECASE),  # 5:30 PDT
        re.compile(r"(\d{1,2})(am|pm)\s*([a-z]+)", re.IGNORECASE),  # 5am PDT
        re.compile(r"(\d{3,4})\s*([a-z]+)", re.IGNORECASE),  # 1300 JST
        re.compile(r"(\d{1,2})\s*([a-z]+)", re.IGNORECASE),  # 5pst (no space required)
    ]

    def __init__(self):
        super().__init__()
        self._timezone_aliases = self._build_timezone_aliases()

    def get_id(self) -> str:
        return "timezone"

    def get_name(self) -> str:
        return "Timezone Converter"

    def get_description(self) -> str:
        return "Convert times between different timezones"

    def _build_timezone_aliases(self) -> Dict[str, str]:
        """Build a mapping of common timezone abbreviations and city names to tz database IDs."""

        # fmt: off
        alias_groups = {
            "America/Montreal": ["montreal"],
            "America/Toronto": ["toronto"],
            "Asia/Hong_Kong": ["hongkong", "hkt"],
            "Asia/Kolkata": ["ist", "india", "mumbai", "delhi", "bangalore"],
            "Asia/Shanghai": ["beijing", "shanghai"],
            "Asia/Singapore": ["singapore"],
            "Asia/Tokyo": ["tokyo", "japan", "jst"],
            "Australia/Melbourne": ["melbourne"],
            "Australia/Sydney": ["sydney", "aest", "aedt"],
            "Europe/Berlin": ["berlin"],
            "Europe/London": ["london"],
            "Europe/Paris": ["paris"],
            "US/Central": ["cdt", "cst", "chicago"],
            "US/Eastern": ["edt", "est", "nyc", "ny", "toronto"],
            "US/Pacific": ["pdt", "pst", "vancouver"],
            "US/Mountain": ["mdt", "mst", "denver"],
            "UTC": ["utc", "gmt"],
        }
        # fmt: on

        return {
            alias.lower(): tz
            for tz, aliases in alias_groups.items()
            for alias in aliases
        }

    def initialize(self, config: Dict[str, Any], config_manager) -> bool:
        """Initialize the plugin with the given configuration"""
        super().initialize(config, config_manager)
        return True

    def start(self) -> bool:
        """Start the plugin and perform any necessary setup work"""
        return True

    def _is_timezone_query(self, query: str) -> bool:
        """Check if the query looks like a timezone conversion"""
        if not query or len(query.strip()) < 5:
            return False

        query_lower = query.lower().strip()

        # Must contain "to" for conversion
        if " to " not in query_lower:
            return False

        # Should have time-like patterns or "now"
        has_time = any(pattern.search(query_lower) for pattern in self._TIME_PATTERNS)
        return has_time

    def _parse_timezone_query(self, query: str) -> Optional[Dict[str, Any]]:
        """Parse a timezone conversion query"""
        try:
            query = query.strip()
            parts = query.lower().split(" to ")

            if len(parts) != 2:
                return None

            source_part = parts[0].strip()
            target_part = parts[1].strip()

            # Parse source time and timezone
            source_time, source_tz = self._parse_time_and_timezone(source_part)
            if not source_time or not source_tz:
                return None

            # Parse target timezone
            target_tz = self._parse_timezone(target_part)
            if not target_tz:
                return None

            return {
                "source_time": source_time,
                "source_tz": source_tz,
                "target_tz": target_tz,
                "original_query": query,
            }

        except Exception:
            return None

    def _parse_time_and_timezone(
        self, text: str
    ) -> tuple[Optional[str], Optional[str]]:
        """Parse time and timezone from text like '5AM PDT', '1300 JST', '5 pst', or 'now'"""
        text = text.strip().lower()

        # Handle "now" keyword
        if text == "now":
            return "now", "local"

        # Use compiled patterns for time formats
        for pattern in self._PARSE_PATTERNS:
            match = pattern.search(text)
            if match:
                if len(match.groups()) == 2:  # Format like "1300 JST" or "5 pst"
                    time_str, tz_str = match.groups()
                else:  # Format like "5am PDT"
                    time_str = match.group(1) + (
                        match.group(2) if len(match.groups()) > 2 else ""
                    )
                    tz_str = (
                        match.group(3) if len(match.groups()) > 2 else match.group(2)
                    )

                tz = self._parse_timezone(tz_str)
                if tz:
                    return time_str, tz

        return None, None

    def _parse_timezone(self, tz_text: str) -> Optional[str]:
        """Parse timezone from text, supporting 'local' as a special keyword"""
        tz_text = tz_text.strip().lower()

        if tz_text == "local":
            return "local"

        # Check aliases first
        if tz_text in self._timezone_aliases:
            return self._timezone_aliases[tz_text]

        # Try to find it in pytz timezones
        for tz_name in pytz.all_timezones:
            if tz_text in tz_name.lower():
                return tz_name

        return None

    def _convert_time(
        self, time_str: str, source_tz_name: str, target_tz_name: str
    ) -> Optional[str]:
        """Convert time from source timezone to target timezone, supporting 'local' for both"""
        try:
            # Determine source timezone
            if source_tz_name == "local":
                source_tz = None  # Will use local timezone
            else:
                try:
                    source_tz = pytz.timezone(source_tz_name)
                except pytz.UnknownTimeZoneError:
                    return None

            # Determine target timezone
            if target_tz_name == "local":
                target_tz = None  # Will use local timezone
            else:
                try:
                    target_tz = pytz.timezone(target_tz_name)
                except pytz.UnknownTimeZoneError:
                    return None

            # Handle "now" keyword
            if time_str == "now":
                if source_tz is None:
                    source_dt = datetime.now().astimezone()
                else:
                    source_dt = datetime.now(source_tz)
                if target_tz is None:
                    target_dt = source_dt.astimezone()
                else:
                    target_dt = source_dt.astimezone(target_tz)
            else:
                now = datetime.now()

                # Handle different time formats
                if ":" in time_str:
                    # HH:MM format
                    time_obj = datetime.strptime(time_str, "%H:%M").time()
                elif time_str.lower().endswith("am") or time_str.lower().endswith("pm"):
                    # 12-hour format
                    time_obj = datetime.strptime(time_str.upper(), "%I%p").time()
                elif len(time_str) in [3, 4] and time_str.isdigit():
                    # Military time format (e.g., 1300, 800)
                    if len(time_str) == 3:
                        time_str = "0" + time_str
                    hour = int(time_str[:2])
                    minute = int(time_str[2:])
                    time_obj = time(hour, minute)
                elif time_str.isdigit() and 1 <= int(time_str) <= 24:
                    # Simple hour format (e.g., "5" means 5:00)
                    hour = int(time_str)
                    if hour == 24:
                        hour = 0
                    time_obj = time(hour, 0)
                else:
                    return None

                source_dt = datetime.combine(now.date(), time_obj)
                if source_tz is None:
                    # Localize to local timezone
                    source_dt = source_dt.astimezone()
                else:
                    source_dt = source_tz.localize(source_dt)

                if target_tz is None:
                    target_dt = source_dt.astimezone()
                else:
                    target_dt = source_dt.astimezone(target_tz)

            # Format the result
            target_time_12h = target_dt.strftime("%I:%M %p").lstrip("0")
            target_time_24h = target_dt.strftime("%H:%M")
            target_tz_abbr = target_dt.strftime("%Z")

            return f"{target_time_12h} ({target_time_24h}) {target_tz_abbr}"

        except Exception:
            return None

    def search(self, query: str) -> List[SearchResult]:
        """Search for timezone conversions matching the query, supporting 'local' for both source and target"""
        if not self._is_timezone_query(query):
            return []

        parsed = self._parse_timezone_query(query)
        if not parsed:
            return []

        result = self._convert_time(
            parsed["source_time"], parsed["source_tz"], parsed["target_tz"]
        )

        if not result:
            return []

        # Display logic for source and target timezones
        def tz_display(tz_name):
            if tz_name == "local":
                return "Local"
            try:
                return pytz.timezone(tz_name).zone
            except pytz.UnknownTimeZoneError:
                return tz_name

        source_tz_display = tz_display(parsed["source_tz"])
        target_tz_display = tz_display(parsed["target_tz"])

        description = f"{result} in {target_tz_display}"
        base_score = calculate_match_score(query, query, is_name=True)
        timezone_bonus = 50
        final_score = base_score + timezone_bonus

        search_result = SearchResult(
            plugin_id=self.get_id(),
            item_id=query,
            name=f"{parsed['source_time']} {source_tz_display} → {result}",
            description=description,
            icon_spec="theme://appointment-soon",
            score=final_score,
            metadata={
                "result": result,
                "conversion": parsed,
                "track_history": self.should_track_history(),
            },
        )

        return [search_result]

    def execute(self, result: SearchResult) -> bool:
        return False
