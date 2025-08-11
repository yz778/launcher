#!/usr/bin/env python3

import logging
import re
from typing import Dict, List, Any, Optional
from datetime import datetime
import pytz

import pyperclip
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

from ..base import Plugin, SearchResult
from launcher.utils.scoring_system import calculate_match_score

logger = logging.getLogger(__name__)


class TimezonePlugin(Plugin):
    """Plugin for converting times between timezones"""

    # Compiled regex patterns for performance
    _TIME_PATTERNS = [
        re.compile(r"\d{1,2}:\d{2}"),  # HH:MM format
        re.compile(r"\d{1,2}am"),  # 5am format
        re.compile(r"\d{1,2}pm"),  # 5pm format
        re.compile(r"\d{3,4}"),  # 1300, 0800 format
        re.compile(r"\d{1,2}\s+[a-z]+"),  # 5 pst format
        re.compile(r"now"),  # now keyword
    ]

    _PARSE_PATTERNS = [
        re.compile(r"(\d{1,2}:\d{2})\s*([a-z]+)", re.IGNORECASE),  # 5:30 PDT
        re.compile(r"(\d{1,2})(am|pm)\s*([a-z]+)", re.IGNORECASE),  # 5am PDT
        re.compile(r"(\d{3,4})\s*([a-z]+)", re.IGNORECASE),  # 1300 JST
        re.compile(r"(\d{1,2})\s+([a-z]+)", re.IGNORECASE),  # 5 pst
    ]

    def __init__(self):
        super().__init__()
        self.icon_size = None
        self.icon = None
        self._timezone_aliases = self._build_timezone_aliases()

    def get_id(self) -> str:
        return "timezone"

    def get_name(self) -> str:
        return "Timezone Converter"

    def get_description(self) -> str:
        return "Convert times between different timezones"

    def get_config_defaults(self) -> Dict[str, Any]:
        """Get default configuration for this plugin"""
        return {
            "track_history": True,
        }

    def get_default_css(self) -> str:
        """Get default CSS for this plugin"""
        return """
/* Timezone Plugin CSS */
.timezone-result #app-list-item {
    padding: 8px;
    border-radius: 8px;
    transition: background-color 0.2s ease;
    min-height: 50px;
}

.timezone-result #app-list-item:hover {
    background-color: rgba(70, 130, 180, 0.4);
}

.timezone-result #app-list-item:selected {
    background-color: rgba(90, 150, 200, 0.6);
}

.timezone-result #app-name {
    color: #e0f0ff;
    font-size: 18px;
    font-weight: bold;
    font-family: monospace;
}

.timezone-result #app-description {
    color: #b0d0f0;
    font-size: 14px;
    font-family: monospace;
}
"""

    def _build_timezone_aliases(self) -> Dict[str, str]:
        """Build a mapping of common timezone abbreviations to pytz timezone names"""
        return {
            # US/Canada
            "pdt": "US/Pacific",
            "pst": "US/Pacific",
            "mdt": "US/Mountain",
            "mst": "US/Mountain",
            "cdt": "US/Central",
            "cst": "US/Central",
            "edt": "US/Eastern",
            "est": "US/Eastern",
            # Major cities/regions
            "vancouver": "America/Vancouver",
            "seattle": "America/Los_Angeles",
            "portland": "America/Los_Angeles",
            "sf": "America/Los_Angeles",
            "la": "America/Los_Angeles",
            "denver": "America/Denver",
            "chicago": "America/Chicago",
            "nyc": "America/New_York",
            "ny": "America/New_York",
            "toronto": "America/Toronto",
            "montreal": "America/Montreal",
            # International
            "utc": "UTC",
            "gmt": "GMT",
            "london": "Europe/London",
            "paris": "Europe/Paris",
            "berlin": "Europe/Berlin",
            "tokyo": "Asia/Tokyo",
            "japan": "Asia/Tokyo",
            "jst": "Asia/Tokyo",
            "beijing": "Asia/Shanghai",
            "shanghai": "Asia/Shanghai",
            "hkt": "Asia/Hong_Kong",
            "hongkong": "Asia/Hong_Kong",
            "singapore": "Asia/Singapore",
            "sydney": "Australia/Sydney",
            "melbourne": "Australia/Melbourne",
            "aest": "Australia/Sydney",
            "aedt": "Australia/Sydney",
            # India
            "ist": "Asia/Kolkata",
            "india": "Asia/Kolkata",
            "mumbai": "Asia/Kolkata",
            "delhi": "Asia/Kolkata",
            "bangalore": "Asia/Kolkata",
        }

    def initialize(self, config: Dict[str, Any], config_manager) -> bool:
        """Initialize the plugin with the given configuration"""
        super().initialize(config, config_manager)
        self.icon_size = self.get_icon_size()
        return True

    def start(self) -> bool:
        """Start the plugin and perform any necessary setup work"""
        self._load_icon()
        return True

    def _load_icon(self) -> None:
        """Load the timezone icon"""
        try:
            from launcher.utils.icon_utils import load_theme_icon

            # Try multiple clock-related icons as fallbacks
            icon_names = ["appointment-soon"]

            for icon_name in icon_names:
                self.icon = load_theme_icon(icon_name, self.icon_size)
                if self.icon:
                    logger.debug(f"Loaded timezone icon: {icon_name}")
                    break

            if not self.icon:
                logger.warning("Could not load any timezone icon")
        except ImportError as e:
            logger.error(f"Could not import icon_utils: {e}")
            self.icon = None

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

        except Exception as e:
            logger.debug(f"Error parsing timezone query: {e}")
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
        """Parse timezone from text"""
        tz_text = tz_text.strip().lower()

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
        """Convert time from source timezone to target timezone"""
        try:
            # Validate target timezone
            try:
                target_tz = pytz.timezone(target_tz_name)
            except pytz.UnknownTimeZoneError:
                logger.debug(f"Unknown target timezone: {target_tz_name}")
                return None

            # Handle "now" keyword
            if time_str == "now":
                if source_tz_name == "local":
                    # Use local time - safely get timezone-aware datetime
                    source_dt = datetime.now().astimezone()
                    # Convert to target timezone
                    target_dt = source_dt.astimezone(target_tz)
                else:
                    # Get current time in source timezone
                    try:
                        source_tz = pytz.timezone(source_tz_name)
                    except pytz.UnknownTimeZoneError:
                        logger.debug(f"Unknown source timezone: {source_tz_name}")
                        return None
                    source_dt = datetime.now(source_tz)
                    target_dt = source_dt.astimezone(target_tz)
            else:
                try:
                    source_tz = pytz.timezone(source_tz_name)
                except pytz.UnknownTimeZoneError:
                    logger.debug(f"Unknown source timezone: {source_tz_name}")
                    return None
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
                    from datetime import time

                    time_obj = time(hour, minute)
                elif time_str.isdigit() and 1 <= int(time_str) <= 24:
                    # Simple hour format (e.g., "5" means 5:00)
                    hour = int(time_str)
                    if hour == 24:
                        hour = 0
                    from datetime import time

                    time_obj = time(hour, 0)
                else:
                    return None

                # Create datetime with today's date
                source_dt = datetime.combine(now.date(), time_obj)

                # Localize to source timezone
                source_dt = source_tz.localize(source_dt)

                # Convert to target timezone
                target_dt = source_dt.astimezone(target_tz)

            # Format the result
            target_time_12h = target_dt.strftime("%I:%M %p").lstrip("0")
            target_time_24h = target_dt.strftime("%H:%M")
            target_tz_abbr = target_dt.strftime("%Z")

            return f"{target_time_12h} ({target_time_24h}) {target_tz_abbr}"

        except Exception as e:
            logger.debug(f"Error converting time: {e}")
            return None

    def search(self, query: str) -> List[SearchResult]:
        """Search for timezone conversions matching the query"""
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

        # Get timezone names for display
        try:
            target_tz_obj = pytz.timezone(parsed["target_tz"])
        except pytz.UnknownTimeZoneError:
            logger.debug(f"Unknown target timezone for display: {parsed['target_tz']}")
            return []

        if parsed["source_tz"] == "local":
            source_tz_display = "Local"
        else:
            try:
                source_tz_obj = pytz.timezone(parsed["source_tz"])
                source_tz_display = source_tz_obj.zone
            except pytz.UnknownTimeZoneError:
                logger.debug(
                    f"Unknown source timezone for display: {parsed['source_tz']}"
                )
                return []

        description = f"{result} in {target_tz_obj.zone}"

        # Give timezone queries a higher score since this is a specialized plugin
        base_score = calculate_match_score(query, query, is_name=True)
        # Add bonus for timezone-specific queries to prioritize over generic calculation plugins
        timezone_bonus = 50
        final_score = base_score + timezone_bonus

        # Ensure icon is loaded
        if not self.icon:
            self._load_icon()

        search_result = SearchResult(
            plugin_id=self.get_id(),
            item_id=query,
            name=f"{parsed['source_time']} {source_tz_display} → {result}",
            description=description,
            icon=self.icon,
            score=final_score,
            metadata={
                "result": result,
                "conversion": parsed,
                "track_history": self.should_track_history(),
            },
        )

        return [search_result]

    def execute(self, result: SearchResult) -> bool:
        """Execute the timezone conversion result - copy to clipboard"""
        if result.plugin_id != self.get_id():
            return False

        conversion_result = result.metadata.get("result")
        if not conversion_result:
            return False

        try:
            pyperclip.copy(conversion_result)
            logger.info(
                f"Copied timezone conversion result to clipboard: {conversion_result}"
            )
            return True
        except Exception as e:
            logger.error(f"Error copying to clipboard: {e}")
            return False
