import os
from module.CfEnv import KEY_PATH, SUB_KEY_PATH

from codegen.generator import decrypt_f

decrypt_f(KEY_PATH)
accounts_init = []
try:
    for _, _, files in os.walk(SUB_KEY_PATH):
        accounts_init = files
except FileNotFoundError:
    print("keys not found")

for account in accounts_init:
    decrypt_f(f"{SUB_KEY_PATH}/{account}")
