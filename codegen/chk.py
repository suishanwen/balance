import sys
import importlib
import os
from pathlib import Path

project_path = str(Path(os.getcwd()).parent)

sys.path.append(project_path)

importlib.reload(sys)

from codegen.generator import write

write("dec", '../key.ini')
accounts_init = []
try:
    for _, _, files in os.walk("../keys"):
        accounts_init = files
except FileNotFoundError:
    print("keys not found")

for account in accounts_init:
    write("dec", '../keys/' + account)
