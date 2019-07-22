import os
import sys
import importlib

from pathlib import Path

project_path = str(Path(os.getcwd()).parent)
sys.path.append(project_path)
importlib.reload(sys)
from codegen.generator import write

write("enc", '../tokens/Token.py')
