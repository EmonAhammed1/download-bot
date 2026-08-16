import os
import sys
import time
import subprocess
import paramiko

# Ensure UTF-8 output
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

HOST = "72.244.153.23"
PORT = 22
USER = "root"
PASS = "bVgqsYLwOPUNfNsHpO0W"
LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))
REMOTE_APP_DIR = "/opt/media-downloader-bot"

FILES_TO_SYNC = [
    "bot.py",
    "downloader.py",
    "config.py",
    "requirements.txt",
]

def run_sync(commit_msg="Update bot"):
    print("==========================================")
    print("🚀 Auto-Sync & Deploy to GitHub + VPS")
    print("==========================================")

    # 1. Git Add, Commit & Push to GitHub
    print("\n1. Pushing changes to GitHub...")
    try:
        subprocess.run(["git", "add", "."], cwd=LOCAL_DIR, check=True)
        # Commit if there are changes
        res = subprocess.run(["git", "status", "--porcelain"], cwd=LOCAL_DIR, capture_output=True, text=True)
        if res.stdout.strip():
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=LOCAL_DIR, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=LOCAL_DIR, check=True)
        print("✅ Pushed to GitHub successfully!")
    except Exception as e:
        print(f"⚠️ Git push notice: {e}")

    # 2. Deploy to VPS via SSH & SFTP
    print(f"\n2. Connecting to VPS ({HOST})...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)
        print("✅ Connected to VPS via SSH!")
    except Exception as e:
        print(f"❌ Failed to connect to VPS: {e}")
        return

    # Upload updated files
    print("\n3. Syncing updated files to VPS...")
    sftp = ssh.open_sftp()
    for filename in FILES_TO_SYNC:
        local_path = os.path.join(LOCAL_DIR, filename)
        remote_path = f"{REMOTE_APP_DIR}/{filename}"
        if os.path.exists(local_path):
            sftp.put(local_path, remote_path)
            print(f"   -> Uploaded {filename}")
    sftp.close()

    # Restart service on VPS
    print("\n4. Restarting bot service on VPS...")
    stdin, stdout, stderr = ssh.exec_command(
        f"cd {REMOTE_APP_DIR} && "
        f"./venv/bin/pip install --no-cache-dir -r requirements.txt beautifulsoup4 > /dev/null 2>&1 && "
        f"systemctl restart media-downloader-bot && "
        f"sleep 2 && "
        f"systemctl status media-downloader-bot --no-pager"
    )
    output = stdout.read().decode('utf-8', errors='ignore')
    print("\n[VPS Status]:")
    print(output.strip())

    ssh.close()
    print("\n🎉 Deployment complete! Your bot is live on VPS with the latest code.")

if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else "Auto update"
    run_sync(msg)
