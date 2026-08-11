PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$PROJECT_DIR"
echo '----- pull code -----'
REQ_HASH_BEFORE=$(md5sum requirements.txt 2>/dev/null | awk '{print $1}')
git pull
REQ_HASH_AFTER=$(md5sum requirements.txt 2>/dev/null | awk '{print $1}')
if [ "$REQ_HASH_BEFORE" != "$REQ_HASH_AFTER" ]; then
    echo '----- requirements changed, installing -----'
    pip3 install -r requirements.txt --break-system-packages
fi
cd codegen
python3 dec.py
echo '----- kill okclient -----'
ps -ef | grep OKClient.py | grep -v grep | awk '{print $2}' | xargs kill -9
echo '----- start okclient -----'
cd "$PROJECT_DIR/ok"
cat /dev/null > nohup.out
nohup python3 OKClient.py > "$PROJECT_DIR/ok/nohup.out" 2>&1 &
