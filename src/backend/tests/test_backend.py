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
    def test_scraper_cleaning(self):
        from backend.scraper_service import OnlineFixScraper
        self.assertEqual(OnlineFixScraper._clean_version("v1.2.3.a [Online-Fix.me]"), "1.2.3.a")
        self.assertEqual(OnlineFixScraper._clean_version("Версия игры: 2.1.a по сети"), "2.1.a")
        self.assertEqual(OnlineFixScraper._clean_version("Build 17120 Download Direct"), "17120")

    def test_steamrip_scraper_parsing(self):
        from backend.scraper_service import OnlineFixScraper
        from unittest.mock import MagicMock

        sample_html = """
        <html>
        <head><title>S.T.A.L.K.E.R. 2: Heart of Chornobyl Free Download (v2.0.3) — SteamRIP</title></head>
        <body>
            <h1>S.T.A.L.K.E.R. 2: Heart of Chornobyl Free Download (v2.0.3)</h1>
            <div class="entry-content">
                <p>+ Game Size: 188 GB</p>
                <p>+ Version: v2.0.3 (Build 24914692) + 4 DLC & Extras | Full Version</p>
                <p>The Heart of Chornobyl calls for stalkers willing to explore the dangerous anomalies.</p>
                
                <p style="text-align: center;">
                    <strong>BZZHR</strong>
                    <br>
                    <a href="//bzzhr.to/x1u8zy8x8kp3" class="shortc-button medium purple">DOWNLOAD HERE</a>
                </p>
                
                <p style="text-align: center;">
                    <span style="color: rgb(124, 106, 247);">FileDitch</span>
                    <br>
                    <a href="//fileditchfiles.st/balpha10/111/part1.rar" class="shortc-button medium purple">PART 1</a>
                    <a href="//fileditchfiles.st/balpha10/222/part2.rar" class="shortc-button medium purple">PART 2</a>
                    <a href="//fileditchfiles.st/balpha10/333/part3.rar" class="shortc-button medium purple">PART 3</a>
                    <a href="//fileditchfiles.st/balpha10/444/part4.rar" class="shortc-button medium purple">PART 4</a>
                </p>
            </div>
        </body>
        </html>
        """

        scraper = OnlineFixScraper()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = sample_html
        scraper.session.get = MagicMock(return_value=mock_resp)

        result = scraper.scrape_game_page("https://steamrip.com/s-t-a-l-k-e-r-2-heart-of-chornobyl-free-download/")
        self.assertTrue(result["success"])
        self.assertIn("S.T.A.L.K.E.R. 2", result["title"])
        self.assertIn("2.0.3", result["version"])
        self.assertEqual(result["approx_size"], "188GB")
        self.assertIn("BuzzHeavier", result["available_hosts"])
        self.assertIn("FileDitch", result["available_hosts"])
        self.assertEqual(len(result["available_hosts"]["BuzzHeavier"]["parts"]), 1)
        self.assertEqual(result["available_hosts"]["BuzzHeavier"]["parts"][0], "https://bzzhr.to/x1u8zy8x8kp3")
        self.assertEqual(len(result["available_hosts"]["FileDitch"]["parts"]), 4)
        self.assertEqual(result["available_hosts"]["FileDitch"]["parts"][0], "https://fileditchfiles.st/balpha10/111/part1.rar")
        self.assertEqual(result["available_hosts"]["FileDitch"]["parts"][3], "https://fileditchfiles.st/balpha10/444/part4.rar")


if __name__ == "__main__":
    unittest.main()


