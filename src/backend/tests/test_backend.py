"""
Unit tests for Fanta OFME Downloader Backend
"""

import unittest
import os
import sys
import shutil
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.config import Config
from backend.database import DatabaseManager, GameEntry
from backend.steam import SteamManager
from backend.resolver import normalize_browser_name, LinkResolver
from backend.downloader import Downloader
from backend.extractor import Extractor


class TestBackend(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_config_lifecycle(self):
        cfg = Config(data_folder=self.temp_dir)
        cfg.set("rar_password", "custom-password")
        self.assertEqual(cfg.get("rar_password"), "custom-password")
        
        # Verify persistence reload
        cfg2 = Config(data_folder=self.temp_dir)
        self.assertEqual(cfg2.get("rar_password"), "custom-password")

    def test_database_parser(self):
        sample_db = """
# Header
GoFile (Test Game) [1.2.3]
ApproxSize: 2.5GB
Description: A great co-op test game.
Thumbnail: https://example.com/thumb.png
Origin: https://online-fix.me/test
MainGame: https://gofile.io/d/12345
Fix: https://gofile.io/d/67890

PixelDrain (Second Game) [v0.9]
ApproxSize: 500MB
Description: Indie adventure.
Thumbnail: 
Origin: https://online-fix.me/second
MainGame: https://pixeldrain.com/u/abcde
Fix: 
"""
        db = DatabaseManager(cache_dir=self.temp_dir, default_url="")
        games = db.parse_database(sample_db)
        self.assertEqual(len(games), 2)
        self.assertEqual(games[0].title, "Test Game")
        self.assertEqual(games[0].version, "1.2.3")
        self.assertEqual(games[0].host, "GoFile")
        self.assertEqual(games[0].approx_size, "2.5GB")
        self.assertGreater(games[0].size_bytes, 2 * 1024 * 1024 * 1024)
        
        self.assertEqual(games[1].title, "Second Game")
        self.assertEqual(games[1].host, "PixelDrain")

    def test_pixeldrain_resolve(self):
        url, name = LinkResolver.resolve_url("https://pixeldrain.com/u/sample123")
        self.assertEqual(url, "https://pixeldrain.com/api/file/sample123")

    def test_browser_normalize(self):
        self.assertEqual(normalize_browser_name("brave.exe"), "Brave")
        self.assertEqual(normalize_browser_name("Google Chrome"), "Google Chrome")
        self.assertEqual(normalize_browser_name("OperaGX launcher"), "Opera GX")

    def test_downloader_queue(self):
        dl = Downloader(download_path=self.temp_dir)
        job_id = dl.add_job("https://example.com/test.zip", "test.zip", {"title": "Test"})
        self.assertTrue(job_id.startswith("job_"))
        job = dl.get_job(job_id)
        self.assertIsNotNone(job)
        self.assertEqual(job["filename"], "test.zip")
        self.assertEqual(job["meta"]["title"], "Test")


if __name__ == "__main__":
    unittest.main()
