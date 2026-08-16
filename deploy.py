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
    "Dockerfile",
    "docker-compose.yml",
    "README.md",
]

def deploy_docker(commit_msg="Update bot"):
    print("==========================================")
    print("🐳 Deploying Telegram Bot as Docker Container to VPS")
    print("==========================================")

    # 1. Git Add, Commit & Push to GitHub
    print("\n1. Pushing changes to GitHub...")
    try:
        subprocess.run(["git", "add", "."], cwd=LOCAL_DIR, check=True)
        res = subprocess.run(["git", "status", "--porcelain"], cwd=LOCAL_DIR, capture_output=True, text=True)
        if res.stdout.strip():
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=LOCAL_DIR, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=LOCAL_DIR, check=True)
        print("✅ Pushed to GitHub successfully!")
    except Exception as e:
        print(f"⚠️ Git notice: {e}")

    # 2. SSH to VPS
    print(f"\n2. Connecting to VPS ({HOST})...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)
        print("✅ Connected to VPS via SSH!")
    except Exception as e:
        print(f"❌ Failed to connect to VPS: {e}")
        return

    def exec_cmd(cmd):
        print(f"\n[RUNNING]: {cmd}")
        stdin, stdout, stderr = ssh.exec_command(cmd)
        out = stdout.read().decode('utf-8', errors='ignore')
        err = stderr.read().decode('utf-8', errors='ignore')
        if out:
            print(f"[OUTPUT]:\n{out.strip()}")
        if err and "warning" not in err.lower() and "notice" not in err.lower():
            print(f"[STDERR]:\n{err.strip()}")
        return out, err

    # 3. Stop systemd service if running to avoid conflict
    print("\n3. Stopping old systemd service (switching to Docker)...")
    exec_cmd("systemctl stop media-downloader-bot || true")
    exec_cmd("systemctl disable media-downloader-bot || true")

    # 4. Upload files via SFTP
    print("\n4. Syncing all files to VPS...")
    exec_cmd(f"mkdir -p {REMOTE_APP_DIR} {REMOTE_APP_DIR}/downloads")
    sftp = ssh.open_sftp()
    for filename in FILES_TO_SYNC:
        local_path = os.path.join(LOCAL_DIR, filename)
        remote_path = f"{REMOTE_APP_DIR}/{filename}"
        if os.path.exists(local_path):
            sftp.put(local_path, remote_path)
            print(f"   -> Uploaded {filename}")
    sftp.close()

    # 5. Build and run Docker container
    print("\n5. Building and starting Docker container...")
    exec_cmd(f"cd {REMOTE_APP_DIR} && docker compose up -d --build")

    time.sleep(3)

    # 6. Verify Docker container status
    print("\n6. Verifying Docker container state...")
    exec_cmd("docker ps --filter name=telegram-media-bot")
    exec_cmd("docker logs --tail 20 telegram-media-bot")

    ssh.close()
    print("\n==========================================")
    print("🎉 Docker Container is UP & RUNNING on your VPS Dashboard!")
    print("==========================================")

if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else "Deploy docker container"
    deploy_docker(msg)
