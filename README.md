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
    pip install requests PyQt6
    ```

3.  **Configure the Script (if needed):**
    Open the main Python script and ensure the `WINRAR_PATH` variable points to your `WinRAR.exe` file.
    ```python
    # Make sure this path is correct for your system
    WINRAR_PATH = r"C:\Program Files\WinRAR\WinRAR.exe"
    ```
4. **Run the Script:**
    ```bash
    Python PEAK Downloader by zuhu.py 
    ```
    *(Replace `PEAK Downloader by zuhu.py` with the script's name u saved it as)*

</details>

---

### How to Use: A Visual Guide

The script will guide you through a few simple steps.

| Step | Action | Preview |
| :--: | :--- | :--- |
| **1** | **Select Game & Source**<br/><br/>First, choose the game you want to download. Then, select your preferred download host from the next menu. | <img width="1157" height="742" alt="image" src="https://github.com/user-attachments/assets/7b6c5ecd-3e0e-42ae-8d05-e35befbbfcac" /> |
| **2** | **Set Path & Download**<br/><br/>Enter the base directory where you want the game extracted. The download will start automatically. | <img width="1157" height="742" alt="image" src="https://github.com/user-attachments/assets/2e4f7ae4-15cd-478f-8613-5c846eae5193" /> |
| **3** | **Apply Fix (Optional)**<br/><br/>After extraction, the script will ask if you want to download and apply an available fix or update. | <img width="1157" height="742" alt="image" src="https://github.com/user-attachments/assets/9d8f08bc-0433-4e74-a7a6-4c0b2e6ba14c" /> |


---

### Libraries Used

*   **External:** [requests](https://pypi.org/project/requests/), [PyQt6](https://pypi.org/project/PyQt6/)
*   **Standard:** `os`, `sys`, `subprocess`, `json`, `re`, `hashlib`, `time`

---

### ✨ Maintainers

This project is kept up-to-date by the following awesome people.

*   **[ZuhuInc](https://github.com/ZuhuInc)**
*   **[TurfBoy27](https://github.com/Turfboy27)**
*   **[lceqx](https://github.com/lceqx)**

---

### License

This project is licensed under the MIT License - see the `LICENSE` file for details.
