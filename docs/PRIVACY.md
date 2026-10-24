# Privacy Policy for Fanta OFME Downloader

**Last Updated:** October 2026  
**License:** Open Source (MIT)  
**Developer:** Zuhu / ZuhuInc  
**Repository:** [https://github.com/ZuhuInc/Simple-OFME-Downloader-LIB](https://github.com/ZuhuInc/Simple-OFME-Downloader-LIB)  
**Contact:** officialzuhu@gmail.com  

---

## 1. Overview & Commitment

**Fanta OFME Downloader** is a free, open-source desktop application. We respect your privacy and believe in total transparency. 

* **No Tracking:** We do not collect, track, or monitor your gameplay or download history.
* **No Third-Party Servers:** The application communicates directly from your PC to target game hostings and Google APIs. No intermediate servers or telemetry collectors exist.
* **No Selling of Data:** We never sell, rent, or monetize user data.

---

## 2. Google Drive Cloud Saves Integration

Fanta OFME Downloader includes an optional Google Drive integration allowing users to synchronize and back up their game save files across multiple PCs.

### Scopes Requested
When connecting Google Drive, the app requests the following minimal Google OAuth 2.0 scopes:
* `https://www.googleapis.com/auth/drive.file` — *Access only to files and folders created or opened by Fanta OFME Downloader.*
* `https://www.googleapis.com/auth/userinfo.email` — *Displaying your account email address inside the app UI for account switching.*

### Strict Limited Access (`drive.file`)
Because we use the **non-sensitive `drive.file` scope**:
* The app **CAN ONLY** access files and folders that the app itself created (specifically inside the `Fanta OFME Cloud Saves` folder).
* The app **CANNOT** read, view, modify, or delete any of your other personal Google Drive documents, pictures, spreadsheets, or folders.

### How Google Drive Data is Used
1. **Save Backups:** Compresses your chosen game's local save directory into a `.zip` archive and uploads it to your personal Google Drive in the `Fanta OFME Cloud Saves` folder.
2. **Save Restores:** Downloads your backup `.zip` from your Google Drive and extracts it to your local game save folder.
3. **Timestamp Comparison:** Checks the modification date of your cloud backup to alert you if a newer save exists on another computer.

---

## 3. Storage of Credentials & Tokens

* All OAuth tokens, API settings, and custom save directory paths are stored **locally on your computer** in your private app directory (e.g., `CloudSync.json`).
* Tokens are never transmitted to any third party or external server.

---

## 4. Revoking Permissions & Deleting Data

You maintain full control of your Google Drive account and data at all times:
* **Disconnect:** Click **Disconnect** in the app's *Cloud & Saves* tab at any time to purge local tokens.
* **Delete Saves:** Open your [Google Drive](https://drive.google.com) and delete the `Fanta OFME Cloud Saves` folder.
* **Revoke App Access:** Revoke access anytime in your [Google Account Security Permissions](https://myaccount.google.com/permissions).

---

## 5. Contact & Questions

If you have questions about this Privacy Policy or the Google Drive integration, please reach out:
* **GitHub Issues:** [https://github.com/ZuhuInc/Simple-OFME-Downloader-LIB/issues](https://github.com/ZuhuInc/Simple-OFME-Downloader-LIB/issues)
* **Email:** officialzuhu@gmail.com
