# startup_install.py
# Adds Buddy to Windows startup via registry.
# Run ONCE: python startup_install.py

import winreg
import sys
import os

APP_NAME = "Buddy"
PYTHON   = sys.executable
SCRIPT   = os.path.abspath("main.py")
CMD      = f'"{PYTHON}" "{SCRIPT}"'

key = winreg.OpenKey(
    winreg.HKEY_CURRENT_USER,
    r"Software\Microsoft\Windows\CurrentVersion\Run",
    0, winreg.KEY_SET_VALUE
)
winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, CMD)
winreg.CloseKey(key)
print(f"Buddy registered for startup:\n  {CMD}")
