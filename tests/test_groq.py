import json
import pathlib
import tempfile
import unittest
from unittest import mock

import api
import config
import settings_ui


class GroqCompatibilityTests(unittest.TestCase):
    def test_old_config_gains_groq_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "config.json"
            path.write_text(json.dumps({"transcribe_provider": "openai"}), encoding="utf-8")
            with mock.patch.object(config, "CONFIG_FILE", path):
                conf = config.Config()
        self.assertEqual(conf["groq_base_url"], api.GROQ_URL)
        self.assertEqual(conf["groq_transcribe_model"], "whisper-large-v3-turbo")

    def test_groq_target_and_timestamp_model(self):
        with mock.patch.object(config.Config, "load"):
            conf = config.Config()
        conf["transcribe_provider"] = "groq"
        conf["groq_api_key"] = "test-key"
        target = conf.transcribe_target()
        self.assertEqual(target.provider, "groq")
        self.assertEqual(target.base_url, api.GROQ_URL)
        self.assertEqual(api.timestamp_model(target.provider, target.model), target.model)

    def test_groq_is_available_in_settings(self):
        self.assertIn(("Groq", "groq"), settings_ui.TRANSCRIBE_PROVIDERS)


if __name__ == "__main__":
    unittest.main()
