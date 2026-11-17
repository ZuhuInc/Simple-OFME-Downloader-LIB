"""
Unit tests for Fanta OFME Downloader Backend
"""

import unittest
import unittest.mock
import os
import sys
import shutil
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

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
        url, name, cookies = LinkResolver.resolve_url("https://pixeldrain.com/u/sample123")
        self.assertEqual(url, "https://pixeldrain.com/api/file/sample123?download")

    def test_fileditch_resolve(self):
        url, name, cookies = LinkResolver.resolve_url("https://fileditchfiles.st/balpha10/111/part1.rar")
        self.assertEqual(url, "https://fileditchfiles.st/balpha10/111/part1.rar")
        self.assertEqual(name, "part1.rar")

    def test_buzzheavier_resolve(self):
        url, name, cookies = LinkResolver.resolve_url("https://bzzhr.to/liksw0ew4pu8")
        self.assertTrue("ts.bzzhr.to" in url or "liksw0ew4pu8" in url)
        self.assertIsNotNone(name)
        self.assertTrue("CloverPit" in name)

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

    def test_add_and_update_game_local_db(self):
        cfg = Config(data_folder=self.temp_dir)
        local_db = os.path.join(self.temp_dir, "CustomData.json")
        cfg.set("local_db_path", local_db)
        cfg.set("use_local_db", True)

        db = DatabaseManager(cache_dir=self.temp_dir, default_url="", config=cfg)
        self.assertEqual(len(db.fetch_and_load()), 0)

        # Add game
        entry = db.add_or_update_game({
            "title": "Super Cool Game",
            "version": "1.0.5",
            "host": "GoFile",
            "approx_size": "10GB",
            "description": "Multiplayer adventure",
            "thumbnail": "https://example.com/thumb.jpg",
            "origin_url": "https://online-fix.me/games/super-cool",
            "parts": ["https://gofile.io/d/part1", "https://gofile.io/d/part2"],
            "fix_url": "https://gofile.io/d/fix",
            "category": "Co-op"
        })

        self.assertEqual(entry.title, "Super Cool Game")
        self.assertEqual(entry.version, "1.0.5")
        self.assertEqual(len(entry.parts), 2)
        self.assertEqual(len(db.games), 1)
        self.assertTrue(os.path.exists(local_db))

        # Switch to remote mode (use_local_db = False)
        cfg.set("use_local_db", False)
        # In remote mode, fetch should query GitHub Data.json or fallback
        games_remote = db.fetch_and_load(force_refresh=True)
        self.assertGreater(len(games_remote), 10)
        # Custom local game shouldn't be in remote unless added to remote repository
        custom_found = any(g.title == "Super Cool Game" for g in games_remote)
        self.assertFalse(custom_found)

    def test_extractor_detection_and_zip(self):
        extractor = Extractor()
        self.assertTrue(extractor.is_any_extractor_available())

        # Test zip creation and extraction
        import zipfile
        dummy_zip = os.path.join(self.temp_dir, "test_game.zip")
        extract_out = os.path.join(self.temp_dir, "extracted_game")
        
        with zipfile.ZipFile(dummy_zip, "w") as zf:
            zf.writestr("GameFolder/Game.exe", b"fake_game_binary_data")
            zf.writestr("GameFolder/readme.txt", b"Instructions")

        res = extractor.extract_archive(dummy_zip, extract_out)
        self.assertTrue(res["success"])
        self.assertTrue(os.path.exists(os.path.join(extract_out, "GameFolder", "Game.exe")))
        self.assertIsNotNone(res.get("exe_path"))

    def test_binary_vdf_and_steam_manager(self):
        from backend.steam import BinaryVDF, SteamManager
        # Test BinaryVDF encode/decode
        sample_dict = {
            "shortcuts": {
                "0": {
                    "appid": 3120485912,
                    "AppName": "Helldivers 2 (OnlineFix)",
                    "Exe": "\"C:\\Games\\Helldivers\\game.exe\"",
                    "StartDir": "\"C:\\Games\\Helldivers\\\"",
                    "icon": "",
                    "ShortcutPath": "",
                    "LaunchOptions": "",
                    "IsHidden": 0,
                    "AllowDesktopConfig": 1,
                    "AllowOverlay": 1,
                    "OpenVR": 0,
                    "Devkit": 0,
                    "DevkitGameID": "",
                    "DevkitOverrideAppID": 0,
                    "LastPlayTime": 0,
                    "FlatpakAppID": "",
                    "tags": {}
                }
            }
        }
        encoded = BinaryVDF.serialize(sample_dict)
        decoded = BinaryVDF.parse(encoded)
        self.assertIn("shortcuts", decoded)
        self.assertIn("0", decoded["shortcuts"])
        self.assertEqual(decoded["shortcuts"]["0"]["AppName"], "Helldivers 2 (OnlineFix)")
        self.assertEqual(decoded["shortcuts"]["0"]["appid"], 3120485912)

        # Test SteamManager shortcut addition and deletion in temp folder
        fake_steam = os.path.join(self.temp_dir, "Steam")
        fake_userdata = os.path.join(fake_steam, "userdata", "1004235037", "config")
        os.makedirs(fake_userdata, exist_ok=True)
        
        steam_mgr = SteamManager()
        steam_mgr.steam_path = fake_steam
        
        # Add non-steam game
        res_add = steam_mgr.add_non_steam_game(
            name="Test OFME Game",
            exe_path="C:\\Games\\Test\\Test.exe",
            start_dir="C:\\Games\\Test",
            account_id="1004235037"
        )
        self.assertTrue(res_add["success"])
        self.assertIsNotNone(res_add["appid"])
        self.assertIn("steam://rungameid/", res_add["steam_url"])

        # Fetch shortcuts
        shortcuts = steam_mgr.get_shortcuts(account_id="1004235037")
        self.assertEqual(len(shortcuts), 1)
        self.assertEqual(shortcuts[0]["name"], "Test OFME Game")
        self.assertEqual(shortcuts[0]["appid"], res_add["appid"])

        # Delete shortcut
        res_del = steam_mgr.delete_shortcut(identifier="Test OFME Game", account_id="1004235037")
        self.assertTrue(res_del["success"])
        self.assertEqual(len(steam_mgr.get_shortcuts(account_id="1004235037")), 0)

    def test_database_mirrors(self):
        import json
        sample_json = json.dumps([{
            "title": "Mirror Test Title",
            "version": "2.0.0",
            "host": "GoFile",
            "parts": ["https://gofile.io/d/part1", "https://gofile.io/d/part2"],
            "fix_url": "https://gofile.io/d/fix",
            "mirrors": {
                "PixelDrain": {
                    "parts": ["https://pixeldrain.com/u/p1", "https://pixeldrain.com/u/p2"],
                    "fix_url": "https://pixeldrain.com/u/fix"
                }
            }
        }])
        db = DatabaseManager(cache_dir=self.temp_dir, default_url="")
        games = db.parse_database(sample_json)
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0].title, "Mirror Test Title")
        self.assertIsNotNone(games[0].mirrors)
        self.assertIn("PixelDrain", games[0].mirrors)
        self.assertEqual(len(games[0].mirrors["PixelDrain"]["parts"]), 2)

        # Test to_dict serialization
        d = games[0].to_dict()
        self.assertIn("mirrors", d)
        self.assertIn("PixelDrain", d["mirrors"])

        # Test saving game with mirrors using isolated config and temp db path
        cfg = Config(data_folder=self.temp_dir)
        custom_db_path = os.path.join(self.temp_dir, "CustomData.json")
        cfg.set("local_db_path", custom_db_path)
        db_custom = DatabaseManager(cache_dir=self.temp_dir, default_url="", config=cfg)

        saved = db_custom.add_or_update_game({
            "title": "New Mirror Game",
            "version": "1.0",
            "host": "GoFile",
            "parts": ["https://gofile.io/d/main"],
            "mirrors": {
                "BuzzHeavier": {
                    "parts": ["https://buzzheavier.com/f/123"],
                    "fix_url": ""
                }
            }
        })
        self.assertIsNotNone(saved)
        self.assertEqual(saved.title, "New Mirror Game")
        self.assertIn("BuzzHeavier", saved.mirrors)

        with open(custom_db_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertIn("New Mirror Game", data)
            self.assertIn("mirrors", data["New Mirror Game"])
            self.assertIn("BuzzHeavier", data["New Mirror Game"]["mirrors"])

    def test_downloader_retry_job(self):
        dl = Downloader(download_path=self.temp_dir)
        job_id = dl.add_job("https://example.com/test.zip", "test.zip", {"title": "Retry Test"})
        self.assertTrue(job_id.startswith("job_"))
        
        # Simulate failure
        with dl._lock:
            dl.jobs[job_id].status = "error"
            dl.jobs[job_id].error_msg = "Connection reset by peer"

        job = dl.get_job(job_id)
        self.assertEqual(job["status"], "error")
        self.assertEqual(job["error_msg"], "Connection reset by peer")

        # Retry job without new url
        retry_res = dl.retry_job(job_id)
        self.assertTrue(retry_res)
        job_after = dl.get_job(job_id)
        self.assertIn(job_after["status"], ("queued", "resolving", "connecting", "downloading"))
        self.assertEqual(job_after["error_msg"], "")

        # Retry job with alternate mirror link
        with dl._lock:
            dl.jobs[job_id].status = "error"
            dl.jobs[job_id].error_msg = "HTTP 404"
        retry_mirror = dl.retry_job(job_id, new_url="https://pixeldrain.com/api/file/alt?download")
        self.assertTrue(retry_mirror)
        job_mirror = dl.get_job(job_id)
        self.assertIn(job_mirror["status"], ("queued", "resolving", "connecting", "downloading"))
        self.assertEqual(job_mirror["url"], "https://pixeldrain.com/api/file/alt?download")

    def test_resolver_dropbox(self):
        url = "https://www.dropbox.com/scl/fi/test/azimuth-windows.zip?rlkey=xyz&dl=0"
        resolved_url, filename, cookies = LinkResolver.resolve_url(url)
        self.assertIn("dl=1", resolved_url)
        self.assertEqual(filename, "azimuth-windows.zip")
        self.assertIsNone(cookies)

    def test_azimuth_config_and_exe_detection(self):
        game_root = os.path.join(self.temp_dir, "FH2_Test")
        os.makedirs(game_root, exist_ok=True)

        # Create dummy azimuth.exe and durango exe
        azimuth_path = os.path.join(game_root, "azimuth.exe")
        with open(azimuth_path, "wb") as f:
            f.write(b"AZIMUTH")

        durango_dir = os.path.join(game_root, "Anthem_1.0.0.64_x64__8wekyb3d8bbwe", "Mount")
        os.makedirs(durango_dir, exist_ok=True)
        durango_path = os.path.join(durango_dir, "forza_durango_release_final.exe")
        with open(durango_path, "wb") as f:
            f.write(b"DURANGO" * 1000)

        dlc_dir = os.path.join(game_root, "Forza Horizon 2 Storm Island (1.0.0.36)", "StormIsland_1.0.0.36_neutral__8wekyb3d8bbwe")
        os.makedirs(dlc_dir, exist_ok=True)

        # Verify _find_game_exe picks azimuth.exe and ignores durango
        found_exe = Extractor._find_game_exe(game_root)
        self.assertEqual(found_exe, azimuth_path)

        # Verify _ensure_azimuth_config creates valid ini
        Extractor._ensure_azimuth_config(game_root)
        ini_file = os.path.join(game_root, "data", "azimuth.ini")
        self.assertTrue(os.path.exists(ini_file))
        with open(ini_file, "r", encoding="utf-16") as f:
            ini_txt = f.read()
        self.assertIn("[launcher]", ini_txt)
        self.assertIn("game=1a96545b", ini_txt)
        self.assertIn("[title-1a96545b]", ini_txt)
        self.assertIn("Anthem_1.0.0.64_x64__8wekyb3d8bbwe", ini_txt)
        self.assertIn("StormIsland_1.0.0.36_neutral__8wekyb3d8bbwe", ini_txt)
        self.assertIn("player_name=Fanta OFME", ini_txt)

    def test_launch_game_endpoint(self):
        from flask import Flask
        from backend.controllers.games_controller import create_games_blueprint
        import unittest.mock

        cfg = Config(data_folder=self.temp_dir)
        db = DatabaseManager(cache_dir=self.temp_dir, default_url="", config=cfg)

        app = Flask(__name__)
        app.register_blueprint(create_games_blueprint(db, cfg))
        client = app.test_client()

        # 1. Missing executable returns 404
        res = client.post('/api/games/launch', json={"title": "NonExistentGame"})
        self.assertEqual(res.status_code, 404)
        self.assertFalse(res.get_json()["success"])

        # 2. Steam URL launch
        with unittest.mock.patch('os.startfile', create=True) as mock_startfile:
            res_steam = client.post('/api/games/launch', json={
                "title": "PEAK",
                "steam_url": "steam://rungameid/123456"
            })
            self.assertEqual(res_steam.status_code, 200)
            self.assertTrue(res_steam.get_json()["success"])
            self.assertEqual(res_steam.get_json()["method"], "steam")
            mock_startfile.assert_called_with("steam://rungameid/123456")

        # 3. Direct executable launch with subprocess.Popen mock
        dummy_exe = os.path.join(self.temp_dir, "Game.exe")
        with open(dummy_exe, "w") as f:
            f.write("dummy")

        with unittest.mock.patch('subprocess.Popen') as mock_popen:
            mock_proc = unittest.mock.MagicMock()
            mock_proc.pid = 9999
            mock_popen.return_value = mock_proc

            res_exe = client.post('/api/games/launch', json={
                "title": "TestGame",
                "exe_path": dummy_exe
            })
            self.assertEqual(res_exe.status_code, 200)
            data = res_exe.get_json()
            self.assertTrue(data["success"])
            self.assertEqual(data["method"], "executable")
            self.assertEqual(data["pid"], 9999)
            mock_popen.assert_called_once()
            self.assertEqual(mock_popen.call_args[0][0], [dummy_exe])
            self.assertEqual(mock_popen.call_args[1]["cwd"], self.temp_dir)

    def test_multipart_downloader_logic(self):
        downloader = Downloader(download_path=self.temp_dir)
        j1_id = downloader.add_job(
            "https://example.com/p1.rar",
            "Crime Simulator_Part1.rar",
            meta={"title": "Crime Simulator", "type": "main_part_1", "part_index": 1, "total_parts": 2}
        )
        j2_id = downloader.add_job(
            "https://example.com/p2.rar",
            "Crime Simulator_Part2.rar",
            meta={"title": "Crime Simulator", "type": "main_part_2", "part_index": 2, "total_parts": 2}
        )

        j1 = downloader.jobs[j1_id]
        j2 = downloader.jobs[j2_id]

        self.assertTrue(downloader._is_multipart_job(j1))
        self.assertTrue(downloader._is_multipart_job(j2))

        siblings = downloader._get_sibling_part_jobs_locked(j1)
        self.assertEqual(len(siblings), 2)
        self.assertEqual(siblings[0].id, j1_id)
        self.assertEqual(siblings[1].id, j2_id)

    def test_extractor_blocking_processes_and_routing(self):
        extractor = Extractor()

        # 1. Blocking process check on current python process directory
        running_blocking = extractor.get_blocking_processes(os.path.dirname(sys.executable))
        self.assertTrue(any("python" in p.lower() for p in running_blocking))

        # 2. Empty directory has zero blocking processes
        empty_dir = os.path.join(self.temp_dir, "empty_game")
        os.makedirs(empty_dir, exist_ok=True)
        self.assertEqual(extractor.get_blocking_processes(empty_dir), [])

        # 2b. Drive root process check safety guard
        self.assertEqual(extractor.get_blocking_processes("C:\\"), [])
        self.assertEqual(extractor.get_blocking_processes("D:\\"), [])

        # 3. extract_archive aborts if blocking processes detected in game folder
        dummy_archive = os.path.join(self.temp_dir, "dummy_fix.zip")
        with open(dummy_archive, "w") as f:
            f.write("dummy")

        with unittest.mock.patch.object(extractor, 'get_blocking_processes', return_value=['Launcher.exe']):
            res = extractor.extract_archive(
                archive_path=dummy_archive,
                extract_dir=empty_dir,
                is_fix=True
            )
            self.assertFalse(res["success"])
            self.assertIn("The game is currently running (Launcher.exe)", res["error"])

        # 3b. New game install does not check blocking processes on general library root
        new_game_archive = os.path.join(self.temp_dir, "new_game.zip")
        with open(new_game_archive, "w") as f:
            f.write("dummy")
        with unittest.mock.patch.object(extractor, 'get_blocking_processes') as mock_check, \
             unittest.mock.patch.object(extractor, 'is_winrar_available', return_value=True), \
             unittest.mock.patch('subprocess.run') as mock_run:
            mock_run.return_value = unittest.mock.MagicMock(returncode=0, stdout="", stderr="")
            res = extractor.extract_archive(
                archive_path=new_game_archive,
                extract_dir=empty_dir,
                game_title="Brand New Game",
                is_fix=False,
                delete_after=False
            )
            mock_check.assert_not_called()

        # 4. Multi-part part 2 auto-route to part 1
        part1_path = os.path.join(self.temp_dir, "Game_Part1.rar")
        part2_path = os.path.join(self.temp_dir, "Game_Part2.rar")
        with open(part1_path, "w") as f:
            f.write("part1")
        with open(part2_path, "w") as f:
            f.write("part2")

        with unittest.mock.patch.object(extractor, 'is_winrar_available', return_value=True), \
             unittest.mock.patch('subprocess.run') as mock_run:
            mock_run.return_value = unittest.mock.MagicMock(returncode=0, stdout="", stderr="")
            res = extractor.extract_archive(
                archive_path=part2_path,
                extract_dir=empty_dir,
                delete_after=False
            )
            self.assertTrue(res["success"])
            called_args = mock_run.call_args[0][0]
            self.assertIn(part1_path, called_args)

    def test_downloads_controller_extract_sync(self):
        """Test that /api/extract syncs status and cleans error_msg on downloader jobs"""
        from flask import Flask
        from src.backend.controllers.downloads_controller import create_downloads_blueprint
        from src.backend.downloader import Downloader

        app = Flask(__name__)
        config = Config(data_folder=self.temp_dir)
        downloader = Downloader(download_path=self.temp_dir, config=config, extractor=Extractor())
        mock_socketio = unittest.mock.MagicMock()
        mock_extractor = unittest.mock.MagicMock()
        mock_extractor.extract_archive.return_value = {
            "success": True,
            "game_dir": os.path.join(self.temp_dir, "Liar's Bar"),
            "exe_path": os.path.join(self.temp_dir, "Liar's Bar", "Liar's Bar.exe")
        }

        app.register_blueprint(create_downloads_blueprint(downloader, mock_extractor, config, mock_socketio))
        client = app.test_client()

        # Simulate a failed job
        job_id = downloader.add_job("https://example.com/liarsbar.rar", "Liars_Bar.rar", {"title": "Liar's Bar"})
        job = downloader.jobs[job_id]
        job.status = "completed"
        job.eta = "Done (Extraction Failed)"
        job.error_msg = "Extraction notice: The game is currently running (azimuth.exe)"

        # Trigger manual extraction
        resp = client.post('/api/extract', json={
            "job_id": job_id,
            "archive_path": job.dest_file,
            "title": "Liar's Bar"
        })
        self.assertEqual(resp.status_code, 200)

        # Wait briefly for thread to complete
        import time
        for _ in range(50):
            if job.eta == "Installed / Ready":
                break
            time.sleep(0.05)

        self.assertEqual(job.status, "completed")
        self.assertEqual(job.eta, "Installed / Ready")
        self.assertEqual(job.error_msg, "")
        self.assertEqual(job.meta.get("extracted_dir"), os.path.join(self.temp_dir, "Liar's Bar"))

    def test_cloud_sync_lifecycle(self):
        """Test CloudSyncManager detection, zipping, restoring, and metadata comparison"""
        from src.backend.cloud_sync import CloudSyncManager

        cloud_dir = os.path.join(self.temp_dir, "CloudSaves")
        mgr = CloudSyncManager(data_folder=self.temp_dir)
        mgr.settings["provider"] = "local_folder"
        mgr.settings["local_cloud_path"] = cloud_dir
        mgr.settings["auto_sync"] = True
        mgr.save_settings()

        # 1. Test settings persistence
        mgr2 = CloudSyncManager(data_folder=self.temp_dir)
        self.assertEqual(mgr2.get_provider(), "local_folder")
        self.assertTrue(mgr2.is_auto_sync_enabled())
        self.assertEqual(mgr2.settings.get("local_cloud_path"), cloud_dir)

        # 2. Test save folder detection with custom folder
        fake_save_dir = os.path.join(self.temp_dir, "FakeGameSaves")
        os.makedirs(fake_save_dir, exist_ok=True)
        with open(os.path.join(fake_save_dir, "save.dat"), "w") as f:
            f.write("save content 123")

        mgr.settings["custom_save_paths"]["TestGame"] = fake_save_dir
        detected_path, detect_type = mgr.detect_save_path("TestGame")
        self.assertEqual(detected_path, fake_save_dir)
        self.assertEqual(detect_type, "Custom")

        # 3. Test backup
        backup_res = mgr.backup_game("TestGame")
        self.assertTrue(backup_res["success"])
        expected_zip = os.path.join(cloud_dir, "TestGame", "TestGame_save.zip")
        self.assertTrue(os.path.exists(expected_zip))

        # 4. Test sync status
        status = mgr.get_game_sync_status("TestGame")
        self.assertTrue(status["local_exists"])
        self.assertTrue(status["cloud_exists"])
        self.assertEqual(status["sync_state"], "in_sync")

        # 5. Test restore with safe rollback
        os.remove(os.path.join(fake_save_dir, "save.dat"))
        self.assertFalse(os.path.exists(os.path.join(fake_save_dir, "save.dat")))
        restore_res = mgr.restore_game("TestGame")
        self.assertTrue(restore_res["success"])
        self.assertTrue(os.path.exists(os.path.join(fake_save_dir, "save.dat")))

    def test_cloud_controller_endpoints(self):
        """Test Flask /api/cloud blueprint endpoints"""
        from flask import Flask
        from src.backend.cloud_sync import CloudSyncManager
        from src.backend.controllers.cloud_controller import create_cloud_blueprint

        app = Flask(__name__)
        config = Config(data_folder=self.temp_dir)
        config.data["PEAK"] = {"downloaded": True, "location": os.path.join(self.temp_dir, "PEAK")}
        cloud_sync = CloudSyncManager(data_folder=self.temp_dir, config=config)
        db_mock = unittest.mock.MagicMock()
        db_mock.games = {}

        app.register_blueprint(create_cloud_blueprint(cloud_sync, config, db_mock))
        client = app.test_client()

        # GET /status
        resp = client.get('/api/cloud/status')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("provider", data)
        self.assertIn("auto_sync", data)

        # POST /configure
        resp = client.post('/api/cloud/configure', json={"auto_sync": True, "provider": "local_folder"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(cloud_sync.is_auto_sync_enabled())
        self.assertEqual(cloud_sync.get_provider(), "local_folder")

        # GET /auth_url
        resp = client.get('/api/cloud/auth_url')
        self.assertEqual(resp.status_code, 200)
        auth_url = resp.get_json().get("auth_url", "")
        self.assertTrue("accounts.google.com" in auth_url or "api/cloud/login" in auth_url)

        # GET /login
        resp = client.get('/api/cloud/login')
        self.assertEqual(resp.status_code, 200)
        self.assertIn("accounts.google.com/gsi/client", resp.get_data(as_text=True))

        # POST /save-token
        with unittest.mock.patch('requests.get') as mock_uget:
            mock_uget.return_value.status_code = 200
            mock_uget.return_value.json.return_value = {"email": "testuser@gmail.com"}
            resp = client.post('/api/cloud/save-token', json={"access_token": "ya29.testtoken", "expires_in": 3600})
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(cloud_sync.is_gdrive_connected())
            self.assertEqual(resp.get_json().get("email"), "testuser@gmail.com")

        # GET /games (with db_mock.games as dict)
        resp = client.get('/api/cloud/games')
        self.assertEqual(resp.status_code, 200)
        games_list = resp.get_json().get("games", [])
        self.assertTrue(any(g.get("title") == "PEAK" for g in games_list))

        # Test db_mock.games as a list of GameEntry objects (verifies fix for AttributeError 'list' has no attribute 'values')
        class FakeGame:
            def __init__(self, title, thumb=""):
                self.title = title
                self.thumbnail = thumb
        config.data["Liar's Bar"] = {"downloaded": True, "location": os.path.join(self.temp_dir, "Liar's Bar")}
        db_mock.games = [FakeGame("PEAK", "thumb.jpg"), FakeGame("Liar's Bar", "liar.jpg")]
        resp = client.get('/api/cloud/games')
        self.assertEqual(resp.status_code, 200)
        games_list = resp.get_json().get("games", [])
        self.assertTrue(any(g.get("title") == "Liar's Bar" for g in games_list))

        # POST /credentials
        creds_payload = {
            "credentials_json": {
                "installed": {
                    "client_id": "test_client_id_123.apps.googleusercontent.com",
                    "client_secret": "test_secret_456"
                }
            }
        }
        resp = client.post('/api/cloud/credentials', json=creds_payload)

        # Test deduplication: ensure "desktop defender" and alias "desktopdefender" never result in duplicate cards
        config.data["desktop defender"] = {"downloaded": True, "location": os.path.join(self.temp_dir, "desktop defender")}
        orig_list_all = cloud_sync.list_all_cloud_saves
        cloud_sync.list_all_cloud_saves = lambda: {
            "desktop defender": {"exists": True, "title": "desktop defender", "provider": "gdrive_api"},
            "desktopdefender": {"exists": True, "title": "desktop defender", "is_alias": True, "provider": "gdrive_api"}
        }
        resp = client.get('/api/cloud/games')
        self.assertEqual(resp.status_code, 200)
        dd_games = [g for g in resp.get_json().get("games", []) if "desktop" in g.get("title", "").lower()]
        self.assertEqual(len(dd_games), 1)
        self.assertEqual(dd_games[0]["title"], "desktop defender")
        cloud_sync.list_all_cloud_saves = orig_list_all
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(cloud_sync.has_gdrive_credentials())
        self.assertEqual(cloud_sync.settings.get("gdrive_client_id"), "test_client_id_123.apps.googleusercontent.com")

    def test_batch_update_outdated_games(self):
        """Test POST /api/version-check/batch-update endpoint and host assignment fix"""
        from flask import Flask
        from src.backend.controllers.version_checker_controller import create_version_checker_blueprint

        app = Flask(__name__)
        config = Config(data_folder=self.temp_dir)
        db_mock = unittest.mock.MagicMock()
        db_mock.games = []
        db_mock.add_or_update_game = unittest.mock.MagicMock()
        vc_mock = unittest.mock.MagicMock()
        vc_mock.clean_version_string = lambda v: str(v).lstrip('v')
        socketio_mock = unittest.mock.MagicMock()

        app.register_blueprint(create_version_checker_blueprint(vc_mock, db_mock, config, socketio_mock))
        client = app.test_client()

        with unittest.mock.patch('src.backend.scraper_service.OnlineFixScraper.scrape_game_page') as mock_scrape:
            mock_scrape.return_value = {
                "success": True,
                "title": "Grounded 2",
                "version": "0.6.0.3",
                "host": "GoFile",
                "parts": ["https://gofile.io/d/test1"],
                "fix_url": "https://gofile.io/d/fix",
                "approx_size": "15GB",
                "description": "Survival game",
                "thumbnail": "https://example.com/thumb.png"
            }

            payload = {
                "games": [
                    {
                        "title": "Grounded 2",
                        "origin_url": "https://online-fix.me/games/adventure/123-grounded-2.html",
                        "latest_version": "v0.6.0.3"
                    }
                ],
                "preferred_host": "GoFile"
            }

            resp = client.post('/api/version-check/batch-update', json=payload)
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data.get("success"))
            self.assertEqual(data.get("updated_count"), 1)
            self.assertIn("Grounded 2", data.get("updated_games", []))

            # Verify that add_or_update_game was called with valid catalog_entry including host
            db_mock.add_or_update_game.assert_called_once()
            called_entry = db_mock.add_or_update_game.call_args[0][0]
            self.assertEqual(called_entry["title"], "Grounded 2")
            self.assertEqual(called_entry["version"], "0.6.0.3")
            self.assertEqual(called_entry["host"], "GoFile")

    def test_self_hosted_cloud_provider(self):
        """Test Self-Hosted Cloud Save provider (Fanta-OFME-Cloud) full lifecycle and Flask endpoints"""
        import io
        import zipfile
        from flask import Flask
        from src.backend.cloud_sync import CloudSyncManager
        from src.backend.controllers.cloud_controller import create_cloud_blueprint

        mgr = CloudSyncManager(data_folder=self.temp_dir)
        mgr.settings["provider"] = "self_hosted"
        mgr.settings["self_hosted_url"] = "http://127.0.0.1:27845/"
        mgr.settings["self_hosted_api_key"] = "fanta_secret_123"
        mgr.save_settings()

        self.assertEqual(mgr._get_self_hosted_base_url(), "http://127.0.0.1:27845")
        self.assertEqual(mgr._get_self_hosted_headers().get("Authorization"), "Bearer fanta_secret_123")
        self.assertEqual(mgr._get_self_hosted_headers().get("X-API-Key"), "fanta_secret_123")
        self.assertTrue(mgr.is_self_hosted_configured())

        # 1. Test connection check (200 OK)
        with unittest.mock.patch('requests.get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {
                "status": "ok",
                "version": "1.0.0",
                "server_name": "Fanta-OFME-Cloud",
                "authenticated": True
            }
            conn_res = mgr.test_self_hosted_connection()
            self.assertTrue(conn_res["success"])
            self.assertEqual(conn_res["server_name"], "Fanta-OFME-Cloud")

        # 2. Test list_all_cloud_saves with self_hosted
        with unittest.mock.patch('requests.get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {
                "saves": [
                    {
                        "safe_name": "Schedule I",
                        "title": "Schedule I",
                        "size_bytes": 4096,
                        "mtime": 1730540000.0
                    }
                ]
            }
            index = mgr.list_all_cloud_saves()
            self.assertIn("Schedule I", index)
            self.assertEqual(index["Schedule I"]["provider"], "self_hosted")
            self.assertEqual(index["Schedule I"]["size_bytes"], 4096)

        # 3. Test backup_game with self_hosted
        save_dir = os.path.join(self.temp_dir, "ScheduleISaves")
        os.makedirs(save_dir, exist_ok=True)
        with open(os.path.join(save_dir, "player.json"), "w") as f:
            f.write('{"money": 9999}')
        mgr.settings["custom_save_paths"]["Schedule I"] = save_dir

        with unittest.mock.patch('requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"success": True}
            b_res = mgr.backup_game("Schedule I")
            self.assertTrue(b_res["success"])
            mock_post.assert_called_once()
            called_url = mock_post.call_args[0][0]
            self.assertIn("/api/saves/Schedule%20I", called_url)

        # 4. Test restore_game with self_hosted
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("restored_player.json", '{"money": 50000}')
        zip_bytes = zip_buf.getvalue()

        with unittest.mock.patch('requests.get') as mock_get:
            def side_effect(url, **kwargs):
                resp = unittest.mock.MagicMock()
                if url.endswith("/download"):
                    resp.status_code = 200
                    resp.iter_content.return_value = [zip_bytes]
                else:
                    resp.status_code = 200
                    resp.json.return_value = {
                        "exists": True,
                        "safe_name": "Schedule I",
                        "size_bytes": len(zip_bytes),
                        "mtime": 1730549999.0
                    }
                return resp

            mock_get.side_effect = side_effect
            r_res = mgr.restore_game("Schedule I")
            self.assertTrue(r_res["success"])
            self.assertTrue(os.path.exists(os.path.join(save_dir, "restored_player.json")))

        # 5. Test delete_cloud_save & Flask endpoints
        app = Flask(__name__)
        config = Config(data_folder=self.temp_dir)
        db_mock = unittest.mock.MagicMock()
        db_mock.games = {}
        app.register_blueprint(create_cloud_blueprint(mgr, config, db_mock))
        client = app.test_client()

        with unittest.mock.patch('requests.delete') as mock_del:
            mock_del.return_value.status_code = 200
            del_resp = client.post('/api/cloud/delete', json={"title": "Schedule I"})
            self.assertEqual(del_resp.status_code, 200)
            self.assertTrue(del_resp.get_json().get("success"))


        # 6. Test cross-provider transfer (/api/cloud/transfer: local_folder -> self_hosted)
        local_cloud_dir = os.path.join(self.temp_dir, "LocalCloud")
        game_folder = os.path.join(local_cloud_dir, "Schedule I")
        os.makedirs(game_folder, exist_ok=True)
        local_zip = os.path.join(game_folder, "Schedule I_save.zip")
        with open(local_zip, "wb") as f:
            f.write(zip_bytes)
        mgr.settings["local_cloud_path"] = local_cloud_dir

        with unittest.mock.patch('requests.get') as mock_get, unittest.mock.patch('requests.post') as mock_post:
            def transfer_get_side_effect(url, **kwargs):
                resp = unittest.mock.MagicMock()
                resp.status_code = 200
                if url.endswith("/api/status"):
                    resp.json.return_value = {"status": "ok", "version": "1.0.0"}
                elif url.endswith("/api/saves"):
                    resp.json.return_value = {"saves": []}
                return resp
            mock_get.side_effect = transfer_get_side_effect
            mock_post.return_value.status_code = 200

            tr_resp = client.post('/api/cloud/transfer', json={
                "source_provider": "local_folder",
                "target_provider": "self_hosted",
                "mode": "newer_or_missing"
            })
            self.assertEqual(tr_resp.status_code, 200)
            tr_data = tr_resp.get_json()
            self.assertTrue(tr_data["success"])
            self.assertEqual(tr_data["transferred"], 1)

        # 7. Test backup_game resolves Game Folder save path (<GameLocation>\Saves) via config_ref
        fish_install_dir = os.path.join(self.temp_dir, "games", "Fish Hunters Most Lethal Fishing Simulator")
        fish_saves_dir = os.path.join(fish_install_dir, "Saves")
        os.makedirs(fish_saves_dir, exist_ok=True)
        with open(os.path.join(fish_saves_dir, "First casting_app_0.2.5.bin"), "wb") as f:
            f.write(b"\x00\x01\x02" * 100)

        config.data["FISH HUNTERS MOST LETHAL FISHING SIMULATOR"] = {
            "downloaded": True,
            "location": fish_install_dir
        }
        mgr.config_ref = config
        with unittest.mock.patch('requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"success": True}
            b_fish = client.post('/api/cloud/backup', json={"title": "Fish Hunters Most Lethal Fishing Simulator"})
            self.assertEqual(b_fish.status_code, 200)
            self.assertTrue(b_fish.get_json().get("success"))

    def test_runners_system(self):
        import json
        from src.backend.runners_manager import RunnersManager
        from src.backend.controllers.games_controller import create_games_blueprint
        from flask import Flask

        # 1. Setup mock game folder with 3 runners
        mock_game_dir = os.path.join(self.temp_dir, "Zelda_Test")
        nx_dir = os.path.join(mock_game_dir, "NX2navi")
        hook_dir = os.path.join(mock_game_dir, "HookShot")
        os.makedirs(nx_dir, exist_ok=True)
        os.makedirs(hook_dir, exist_ok=True)

        nx_exe = os.path.join(nx_dir, "ocarina.exe")
        hook_exe = os.path.join(hook_dir, "hookshot.exe")
        with open(nx_exe, "w") as f: f.write("mock_nx")
        with open(hook_exe, "w") as f: f.write("mock_hook")

        runners_def = [
            {"id": "nx2navi", "name": "Recomp Option 1 (NX2navi)", "repo": "tangerineturtle1/NX2navi", "rel_path": "NX2navi/ocarina.exe", "folder": "NX2navi"},
            {"id": "hookshot", "name": "Recomp Option 2 (Hookshot)", "repo": "NotRexed/Hookshot", "rel_path": "HookShot/hookshot.exe", "folder": "HookShot"},
            {"id": "fritchii", "name": "Emulator (Fritchii)", "repo": "Frizti/Fritchii", "rel_path": "Fritchii/lichii.exe", "folder": "Fritchii", "args": ["games/rom.nup"]}
        ]

        # 2. Test get_runners_status
        statuses = RunnersManager.get_runners_status(mock_game_dir, runners_def)
        self.assertEqual(len(statuses), 3)
        self.assertTrue(statuses[0]["installed"])
        self.assertEqual(statuses[0]["id"], "nx2navi")
        self.assertTrue(statuses[1]["installed"])
        self.assertFalse(statuses[2]["installed"])

        # 3. Test Games Blueprint /runners endpoint
        app = Flask(__name__)
        config = Config(data_folder=self.temp_dir)
        temp_data_file = os.path.join(self.temp_dir, "TestGames.json")
        db_mgr = DatabaseManager(self.temp_dir, "https://example.com/db", config=config)
        db_mgr.get_active_db_path = lambda: temp_data_file
        test_game = {
            "title": "Zelda Test",
            "version": "1.1.1",
            "host": "PixelDrain",
            "runners": runners_def
        }
        db_mgr.add_or_update_game(test_game, installed_data=config.data)
        config.data["ZELDA TEST"] = {"location": mock_game_dir, "downloaded": True}
        config.save()

        bp = create_games_blueprint(db_mgr, config)
        app.register_blueprint(bp)
        client = app.test_client()

        resp = client.get('/api/games/runners?title=Zelda Test')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["runners"]), 3)

        # 4. Test Launch with chosen runner
        with unittest.mock.patch('subprocess.Popen') as mock_popen:
            mock_proc = unittest.mock.MagicMock()
            mock_proc.pid = 7777
            mock_popen.return_value = mock_proc

            launch_res = client.post('/api/games/launch', json={
                "title": "Zelda Test",
                "runner_id": "hookshot"
            })
            self.assertEqual(launch_res.status_code, 200)
            launch_data = launch_res.get_json()
            self.assertTrue(launch_data["success"])
            self.assertEqual(launch_data["pid"], 7777)
            # Verify hookshot exe was called
            self.assertIn("hookshot.exe", mock_popen.call_args[0][0][0])
            # Verify preferred runner saved
            self.assertEqual(config.data["ZELDA TEST"].get("preferred_runner"), "hookshot")

        # 5. Test runner update detection with .runner_version.json
        with open(os.path.join(nx_dir, ".runner_version.json"), "w") as vf:
            json.dump({"version": "v0.0.1"}, vf)
        
        with unittest.mock.patch.object(RunnersManager, 'get_latest_github_release', return_value={"tag_name": "v0.9.1", "assets": []}):
            statuses_updated = RunnersManager.get_runners_status(mock_game_dir, runners_def)
            nx_status = next(s for s in statuses_updated if s["id"] == "nx2navi")
            self.assertTrue(nx_status["update_available"])
            self.assertEqual(nx_status["installed_version"], "v0.0.1")
            self.assertEqual(nx_status["latest_version"], "v0.9.1")

    def test_disk_space_checker(self):
        """Test /api/downloads/disk_space endpoint with same vs split drives and space warnings"""
        from src.backend.controllers.downloads_controller import create_downloads_blueprint
        from flask import Flask

        app = Flask(__name__)
        config = Config(data_folder=self.temp_dir)
        
        # Mocks for downloader and extractor
        mock_downloader = unittest.mock.MagicMock()
        mock_downloader.download_path = os.path.join(self.temp_dir, "DownloadCache")
        os.makedirs(mock_downloader.download_path, exist_ok=True)
        mock_extractor = unittest.mock.MagicMock()
        mock_socketio = unittest.mock.MagicMock()

        bp = create_downloads_blueprint(mock_downloader, mock_extractor, config, mock_socketio)
        app.register_blueprint(bp)
        client = app.test_client()

        # 1. Test check with sufficient space
        target_install = os.path.join(self.temp_dir, "GameInstall")
        os.makedirs(target_install, exist_ok=True)

        resp = client.post('/api/downloads/disk_space', json={
            "install_path": target_install,
            "download_path": mock_downloader.download_path,
            "game_size": "2GB"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertIn("download", data)
        self.assertIn("install", data)
        self.assertEqual(data["download"]["needed_str"], "2.0 GB")

        # 2. Test insufficient space simulation
        with unittest.mock.patch('shutil.disk_usage', return_value=unittest.mock.MagicMock(total=100*1024**3, used=99*1024**3, free=1024**3)):  # 1 GB free
            resp_low = client.post('/api/downloads/disk_space', json={
                "install_path": target_install,
                "download_path": mock_downloader.download_path,
                "game_size": "24GB"
            })
            self.assertEqual(resp_low.status_code, 200)
            low_data = resp_low.get_json()
            self.assertFalse(low_data["has_sufficient_space"])
            self.assertIsNotNone(low_data["warning"])
            self.assertIn("Drive", low_data["warning"])

    def test_v215_hotfix_issues(self):
        """Test GAMES2 unwrapping, GameEntry.get/Steam shortcut add, downloader deduplication/source switch, and per-runner exe persistence."""
        import zipfile
        from flask import Flask
        from src.backend.controllers.steam_controller import create_steam_blueprint
        from src.backend.controllers.downloads_controller import create_downloads_blueprint
        from src.backend.controllers.games_controller import create_games_blueprint
        from src.backend.runners_manager import RunnersManager

        # 1. GAMES2 wrapper extraction & Zelda folder matching
        extractor = Extractor()
        zelda_zip = os.path.join(self.temp_dir, "zelda.zip")
        extract_root = os.path.join(self.temp_dir, "MyGames")
        os.makedirs(extract_root, exist_ok=True)
        with zipfile.ZipFile(zelda_zip, "w") as zf:
            zf.writestr("GAMES2/Legend of Zelda - Ocarina of Time/games/The_Legend_of_Zelda_Ocarina_of_Time_U1.1.1.nup", b"rom_data")
            zf.writestr("GAMES2/Legend of Zelda - Ocarina of Time/NX2navi/ocarina.exe", b"nx_bin")

        res_ext = extractor.extract_archive(
            archive_path=zelda_zip,
            extract_dir=extract_root,
            delete_after=False,
            game_title="The Legend of Zelda: Ocarina of Time"
        )
        self.assertTrue(res_ext["success"])
        expected_zelda_dir = os.path.join(extract_root, "Legend of Zelda - Ocarina of Time")
        self.assertEqual(os.path.normpath(res_ext["game_dir"]), os.path.normpath(expected_zelda_dir))
        self.assertTrue(os.path.isdir(expected_zelda_dir))
        self.assertFalse(os.path.exists(os.path.join(extract_root, "GAMES2")))

        # 2. GameEntry.get() + Steam shortcut add with GameEntry in db_manager.games + per-runner persistence
        fake_steam = os.path.join(self.temp_dir, "SteamMock")
        fake_userdata = os.path.join(fake_steam, "userdata", "123456789", "config")
        os.makedirs(fake_userdata, exist_ok=True)
        steam_mgr = SteamManager()
        steam_mgr.steam_path = fake_steam
        steam_mgr.get_user_accounts = lambda: [{"account_id": "123456789", "steamid64": "76561198000000000", "most_recent": True, "persona_name": "Tester"}]
        steam_mgr.get_active_account_id = lambda _=None: "123456789"

        hook_dir = os.path.join(expected_zelda_dir, "HookShot", "Hookshot-Win64", "bin")
        os.makedirs(hook_dir, exist_ok=True)
        hook_exe = os.path.join(hook_dir, "hookshot.exe")
        with open(hook_exe, "wb") as f:
            f.write(b"hook_bin")
        with open(os.path.join(expected_zelda_dir, "HookShot", "HookshotBuilder.exe"), "wb") as f:
            f.write(b"builder_bin")

        runners_def = [
            {"id": "nx2navi", "name": "NX2navi", "subtitle": "(Recomp 1)", "folder": "NX2navi", "rel_path": "NX2navi/ocarina.exe"},
            {"id": "hookshot", "name": "Hookshot", "subtitle": "(Recomp 2)", "folder": "HookShot", "rel_path": "HookShot/hookshot.exe"},
            {"id": "fritchii", "name": "Fritchii", "subtitle": "(Emulator)", "folder": "Fritchii", "rel_path": "Fritchii/lichii.exe", "args": ["games/The_Legend_of_Zelda_Ocarina_of_Time_U1.1.1.nup"]}
        ]

        cfg = Config(data_folder=self.temp_dir)
        cfg.data["THE LEGEND OF ZELDA: OCARINA OF TIME"] = {
            "downloaded": True,
            "location": expected_zelda_dir
        }
        cfg.save()

        db_mgr = DatabaseManager(self.temp_dir, "", config=cfg)
        game_entry = GameEntry(
            raw_id="the_legend_of_zelda_ocarina_of_time_pixeldrain",
            index=0,
            title="The Legend of Zelda: Ocarina of Time",
            version="1.1.1",
            host="PixelDrain",
            approx_size="24GB",
            description="Zelda",
            thumbnail="",
            origin_url="https://github.com/tangerineturtle1/NX2navi",
            main_game_url="https://pixeldrain.com/u/FFAi5WW3",
            fix_url="",
            runners=runners_def,
            steam_appid="999888"
        )
        self.assertEqual(game_entry.get("title"), "The Legend of Zelda: Ocarina of Time")
        self.assertEqual(game_entry.get("steam_appid"), "999888")
        self.assertEqual(game_entry.get("nonexistent_key", "fallback"), "fallback")
        db_mgr.games = [game_entry]
        db_mgr.update_installed_states(cfg.data)

        app = Flask(__name__)
        app.register_blueprint(create_steam_blueprint(steam_mgr, cfg, db_mgr))
        app.register_blueprint(create_games_blueprint(db_mgr, cfg))

        with unittest.mock.patch.object(steam_mgr.artwork_manager, 'download_and_save_artwork', return_value={}):
            client = app.test_client()
            resp_steam = client.post('/api/steam/shortcuts/add', json={
                "name": "The Legend of Zelda: Ocarina of Time",
                "exe_path": hook_exe,
                "runner_id": "hookshot",
                "account_id": "123456789"
            })
            self.assertEqual(resp_steam.status_code, 200)
            steam_data = resp_steam.get_json()
            self.assertTrue(steam_data["success"])
            saved_rec = cfg.data["THE LEGEND OF ZELDA: OCARINA OF TIME"]
            self.assertEqual(saved_rec["preferred_runner"], "hookshot")
            self.assertEqual(saved_rec["runner_exes"]["hookshot"], hook_exe)
            self.assertIn("hookshot", saved_rec["runner_steam_urls"])

        # 3. RunnersManager nested binary & /api/games/runners + /api/games/runners/select persistence
        with unittest.mock.patch.object(RunnersManager, 'get_latest_github_release', return_value=None):
            statuses = RunnersManager.get_runners_status(expected_zelda_dir, runners_def)
            hook_st = next(s for s in statuses if s["id"] == "hookshot")
            self.assertTrue(hook_st["installed"])
            self.assertEqual(os.path.normpath(hook_st["target_exe"]), os.path.normpath(hook_exe))
            fritch_st = next(s for s in statuses if s["id"] == "fritchii")
            self.assertIn("The_Legend_of_Zelda_Ocarina_of_Time_U1.1.1.nup", fritch_st["launch_options"])

            custom_fritch_exe = os.path.join(expected_zelda_dir, "CustomFritchii", "lichii.exe")
            os.makedirs(os.path.dirname(custom_fritch_exe), exist_ok=True)
            with open(custom_fritch_exe, "wb") as f:
                f.write(b"lichii_bin")

            resp_sel = client.post('/api/games/runners/select', json={
                "title": "The Legend of Zelda: Ocarina of Time",
                "runner_id": "fritchii",
                "exe_path": custom_fritch_exe
            })
            self.assertEqual(resp_sel.status_code, 200)
            sel_data = resp_sel.get_json()
            self.assertTrue(sel_data["success"])
            self.assertEqual(sel_data["preferred_runner"], "fritchii")
            self.assertEqual(os.path.normpath(sel_data["runner_exes"]["fritchii"]), os.path.normpath(custom_fritch_exe))
            # Hookshot path remains saved too
            self.assertEqual(os.path.normpath(sel_data["runner_exes"]["hookshot"]), os.path.normpath(hook_exe))

            resp_run = client.get('/api/games/runners?title=The Legend of Zelda: Ocarina of Time')
            self.assertEqual(resp_run.status_code, 200)
            run_data = resp_run.get_json()
            self.assertEqual(run_data["preferred_runner"], "fritchii")
            fritch_res = next(s for s in run_data["runners"] if s["id"] == "fritchii")
            self.assertTrue(fritch_res["installed"])
            self.assertEqual(os.path.normpath(fritch_res["target_exe"]), os.path.normpath(custom_fritch_exe))

        # 4. Downloader deduplication & switch_job_source (prevents 3 -> 6 doubling)
        dl = Downloader(download_path=self.temp_dir, max_concurrency=2, config=cfg, extractor=extractor)
        dl._check_queue = lambda: None  # Keep jobs deterministic without spawning network threads
        part_ids = []
        for idx in range(1, 4):
            jid = dl.add_job(
                f"https://pixeldrain.com/u/pd{idx}",
                f"The Legend of Zelda - Ocarina of Time.part{idx}.rar",
                {"title": "The Legend of Zelda: Ocarina of Time", "part_index": idx, "total_parts": 3, "type": f"main_part_{idx}", "host": "PixelDrain"}
            )
            part_ids.append(jid)
        self.assertEqual(len(dl.jobs), 3)

        # Create partial files and pause parts 1 & 2 (leaving part 3 queued)
        for idx, jid in enumerate(part_ids):
            j = dl.jobs[jid]
            with open(j.dest_file + ".part", "wb") as pf:
                pf.write(b"partial")
            if idx < 2:
                j.status = "paused"
                j._pause_event.clear()

        # Re-queueing same game parts from another source must reuse existing 3 jobs, not create 6
        for idx in range(1, 4):
            dl.add_job(
                f"https://buzzheavier.com/bh{idx}",
                f"The Legend of Zelda - Ocarina of Time_Part{idx}.rar",
                {"title": "The Legend of Zelda: Ocarina of Time", "part_index": idx, "total_parts": 3, "type": f"main_part_{idx}", "host": "BuzzHeavier"}
            )
        self.assertEqual(len(dl.jobs), 3)
        self.assertFalse(os.path.exists(dl.jobs[part_ids[0]].dest_file + ".part"))

        # Test /api/downloads/switch-source endpoint switches all 3 parts in-place to GoFile
        dl_app = Flask(__name__)
        mock_socketio = unittest.mock.MagicMock()
        dl_app.register_blueprint(create_downloads_blueprint(dl, extractor, cfg, mock_socketio))
        dl_client = dl_app.test_client()
        for idx, jid in enumerate(part_ids):
            dl.jobs[jid].status = "paused"
            with open(dl.jobs[jid].dest_file + ".part", "wb") as pf:
                pf.write(b"bh_partial")

        resp_sw = dl_client.post('/api/downloads/switch-source', json={
            "job_id": part_ids[0],
            "new_host": "GoFile",
            "part_urls": [
                "https://gofile.io/d/YrkeaD8s",
                "https://gofile.io/d/ovEdCmmu",
                "https://gofile.io/d/ZRf06jl0"
            ],
            "switch_all_parts": True
        })
        self.assertEqual(resp_sw.status_code, 200)
        sw_data = resp_sw.get_json()
        self.assertTrue(sw_data["success"])
        self.assertEqual(sw_data["switched_count"], 3)
        self.assertEqual(len(dl.jobs), 3)
        self.assertEqual(dl.jobs[part_ids[0]].url, "https://gofile.io/d/YrkeaD8s")
        self.assertEqual(dl.jobs[part_ids[1]].url, "https://gofile.io/d/ovEdCmmu")
        self.assertEqual(dl.jobs[part_ids[2]].url, "https://gofile.io/d/ZRf06jl0")
        self.assertEqual(dl.jobs[part_ids[0]].meta.get("host"), "GoFile")
        self.assertFalse(os.path.exists(dl.jobs[part_ids[0]].dest_file + ".part"))

        # Test cancel_job removes job cleanly
        self.assertTrue(dl.cancel_job(part_ids[0]))
        self.assertEqual(len(dl.get_all_jobs()), 2)

    def test_runner_version_comparison_and_builder_once(self):
        """Test pre-bundled version comparison (Bundled vs remote tag) and Run Builder Once workflow after runner updates."""
        import json
        import zipfile
        import io
        from flask import Flask
        from src.backend.runners_manager import RunnersManager
        from src.backend.controllers.games_controller import create_games_blueprint

        game_dir = os.path.join(self.temp_dir, "Zelda_Builder_Test")
        hook_dir = os.path.join(game_dir, "HookShot")
        os.makedirs(hook_dir, exist_ok=True)
        hook_exe = os.path.join(hook_dir, "hookshot.exe")
        with open(hook_exe, "wb") as f:
            f.write(b"old_hookshot")
        # Set older timestamp on bundled hookshot.exe
        old_ts = 1700000000.0
        os.utime(hook_exe, (old_ts, old_ts))

        runners_def = [
            {
                "id": "hookshot",
                "name": "Hookshot",
                "subtitle": "(Recomp 2)",
                "repo": "https://git.notrexed.dev/Hookshot/Hookshot",
                "asset_pattern": "Hookshot-.*Windows-x64\\.zip|HookshotBuilder\\.exe",
                "folder": "HookShot",
                "rel_path": "HookShot/hookshot.exe"
            }
        ]

        # 1. Pre-bundled runner (no .runner_version.json) reports 'Bundled' and flags update_available=True
        fake_release = {
            "tag_name": "v0.2.0",
            "assets": [{
                "name": "Hookshot-0.2.0-Windows-x64.zip",
                "browser_download_url": "https://git.notrexed.dev/Hookshot/Hookshot/releases/download/v0.2.0/Hookshot-0.2.0-Windows-x64.zip",
                "size": 1024
            }]
        }
        with unittest.mock.patch.object(RunnersManager, 'get_latest_github_release', return_value=fake_release):
            statuses = RunnersManager.get_runners_status(game_dir, runners_def)
            self.assertEqual(len(statuses), 1)
            self.assertTrue(statuses[0]["installed"])
            self.assertEqual(statuses[0]["installed_version"], "Bundled")
            self.assertEqual(statuses[0]["latest_version"], "v0.2.0")
            self.assertTrue(statuses[0]["update_available"])

        # 2. Updating runner extracts HookshotBuilder.exe without replacing old hookshot.exe -> needs_build=True
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("HookshotBuilder.exe", b"new_builder_binary")
        zip_bytes = buf.getvalue()

        class FakeHTTPResp:
            def __init__(self, data):
                self._stream = io.BytesIO(data)
            def read(self, n=-1):
                return self._stream.read(n)
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        with unittest.mock.patch.object(RunnersManager, 'get_latest_github_release', return_value=fake_release), \
             unittest.mock.patch('urllib.request.urlopen', return_value=FakeHTTPResp(zip_bytes)):
            res_upd = RunnersManager.install_or_update_runner(game_dir, runners_def[0])
            self.assertTrue(res_upd["success"])
            self.assertTrue(res_upd["needs_build"])
            self.assertIn("HookshotBuilder.exe", res_upd["builder_exe"])

        with unittest.mock.patch.object(RunnersManager, 'get_latest_github_release', return_value=fake_release):
            st_after = RunnersManager.get_runners_status(game_dir, runners_def)[0]
            self.assertEqual(st_after["installed_version"], "v0.2.0")
            self.assertFalse(st_after["update_available"])
            self.assertTrue(st_after["needs_build"])
            self.assertTrue(st_after["has_builder"])

        # 3. Calling /api/games/launch or /api/games/runners/run-builder launches the Builder when needs_build=True
        app = Flask(__name__)
        cfg = Config(data_folder=self.temp_dir)
        cfg.data["ZELDA BUILDER"] = {"downloaded": True, "location": game_dir}
        cfg.save()
        db_mgr = DatabaseManager(self.temp_dir, "", config=cfg)
        db_mgr.games = [GameEntry(
            raw_id="zelda_builder", index=0, title="Zelda Builder", version="1.0",
            host="GoFile", approx_size="1GB", description="", thumbnail="",
            origin_url="", main_game_url="", fix_url="", runners=runners_def
        )]
        app.register_blueprint(create_games_blueprint(db_mgr, cfg))
        client = app.test_client()

        with unittest.mock.patch('subprocess.Popen') as mock_popen:
            mock_proc = unittest.mock.MagicMock()
            mock_proc.pid = 4242
            mock_proc.wait.return_value = 0
            mock_popen.return_value = mock_proc

            resp_launch = client.post('/api/games/launch', json={"title": "Zelda Builder", "runner_id": "hookshot"})
            self.assertEqual(resp_launch.status_code, 200)
            launch_json = resp_launch.get_json()
            self.assertTrue(launch_json["success"])
            self.assertEqual(launch_json["method"], "builder")
            self.assertTrue(launch_json["builder_launched"])
            self.assertIn("HookshotBuilder.exe", launch_json["exe_path"])

        # 4. Simulate builder producing a fresh hookshot.exe -> needs_build clears automatically
        new_ts = old_ts + 100.0
        os.utime(hook_exe, (new_ts, new_ts))
        RunnersManager.mark_builder_completed(game_dir, runners_def[0])
        st_built = RunnersManager.get_runners_status(game_dir, runners_def, check_remote=False)[0]
        self.assertFalse(st_built["needs_build"])
        self.assertEqual(os.path.normpath(st_built["primary_exe"]), os.path.normpath(hook_exe))

        # 5. Triforce repo routing & _infer_local_version filtering
        triforce_urls, _ = RunnersManager._build_api_urls("https://git.triforceproject.com/triforce/source")
        self.assertIn("triforce/downloads/releases", triforce_urls[0])
        self.assertEqual(
            RunnersManager.get_release_page_url("https://git.triforceproject.com/triforce/source"),
            "https://git.triforceproject.com/triforce/source"
        )

        # Verify _infer_local_version ignores .NET runtime DLLs (e.g. 8.0.3426) and extracts nightly/setup versions
        longshot_test_dir = os.path.join(self.temp_dir, "Longshot_Ver_Test")
        builder_sub = os.path.join(longshot_test_dir, "LongshotBuilder")
        os.makedirs(builder_sub, exist_ok=True)
        with open(os.path.join(builder_sub, "System.Runtime.8.0.3426.dll"), "wb") as f:
            f.write(b"dll")
        self.assertEqual(RunnersManager._infer_local_version(longshot_test_dir), "")

        nightly_sub = os.path.join(longshot_test_dir, "nightly-80-7315957c")
        os.makedirs(nightly_sub, exist_ok=True)
        self.assertEqual(RunnersManager._infer_local_version(longshot_test_dir), "")

        picked = RunnersManager._select_release_from_list(
            [
                {"tag_name": "nightly-400-abc", "assets": [{"name": "LongshotBuilder-nightly-400-windows-x64.zip"}]},
                {"tag_name": "v3.0.0-rc.7", "assets": [{"name": "LongshotBuilder-v3.0.0-rc.7-windows-x64.zip"}]},
            ],
            r"LongshotBuilder.*\.zip"
        )
        self.assertEqual(picked["tag_name"], "v3.0.0-rc.7")

        nx_test_dir = os.path.join(self.temp_dir, "NX_Ver_Test")
        os.makedirs(os.path.join(nx_test_dir, "NX2navi", "launcher", "triforce"), exist_ok=True)
        with open(os.path.join(nx_test_dir, "NX2navi", "NX2navi-Setup-0.8.0.exe"), "wb") as f:
            f.write(b"setup")
        triforce_setup = os.path.join(nx_test_dir, "NX2navi", "launcher", "triforce", "TriforceSetup.exe")
        with open(triforce_setup, "wb") as f:
            f.write(b"triforce_setup")
        self.assertEqual(RunnersManager._infer_local_version(os.path.join(nx_test_dir, "NX2navi")), "0.8.0")
        triforce_runner = {
            "id": "nx2navi",
            "name": "Triforce",
            "folder": "NX2navi",
            "rel_path": "NX2navi/ocarina.exe"
        }
        self.assertEqual(
            os.path.normpath(RunnersManager.find_builder_executable(nx_test_dir, triforce_runner)),
            os.path.normpath(triforce_setup)
        )


if __name__ == "__main__":
    unittest.main()



