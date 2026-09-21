# 雲端部署規劃（VPS + 網域 + HTTPS）

## 為什麼要做這個、跟 spec/deployment.md 的差異

`spec/deployment.md` 那份是「主機還放在自己 Windows 電腦上，只是用
Docker 讓服務更穩」，解決的是「伺服器有沒有開著」的問題。這份是更進
一步：**把主機搬到雲端 VPS 上、掛自己的網域、開 HTTPS**，讓手機在外
面也能連得到，不用依賴家裡的電腦跟網路。

走最便宜的路線：國外 VPS（Vultr 或 DigitalOcean，新加坡或東京機房）
+ Cloudflare Registrar 買網域，一年總成本大概 NT$2,200~2,600（VPS
約 NT$1,900~2,300 + 網域約 NT$300）。

---

## 步驟一：買網域（Cloudflare Registrar）— 你自己操作

1. 到 Cloudflare 註冊帳號、進「Domain Registration」買一個 `.com`
   網域（成本價，一年約 US$10）。
2. 買完後網域會自動掛在你的 Cloudflare 帳號下，先不用設定 DNS，等
   VPS 開好、拿到 IP 之後再回來設定。

## 步驟二：開 VPS（Vultr 或 DigitalOcean）— 你自己操作

1. 註冊帳號、新增付款方式。
2. 開一台最低規格主機：
   - 系統選 **Ubuntu 24.04 LTS**（Docker 官方支援最完整、教學最多）
   - 機房選 **Singapore** 或 **Tokyo**（離台灣近，延遲低）
   - 規格選最低階那檔（1 vCPU / 1GB RAM，約 US$5~6/月）就夠這個單人
     工具用
3. 開好之後記下這台主機的 **公開 IP**，之後步驟都會用到。
4. 主機商通常會給你一組 root 密碼或直接讓你上傳 SSH 公鑰——**強烈建議
   用 SSH 金鑰登入，不要用密碼**，密碼登入的主機在網路上幾分鐘內就會
   開始被掃描機器人猜密碼。如果本機還沒有 SSH 金鑰：
   ```
   ssh-keygen -t ed25519 -C "coaching-record-tool"
   ```
   開機時把 `~/.ssh/id_ed25519.pub` 的內容貼到主機商的「SSH Keys」欄位。

## 步驟三：DNS 指過去 — 你自己操作

回 Cloudflare，進剛買的網域的 DNS 設定，新增一筆：
- 類型：`A`
- 名稱：`@`（代表根網域）或你想要的子網域，例如 `coach`
- 內容：VPS 的公開 IP
- **Proxy status 先關掉（灰色雲朵，DNS only）**——因為等一下 Caddy
  要直接跟 Let's Encrypt 做驗證，中間多一層 Cloudflare 代理反而會卡
  住第一次拿憑證的過程。等網站跑起來、確認 HTTPS 正常之後，要不要
  再打開橘色雲朵（多一層 Cloudflare 的 CDN／防護）都可以，不影響現有
  設定。

DNS 設定通常幾分鐘內會生效，可以用 `nslookup 你的網域` 確認有指到
VPS 的 IP。

## 步驟四：VPS 基本安全設定 — 你自己操作（SSH 進去下指令）

```bash
# 建一個平常用的非 root 使用者（不要一直用 root 操作）
adduser coach
usermod -aG sudo coach
# 把剛剛的 SSH 公鑰也複製給這個新使用者，之後都用這個帳號登入

# 防火牆只開必要的 port：SSH、HTTP、HTTPS
sudo ufw allow OpenSSH
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

## 步驟五：裝 Docker — 你自己操作（SSH 進去下指令）

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# 執行完這行要登出再登入一次，群組設定才會生效
```

## 步驟六：把專案搬上去

如果 GitHub repo 是 private，用 SSH 金鑰或 deploy token clone；如果
還沒推到 GitHub，也可以直接用 `scp` 把整個資料夾（不含 `venv/`）傳
上去。**特別注意：`coaching.db`、`booking_api_token.txt`、
`discord_webhook_url.txt`、`scheduler_state.json` 這四個檔案要一起
帶上去**——不是重新建立空的，是把你現在本機真實在用的那幾份複製過去，
不然資料會整個歸零。

```bash
# 在 VPS 上
git clone <你的 repo 位址> coaching-record-tool
cd coaching-record-tool

# 在本機電腦（另開一個終端機），把四個真實資料檔案傳上去
scp coaching.db booking_api_token.txt discord_webhook_url.txt scheduler_state.json \
    coach@<VPS的IP>:~/coaching-record-tool/
```

## 步驟七：設定網域、啟動服務

```bash
# 在 VPS 上，coaching-record-tool 目錄裡
cp .env.example .env
nano .env   # 把 DOMAIN 改成你買的那個網域

docker compose -f docker-compose.cloud.yml up -d --build
```

第一次啟動 Caddy 會需要幾十秒到一兩分鐘跟 Let's Encrypt 要憑證，之後
拿瀏覽器打 `https://你的網域` 應該就能看到行事曆頁面、網址列有鎖頭。

## 步驟八：確認沒問題後，把舊的 Windows 排程退役

在雲端版本穩定跑過幾天、手機也實際連過確認沒問題之後，才把本機
Windows 工作排程器（`CoachingRecordToolServer`／`run_server_hidden.vbs`）
停用——不要一次到位，留一個緩衝期比較保險。

---

## 資料庫備份

`scripts/backup_db.sh` 每天把 `coaching.db` 複製一份到 `backups/`
目錄，保留最近 14 天，用 cron 排程執行：

```bash
# 在 VPS 上，設定每天凌晨 3 點自動備份
crontab -e
# 貼上這一行（記得把路徑換成你實際 clone 的位置；從 git 上抓下來的
# .sh 檔預設沒有執行權限，用 sh 開頭執行就不用另外 chmod +x）
0 3 * * * sh /home/coach/coaching-record-tool/scripts/backup_db.sh
```

**這只是「同一台主機上」的備份，防不了這台 VPS 本身整台掛掉或被誤刪
的情況。** 建議自己額外設一個提醒，每隔一陣子（例如每月）手動把
`backups/` 目錄整個下載回本機電腦或雲端硬碟：

```bash
# 在本機電腦執行，把 VPS 上的備份整個拉回來
scp -r coach@<VPS的IP>:~/coaching-record-tool/backups ./coaching-record-tool-backups
```

---

## 之後要停用時（見 CLAUDE.md 的操作風險提醒，刪除前務必先備份）

1. 先跑一次 `scripts/backup_db.sh`（或直接 `scp` 把 `coaching.db` 抓
   回本機），確認本機電腦上有最新的一份資料。
2. 到 VPS 主機商後台把這台機器 Destroy／刪除，帳單就停了。
3. 到 Cloudflare 把網域的自動續約關掉（如果不打算繼續用這個網域）。
