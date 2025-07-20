#!/usr/bin/env python3

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add launcher directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Mock GTK before importing
sys.modules['gi'] = Mock()
sys.modules['gi.repository'] = Mock()
sys.modules['gi.repository.Gtk'] = Mock()
sys.modules['gi.repository.Gdk'] = Mock()
sys.modules['gi.repository.Pango'] = Mock()
sys.modules['gi.repository.GLib'] = Mock()

from launcher.ui.launcher_window import WindowPositioner


class TestWindowPositioner(unittest.TestCase):
    """Test cases for WindowPositioner class"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_window = Mock()
        self.config = {
            "general": {
                "window_position_vertical_percent": 25,
                "window_position_force_center": True,
                "window_position_debug": False
            }
        }
        self.positioner = WindowPositioner(self.mock_window, self.config)

    def test_init_with_config(self):
        """Test WindowPositioner initialization with config"""
        self.assertEqual(self.positioner.vertical_percent, 25)
        self.assertTrue(self.positioner.force_center)
        self.assertFalse(self.positioner.debug_mode)

    def test_init_with_empty_config(self):
        """Test WindowPositioner initialization with empty config"""
        positioner = WindowPositioner(self.mock_window, {})
        self.assertEqual(positioner.vertical_percent, 25)  # default
        self.assertTrue(positioner.force_center)  # default
        self.assertFalse(positioner.debug_mode)  # default

    def test_detect_display_system_wayland_display(self):
        """Test display system detection with WAYLAND_DISPLAY env var"""
        with patch.dict(os.environ, {'WAYLAND_DISPLAY': 'wayland-0'}):
            result = self.positioner.detect_display_system()
            self.assertEqual(result, "wayland")

    def test_detect_display_system_xdg_session_type(self):
        """Test display system detection with XDG_SESSION_TYPE env var"""
        with patch.dict(os.environ, {'XDG_SESSION_TYPE': 'wayland'}, clear=True):
            result = self.positioner.detect_display_system()
            self.assertEqual(result, "wayland")

    def test_detect_display_system_display_env(self):
        """Test display system detection with DISPLAY env var"""
        with patch.dict(os.environ, {'DISPLAY': ':0'}, clear=True):
            result = self.positioner.detect_display_system()
            self.assertEqual(result, "x11")

    def test_detect_display_system_unknown(self):
        """Test display system detection when unknown"""
        with patch.dict(os.environ, {}, clear=True):
            with patch('launcher.ui.launcher_window.Gdk.Display.get_default') as mock_display:
                mock_display.side_effect = Exception("No display")
                result = self.positioner.detect_display_system()
                self.assertEqual(result, "unknown")

    def test_calculate_position_center_horizontal(self):
        """Test position calculation for center horizontal positioning"""
        display_info = {
            'width': 1920,
            'height': 1080,
            'x': 0,
            'y': 0,
            'scale_factor': 1
        }
        window_size = (600, 70)

        target_x, target_y = self.positioner.calculate_position(display_info, window_size)

        # Should be centered horizontally: (1920 - 600) / 2 = 660
        self.assertEqual(target_x, 660)
        # Should be at 25% vertically: 1080 * 0.25 = 270
        self.assertEqual(target_y, 270)

    def test_calculate_position_with_offset(self):
        """Test position calculation with display offset (multi-monitor)"""
        display_info = {
            'width': 1920,
            'height': 1080,
            'x': 1920,  # Second monitor
            'y': 0,
            'scale_factor': 1
        }
        window_size = (600, 70)

        target_x, target_y = self.positioner.calculate_position(display_info, window_size)

        # Should be centered on second monitor: 1920 + (1920 - 600) / 2 = 2580
        self.assertEqual(target_x, 2580)
        # Should be at 25% vertically: 0 + 1080 * 0.25 = 270
        self.assertEqual(target_y, 270)

    def test_calculate_position_bounds_checking(self):
        """Test position calculation with bounds checking"""
        display_info = {
            'width': 800,
            'height': 600,
            'x': 0,
            'y': 0,
            'scale_factor': 1
        }
        window_size = (900, 700)  # Window larger than display

        target_x, target_y = self.positioner.calculate_position(display_info, window_size)

        # Should be constrained to display bounds
        self.assertEqual(target_x, 0)  # Can't go negative
        self.assertEqual(target_y, 0)  # Can't go negative

    def test_calculate_position_custom_vertical_percent(self):
        """Test position calculation with custom vertical percentage"""
        config = {
            "general": {
                "window_position_vertical_percent": 50,  # 50% instead of 25%
            }
        }
        positioner = WindowPositioner(self.mock_window, config)

        display_info = {
            'width': 1920,
            'height': 1080,
            'x': 0,
            'y': 0,
            'scale_factor': 1
        }
        window_size = (600, 70)

        target_x, target_y = positioner.calculate_position(display_info, window_size)

        # Should be at 50% vertically: 1080 * 0.50 = 540
        self.assertEqual(target_y, 540)

    def test_apply_position_success(self):
        """Test successful position application"""
        self.mock_window.get_realized.return_value = True
        self.mock_window.get_mapped.return_value = True
        self.mock_window.get_size.return_value = (600, 70)

        result = self.positioner.apply_position(100, 200)

        self.assertTrue(result)
        self.mock_window.move.assert_called_once_with(100, 200)

    def test_apply_position_realize_window(self):
        """Test position application when window needs to be realized"""
        self.mock_window.get_realized.return_value = False
        self.mock_window.get_mapped.return_value = True
        self.mock_window.get_size.return_value = (600, 70)

        result = self.positioner.apply_position(100, 200)

        self.assertTrue(result)
        self.mock_window.realize.assert_called_once()
        self.mock_window.move.assert_called_once_with(100, 200)

    def test_apply_position_failure(self):
        """Test position application failure handling"""
        self.mock_window.get_realized.return_value = True
        self.mock_window.get_mapped.return_value = True
        self.mock_window.get_size.return_value = (600, 70)
        self.mock_window.move.side_effect = Exception("Move failed")

        result = self.positioner.apply_position(100, 200)

        self.assertFalse(result)

    def test_fallback_positioning(self):
        """Test fallback positioning when all else fails"""
        with patch('launcher.ui.launcher_window.Gtk.WindowPosition.CENTER') as mock_center:
            result = self.positioner._position_window_fallback()

            self.assertTrue(result)
            self.mock_window.set_position.assert_called_once_with(mock_center)

    def test_fallback_positioning_failure(self):
        """Test fallback positioning failure"""
        self.mock_window.set_position.side_effect = Exception("Fallback failed")

        result = self.positioner._position_window_fallback()

        self.assertFalse(result)

    @patch('launcher.ui.launcher_window.WindowPositioner.get_main_display_info')
    @patch('launcher.ui.launcher_window.WindowPositioner.calculate_position')
    @patch('launcher.ui.launcher_window.WindowPositioner.apply_position')
    def test_position_window_success(self, mock_apply, mock_calculate, mock_display_info):
        """Test successful window positioning"""
        mock_display_info.return_value = {'width': 1920, 'height': 1080, 'x': 0, 'y': 0}
        mock_calculate.return_value = (660, 270)
        mock_apply.return_value = True
        self.mock_window.get_size.return_value = (600, 70)

        result = self.positioner.position_window()

        self.assertTrue(result)
        mock_display_info.assert_called_once()
        mock_calculate.assert_called_once()
        mock_apply.assert_called_once_with(660, 270)

    @patch('launcher.ui.launcher_window.WindowPositioner.get_main_display_info')
    @patch('launcher.ui.launcher_window.WindowPositioner._position_window_fallback')
    def test_position_window_no_display_info(self, mock_fallback, mock_display_info):
        """Test window positioning when display info is unavailable"""
        mock_display_info.return_value = None
        mock_fallback.return_value = True

        result = self.positioner.position_window()

        self.assertTrue(result)
        mock_fallback.assert_called_once()

    @patch('launcher.ui.launcher_window.WindowPositioner.get_main_display_info')
    @patch('launcher.ui.launcher_window.WindowPositioner._position_window_fallback')
    def test_position_window_exception_handling(self, mock_fallback, mock_display_info):
        """Test window positioning exception handling"""
        mock_display_info.side_effect = Exception("Display error")
        mock_fallback.return_value = True

        result = self.positioner.position_window()

        self.assertTrue(result)
        mock_fallback.assert_called_once()


class TestDisplayInfoMethods(unittest.TestCase):
    """Test cases for display information gathering methods"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_window = Mock()
        self.positioner = WindowPositioner(self.mock_window, {})

    @patch('launcher.ui.launcher_window.Gdk.Display.get_default')
    def test_get_display_info_fallback_success(self, mock_get_default):
        """Test fallback display info gathering success"""
        mock_display = Mock()
        mock_monitor = Mock()
        mock_geometry = Mock()
        mock_geometry.width = 1920
        mock_geometry.height = 1080
        mock_geometry.x = 0
        mock_geometry.y = 0

        mock_monitor.get_geometry.return_value = mock_geometry
        mock_monitor.get_scale_factor.return_value = 1
        mock_display.get_primary_monitor.return_value = mock_monitor
        mock_get_default.return_value = mock_display

        result = self.positioner.get_display_info_fallback()

        expected = {
            'width': 1920,
            'height': 1080,
            'x': 0,
            'y': 0,
            'scale_factor': 1
        }
        self.assertEqual(result, expected)

    @patch('launcher.ui.launcher_window.Gdk.Display.get_default')
    def test_get_display_info_fallback_no_primary_monitor(self, mock_get_default):
        """Test fallback display info when no primary monitor"""
        mock_display = Mock()
        mock_monitor = Mock()
        mock_geometry = Mock()
        mock_geometry.width = 1920
        mock_geometry.height = 1080
        mock_geometry.x = 0
        mock_geometry.y = 0

        mock_monitor.get_geometry.return_value = mock_geometry
        mock_monitor.get_scale_factor.return_value = 1
        mock_display.get_primary_monitor.return_value = None
        mock_display.get_n_monitors.return_value = 1
        mock_display.get_monitor.return_value = mock_monitor
        mock_get_default.return_value = mock_display

        result = self.positioner.get_display_info_fallback()

        expected = {
            'width': 1920,
            'height': 1080,
            'x': 0,
            'y': 0,
            'scale_factor': 1
        }
        self.assertEqual(result, expected)

    @patch('launcher.ui.launcher_window.Gdk.Display.get_default')
    @patch('launcher.ui.launcher_window.Gdk.Screen.get_default')
    def test_get_display_info_fallback_screen_fallback(self, mock_screen_default, mock_display_default):
        """Test fallback to screen when display methods fail"""
        mock_display_default.side_effect = Exception("Display failed")

        mock_screen = Mock()
        mock_screen.get_width.return_value = 1920
        mock_screen.get_height.return_value = 1080
        mock_screen_default.return_value = mock_screen

        result = self.positioner.get_display_info_fallback()

        expected = {
            'width': 1920,
            'height': 1080,
            'x': 0,
            'y': 0,
            'scale_factor': 1
        }
        self.assertEqual(result, expected)

    @patch('launcher.ui.launcher_window.Gdk.Display.get_default')
    @patch('launcher.ui.launcher_window.Gdk.Screen.get_default')
    def test_get_display_info_fallback_complete_failure(self, mock_screen_default, mock_display_default):
        """Test complete failure of display info gathering"""
        mock_display_default.side_effect = Exception("Display failed")
        mock_screen_default.side_effect = Exception("Screen failed")

        result = self.positioner.get_display_info_fallback()

        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()