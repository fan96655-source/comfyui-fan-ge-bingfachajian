import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import get_settings  # noqa: E402


class ConfigTests(unittest.TestCase):
    def test_default_name(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                get_settings().assistant_name,
                "🚀 帆 AI 视觉个人助手",
            )

    def test_manual_json(self):
        value = '[{"provider":"demo","remaining":12.5}]'
        with patch.dict(
            os.environ,
            {"FAN_AI_MANUAL_BALANCES_JSON": value},
            clear=True,
        ):
            self.assertEqual(
                get_settings().manual_balances[0]["remaining"],
                12.5,
            )


if __name__ == "__main__":
    unittest.main()
