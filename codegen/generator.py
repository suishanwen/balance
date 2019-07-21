from ecies import encrypt, decrypt

prv_key = '574922a3972946b7d76c3d72110d639898586564e44a6a88fb07e8d60a2526c8'
pub_key = '03b2559f961bad62be7bcd89c51d3387776ab63759b25dbc18d5355b59857a8d66'


def enc(path):
    with open(path, 'r') as f:
        return encrypt(pub_key, bytes(f.read(), encoding="utf-8")).hex()


def dec(path):
    with open(path, 'r') as f:
        data = f.read()
        try:
            return str(decrypt(prv_key, bytes.fromhex(data)), encoding="utf-8")
        except Exception as e:
            print(str(e))
            return data


def write(_type, path):
    try:
        code = dec(path) if _type == "dec" else enc(path)
        with open(path, 'w') as f:
            f.write(code)
    except Exception as e:
        print(str(e))
