# Simple OFME Downloader & LIB

![Python Version](https://img.shields.io/badge/python-3.6+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Maintained](https://img.shields.io/badge/maintained%3F-yes-brightgreen.svg)

A command-line utility designed to automate the process of downloading and extracting game files from a centralized list. This script fetches the latest download links, handles user selection, manages downloads with progress bars, and automatically extracts password-protected archives using WinRAR.

---

## Getting Started

> [!NOTE]
> ### Easiest Method: Download the Executable (.exe)
> This is the recommended way for most users and **does not require a Python installation.**
>
> 1.  Go to the [**Releases Page**](https://github.com/ZuhuInc/Simple-OFME-Downloader/releases).
> 2.  Download the latest `.exe` file from the **Assets** section.
> 3.  **Important:** You still need to have **WinRAR** installed for the extractor to work.
> 4.  Run the downloaded file and follow the on-screen instructions!
>
> [**➡️ Go to the Releases Page to Download**](https://github.com/ZuhuInc/Simple-OFME-Downloader/releases)

---

### For Developers: Running from Source

<details>
<summary>Click here for instructions on running from the Python source code</summary>

#### Prerequisites
*   **Python 3.6+**
*   **WinRAR** installed and accessible via your system's `PATH` or configured in the script.

#### Installation Steps
1.  **Clone the repository:**
    ```bash
    git clone https://github.com/ZuhuInc/Simple-OFME-Downloader
    cd Simple-OFME-Downloader
    ```

2.  **Install dependencies:**
    ```bash
    pip install requests tqdm
    ```

3.  **Configure the Script (if needed):**
    Open the main Python script and ensure the `WINRAR_PATH` variable points to your `WinRAR.exe` file.
    ```python
    # Make sure this path is correct for your system
    WINRAR_PATH = r"C:\Program Files\WinRAR\WinRAR.exe"
    ```
4. **Run the Script:**
    ```bash
    python main.py 
    ```
    *(Replace `main.py` with your script's actual filename)*

</details>

---

### How to Use: A Visual Guide

The script will guide you through a few simple steps.

| Step | Action | Preview |
| :--: | :--- | :--- |
| **1** | **Select Game & Source**<br/><br/>First, choose the game you want to download. Then, select your preferred download host from the next menu. | ![Game & Source](https://i.imgur.com/h0x3N8t.png) |
| **2** | **Set Path & Download**<br/><br/>Enter the base directory where you want the game extracted. The download will start automatically. | ![Path & Download](https://i.imgur.com/BPIKkMj.png) |
| **3** | **Apply Fix (Optional)**<br/><br/>After extraction, the script will ask if you want to download and apply an available fix or update. | ![Apply/Download Fix](https://i.imgur.com/jXT3YSw.png) |
| **4**| **All Done!**<br/><br/>A final summary screen will show the status of all operations. | ![IDone](https://i.imgur.com/NLyvxAO.png) |

---

### Libraries Used

*   **External:** [requests](https://pypi.org/project/requests/), [tqdm](https://pypi.org/project/tqdm/)
*   **Standard:** `os`, `sys`, `subprocess`, `shutil`, `re`, `hashlib`

---

### ✨ Maintainers

This project is kept up-to-date by the following awesome people.

*   **[ZuhuInc](https://github.com/ZuhuInc)**
*   **[BramTurf](https://github.com/BramTurf)**
*   **[lceqx](https://github.com/lceqx)**

---

### License

This project is licensed under the MIT License - see the `LICENSE` file for details.
