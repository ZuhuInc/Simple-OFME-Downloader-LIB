"""
Fanta OFME Downloader - Online-Fix Scraper Service
Handles authenticated scraping of game details and download links from Online-Fix.me
and its hosters portal (hosters.online-fix.me).
"""

import json
import re
import urllib.parse
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, List, Optional


class OnlineFixScraper:
    def __init__(self, username: str = "", password: str = ""):
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
            "Referer": "https://online-fix.me/"
        })
        self._is_logged_in = False

    def update_credentials(self, username: str, password: str):
        if username != self.username or password != self.password:
            self.username = username
            self.password = password
            self._is_logged_in = False

    def login(self) -> bool:
        """Logs in to online-fix.me to enable access to member-only hoster links."""
        if not self.username or not self.password:
            print("[Scraper] No Online-Fix credentials provided. Continuing as guest.")
            return False

        try:
            login_url = "https://online-fix.me/"
            payload = {
                "login_name": self.username,
                "login_password": self.password,
                "login": "submit"
            }
            resp = self.session.post(login_url, data=payload, timeout=12)
            if resp.status_code == 200 and ("logout" in resp.text.lower() or self.username.lower() in resp.text.lower()):
                self._is_logged_in = True
                print(f"[Scraper] Successfully logged in to Online-Fix as {self.username}")
                return True
            else:
                print(f"[Scraper] Login response received (Status: {resp.status_code}). Session initialized.")
                self._is_logged_in = True
                return True
        except Exception as e:
            print(f"[Scraper] Login error: {e}")
            return False

    def scrape_game_page(self, origin_url: str, preferred_host: str = "GoFile") -> Dict[str, Any]:
        """
        Routes scraping to either Online-Fix or SteamRIP scraper based on origin URL.
        """
        if not origin_url or not origin_url.startswith("http"):
            return {"success": False, "error": "Invalid origin URL"}

        if "steamrip.com" in origin_url.lower():
            return self.scrape_steamrip_page(origin_url, preferred_host=preferred_host)
        else:
            return self.scrape_onlinefix_page(origin_url, preferred_host=preferred_host)

    def scrape_onlinefix_page(self, origin_url: str, preferred_host: str = "GoFile") -> Dict[str, Any]:
        """
        Scrapes game metadata from the Online-Fix post and pulls direct download links
        from the hosters.online-fix.me portal.
        """
        if not self._is_logged_in and self.username and self.password:
            self.login()

        try:
            resp = self.session.get(origin_url, timeout=15)
            if resp.status_code != 200:
                return {"success": False, "error": f"Failed to fetch game page (Status {resp.status_code})"}

            html = resp.text
            soup = BeautifulSoup(html, "html.parser")

            # 1. Parse Game Title
            title = ""
            h1 = soup.find("h1")
            if h1:
                title = h1.get_text(separator=" ").strip()
                # Clean Russian suffixes like "по сети"
                title = re.sub(r"(?:по\s*сети|онлайн|скачать|free|download).*", "", title, flags=re.IGNORECASE).strip()

            if not title:
                title_tag = soup.find("title")
                if title_tag:
                    title = title_tag.get_text().split("по сети")[0].split("—")[0].strip()

            # 2. Parse Live Version
            version = ""
            quotes = soup.find_all(class_="quote")
            for q in quotes:
                text = q.get_text(separator=" ")
                m = re.search(r"(?:Версия\s*игры|Версия|Version)\s*:\s*([^\n\r<\|]+)", text, re.IGNORECASE)
                if m:
                    version = self._clean_version(m.group(1))
                    if version:
                        break

            if not version:
                m = re.search(r"Версия\s*игры\s*:\s*<b>\s*([^<]+)\s*</b>", html, re.IGNORECASE)
                if m:
                    version = self._clean_version(m.group(1))

            # 3. Parse Description & Approx Size
            description = ""
            desc_div = soup.find("div", id="news-id-") or soup.find("div", class_="full-news") or soup.find("article")
            if desc_div:
                p_tags = desc_div.find_all("p")
                for p in p_tags:
                    p_txt = p.get_text(strip=True)
                    if len(p_txt) > 40 and not p_txt.startswith("Версия") and not p_txt.startswith("Язык"):
                        description = p_txt
                        break

            approx_size = ""
            size_m = re.search(r"(?:Размер(?:\s*игры)?|Size|File\s*size)\s*:\s*(?:<b>)?\s*([0-9\.,]+\s*(?:GB|MB|KB|ГБ|МБ|КБ|G|M))", html, re.IGNORECASE)
            if size_m:
                approx_size = size_m.group(1).strip().replace("ГБ", "GB").replace("МБ", "MB")

            # 4. Find Hosters Portal Link
            hosters_url = ""
            hoster_links = soup.find_all("a", href=True)
            for a in hoster_links:
                href = a["href"]
                if "hosters.online-fix.me" in href:
                    hosters_url = href
                    break

            if not hosters_url:
                # Regex fallback in raw html
                hm = re.search(r'href=["\'](https?://hosters\.online-fix\.me[^"\']+)["\']', html)
                if hm:
                    hosters_url = hm.group(1)

            available_hosts: Dict[str, Dict[str, Any]] = {}
            if hosters_url:
                print(f"[Scraper] Found hosters portal link: {hosters_url}")
                available_hosts = self._scrape_hosters_portal(hosters_url)

            # Determine selected host data
            selected_host = preferred_host
            if selected_host not in available_hosts and available_hosts:
                if "GoFile" in available_hosts:
                    selected_host = "GoFile"
                else:
                    selected_host = next(iter(available_hosts))

            host_data = available_hosts.get(selected_host, {"parts": [], "fix_url": ""})

            # Check if filename has version clue if version is missing
            if not version and host_data.get("inferred_version"):
                version = host_data["inferred_version"]

            return {
                "success": True,
                "title": title or "New Game",
                "version": version or "1.0",
                "host": selected_host,
                "parts": host_data.get("parts", []),
                "fix_url": host_data.get("fix_url", ""),
                "approx_size": approx_size or "N/A",
                "description": description,
                "origin_url": origin_url,
                "hosters_url": hosters_url,
                "available_hosts": available_hosts
            }

        except Exception as e:
            print(f"[Scraper] Online-Fix scraping error: {e}")
            return {"success": False, "error": str(e)}

    def scrape_steamrip_page(self, origin_url: str, preferred_host: str = "BuzzHeavier") -> Dict[str, Any]:
        """
        Scrapes game metadata and direct download buttons/parts directly from a SteamRIP page.
        """
        try:
            resp = self.session.get(origin_url, timeout=15)
            if resp.status_code != 200:
                return {"success": False, "error": f"Failed to fetch SteamRIP page (Status {resp.status_code})"}

            html = resp.text
            soup = BeautifulSoup(html, "html.parser")

            # 1. Parse Title
            title = ""
            h1 = soup.find("h1")
            if h1:
                raw_h1 = h1.get_text(separator=" ").strip()
                # Remove (v...) or (Build ...) or Free Download from title
                title = re.sub(r"\s*(?:\([^\)]*\)|Free\s*Download|Direct\s*Download|PC\s*Game|Full\s*Version).*", "", raw_h1, flags=re.IGNORECASE).strip()

            if not title:
                title_tag = soup.find("title")
                if title_tag:
                    title = title_tag.get_text().split("Free Download")[0].split("—")[0].strip()

            # 2. Parse Version
            version = ""
            # Search for version in bullet items (+ Version: ...)
            for li in soup.find_all(["li", "p", "div"]):
                txt = li.get_text(strip=True)
                if "version:" in txt.lower() or "версия:" in txt.lower():
                    m = re.search(r"(?:Version|Версия)\s*:\s*([^\n\r<\|]+)", txt, re.IGNORECASE)
                    if m:
                        version = self._clean_version(m.group(1))
                        if version:
                            break

            if not version and h1:
                # Fallback to h1 parentheses, e.g. (v2.0.3)
                m = re.search(r"\(([^\)]+)\)", h1.get_text())
                if m:
                    version = self._clean_version(m.group(1))

            # 3. Parse Size
            approx_size = ""
            for elem in soup.find_all(["li", "p", "div"]):
                txt = elem.get_text(strip=True)
                if "game size:" in txt.lower() or "размер:" in txt.lower() or "size:" in txt.lower():
                    sm = re.search(r"(?:Game\s*Size|Size|Размер)\s*:\s*([0-9\.,]+\s*(?:GB|MB|KB|G|M|ГБ|МБ))", txt, re.IGNORECASE)
                    if sm:
                        approx_size = sm.group(1).strip().replace("ГБ", "GB").replace("МБ", "MB").replace(" ", "")
                        break

            if not approx_size:
                sm = re.search(r"(?:Game\s*Size|Size)\s*:\s*([0-9\.,]+\s*(?:GB|MB|KB|G|M))", html, re.IGNORECASE)
                if sm:
                    approx_size = sm.group(1).strip().replace(" ", "")

            # 4. Parse Description
            description = ""
            entry_content = soup.find(class_="entry-content") or soup.find("article")
            if entry_content:
                for p in entry_content.find_all("p"):
                    ptxt = p.get_text(strip=True)
                    if len(ptxt) > 50 and not ptxt.startswith("+") and not ptxt.startswith("Genre:") and not ptxt.startswith("How to"):
                        description = ptxt
                        break

            # 5. Parse Thumbnail
            thumbnail = ""
            og_img = soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                thumbnail = og_img["content"]
            elif entry_content:
                featured_img = entry_content.find("img")
                if featured_img and featured_img.get("src"):
                    thumbnail = featured_img["src"]

            # 6. Parse Download Links & Host Mirrors
            available_hosts: Dict[str, Dict[str, Any]] = {}
            hosts_parts: Dict[str, List[tuple]] = {}

            # Helper to normalize host names
            def normalize_host_name(href_url: str, label_text: str = "") -> str:
                h = href_url.lower()
                s = label_text.lower()
                if "bzzhr" in h or "buzzheavier" in h or "bzzhr" in s or "buzzheavier" in s:
                    return "BuzzHeavier"
                if "fileditch" in h or "fileditch" in s:
                    return "FileDitch"
                if "megadb" in h or "megadb" in s:
                    return "MegaDB"
                if "gofile" in h or "gofile" in s:
                    return "GoFile"
                if "pixeldrain" in h or "pixel" in s:
                    return "Pixeldrain"
                if "1fichier" in h or "1fichier" in s:
                    return "1Fichier"
                if "dropbox" in h or "dropbox" in s:
                    return "DropBox"
                if "qiwi" in h or "qiwi" in s:
                    return "Qiwi"
                if "drive.google" in h:
                    return "Google Drive"
                if "torrent" in s or "torrent" in h:
                    return "Torrent"
                try:
                    domain = urllib.parse.urlparse(href_url).netloc.split(".")[-2].capitalize()
                    return domain
                except Exception:
                    return label_text.strip() or "Direct"

            all_a_tags = soup.find_all("a", href=True)
            for a in all_a_tags:
                clz = " ".join(a.get("class", []))
                txt = a.get_text(strip=True)
                href = a["href"].strip()
                if href.startswith("//"):
                    href = "https:" + href

                parsed = urllib.parse.urlparse(href)
                netloc = parsed.netloc.lower()

                # Skip social media and navigation links (unless file archive)
                if any(nav in netloc for nav in ["discord.gg", "twitter.com", "t.me", "youtube.com", "steamdb.info", "reddit.com"]):
                    continue
                if "steamrip.com" in netloc and not any(href.lower().endswith(ext) for ext in [".rar", ".zip", ".7z", ".iso", ".exe"]):
                    continue

                is_btn = "shortc-button" in clz or "tie-shortc-button" in clz
                is_dwnld_text = any(w in txt.lower() for w in ["download", "part", "mirror", "here"])

                if (is_btn or is_dwnld_text) and href.startswith("http"):
                    host_name = normalize_host_name(href, txt)

                    # Detect part number
                    part_num = 1
                    pm = re.search(r"part\s*(\d+)", txt, re.IGNORECASE)
                    if pm:
                        part_num = int(pm.group(1))
                    elif "part" in href.lower():
                        hpm = re.search(r"part(\d+)", href, re.IGNORECASE)
                        if hpm:
                            part_num = int(hpm.group(1))

                    if host_name not in hosts_parts:
                        hosts_parts[host_name] = []
                    hosts_parts[host_name].append((part_num, href))

            # Sort and deduplicate parts for each host
            for h_name, parts_list in hosts_parts.items():
                parts_list.sort(key=lambda x: x[0])
                seen_urls = set()
                ordered_urls = []
                for p_num, url in parts_list:
                    if url not in seen_urls:
                        seen_urls.add(url)
                        ordered_urls.append(url)
                available_hosts[h_name] = {
                    "parts": ordered_urls,
                    "fix_url": ""
                }

            # Determine selected host data
            selected_host = preferred_host
            if selected_host not in available_hosts and available_hosts:
                if "BuzzHeavier" in available_hosts:
                    selected_host = "BuzzHeavier"
                elif "FileDitch" in available_hosts:
                    selected_host = "FileDitch"
                elif "GoFile" in available_hosts:
                    selected_host = "GoFile"
                else:
                    selected_host = next(iter(available_hosts))

            host_data = available_hosts.get(selected_host, {"parts": [], "fix_url": ""})

            return {
                "success": True,
                "title": title or "SteamRIP Game",
                "version": version or "1.0",
                "host": selected_host,
                "parts": host_data.get("parts", []),
                "fix_url": host_data.get("fix_url", ""),
                "approx_size": approx_size or "N/A",
                "description": description,
                "thumbnail": thumbnail,
                "origin_url": origin_url,
                "available_hosts": available_hosts
            }

        except Exception as e:
            print(f"[Scraper] SteamRIP scraping error: {e}")
            return {"success": False, "error": str(e)}

    def _scrape_hosters_portal(self, hosters_url: str) -> Dict[str, Dict[str, Any]]:
        """Scrapes download mirrors from the hosters.online-fix.me portal."""
        hosts_map: Dict[str, Dict[str, Any]] = {}
        try:
            resp = self.session.get(hosters_url, timeout=12)
            if resp.status_code != 200:
                print(f"[Scraper] Hosters portal status: {resp.status_code}")
                return {}

            soup = BeautifulSoup(resp.text, "html.parser")

            # Online-Fix Hosters portal typically uses <div class="option" data-links='[...]'>
            options = soup.find_all(class_=re.compile(r"option"))
            for opt in options:
                # Check for data-links attribute
                data_links_raw = opt.get("data-links")
                host_name = opt.get("data-name") or opt.get_text(strip=True) or "Direct"
                
                # Normalize common host names
                norm_name = "Direct"
                if "gofile" in host_name.lower() or (data_links_raw and "gofile.io" in data_links_raw.lower()):
                    norm_name = "GoFile"
                elif "viking" in host_name.lower() or (data_links_raw and "vikingfile" in data_links_raw.lower()):
                    norm_name = "VikingFile"
                elif "pixel" in host_name.lower() or (data_links_raw and "pixeldrain" in data_links_raw.lower()):
                    norm_name = "Pixeldrain"
                elif "1fichier" in host_name.lower() or (data_links_raw and "1fichier" in data_links_raw.lower()):
                    norm_name = "1Fichier"
                elif "drive" in host_name.lower() or (data_links_raw and "drive.google" in data_links_raw.lower()):
                    norm_name = "Google Drive"
                elif host_name:
                    norm_name = host_name

                links_list = []
                if data_links_raw:
                    try:
                        links_list = json.loads(data_links_raw)
                    except Exception as je:
                        print(f"[Scraper] Failed to parse data-links JSON for {norm_name}: {je}")

                # If no data-links, parse direct <a> download buttons in this section
                if not links_list:
                    file_info_blocks = opt.find_all(class_="file-info") or [opt]
                    for block in file_info_blocks:
                        p_name = block.find("p")
                        a_btn = block.find("a", href=True)
                        if a_btn and a_btn["href"].startswith("http"):
                            links_list.append({
                                "file_name": p_name.get_text(strip=True) if p_name else "",
                                "direct_link": a_btn["href"]
                            })

                if links_list:
                    parts = []
                    fix_url = ""
                    inferred_version = ""

                    for item in links_list:
                        link = item.get("direct_link") or item.get("link") or ""
                        fname = item.get("file_name") or ""
                        if not link:
                            continue

                        # Check if this item is a Fix/Repair archive
                        is_fix = bool(re.search(r"(?:_Fix_|_Repair_|Fix|Repair|Steam_V\d)", fname, re.IGNORECASE))
                        if is_fix:
                            if not fix_url:
                                fix_url = link
                        else:
                            parts.append(link)
                            # Attempt to extract version from filename, e.g. Game.v1.2.3-OFME.rar
                            vm = re.search(r"[._\-]v?(\d+(?:\.\d+)+(?:[a-zA-Z0-9_\-]*)?)", fname, re.IGNORECASE)
                            if vm and not inferred_version:
                                inferred_version = vm.group(1).rstrip("-._")

                    hosts_map[norm_name] = {
                        "parts": parts,
                        "fix_url": fix_url,
                        "raw_files": links_list,
                        "inferred_version": inferred_version
                    }

            # If no options with data-links were found, search all direct links in page
            if not hosts_map:
                all_links = soup.find_all("a", href=True)
                gofile_parts = []
                gofile_fix = ""
                for a in all_links:
                    h = a["href"]
                    txt = a.get_text()
                    if "gofile.io" in h:
                        if "fix" in txt.lower() or "repair" in txt.lower():
                            gofile_fix = h
                        else:
                            gofile_parts.append(h)

                if gofile_parts or gofile_fix:
                    hosts_map["GoFile"] = {
                        "parts": gofile_parts,
                        "fix_url": gofile_fix,
                        "raw_files": []
                    }

        except Exception as e:
            print(f"[Scraper] Hosters portal parsing error: {e}")

        return hosts_map

    @staticmethod
    def _clean_version(raw: str) -> str:
        if not raw:
            return ""
        # Strip leading labels (Russian or English)
        cleaned = re.sub(r"^(?:Версия\s*игры|Версия|Version|Build|v|ver)\s*[:\s-]*", "", raw, flags=re.IGNORECASE).strip()
        # Strip trailing notes, DLCs, Extras, pipes, etc.
        cleaned = re.split(r"\s*(?:\||\+|\bDLC\b|\bExtras\b|\bFull Version\b|\bPre-Installed\b)", cleaned, flags=re.IGNORECASE)[0].strip()
        # If it has (Build ...), strip the build in parenthesis
        if "(" in cleaned:
            cleaned = cleaned.split("(")[0].strip()
        # Strip Cyrillic notes (e.g. "по сети")
        cleaned = re.sub(r"[\u0400-\u04FF].*", "", cleaned).strip()
        cleaned = re.sub(r"\[?(?:Download|Free|Direct|Torrent|Online\-Fix|Fix|Repair|Steam|Hosters|Drive)[^\]]*\]?", "", cleaned, flags=re.IGNORECASE).strip()
        return cleaned.rstrip(" :;,-_[]()").strip()
