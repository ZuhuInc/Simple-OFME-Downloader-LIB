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


if __name__ == "__main__":
    unittest.main()



