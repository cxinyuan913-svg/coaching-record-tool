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
`public_booking_api_token.txt`、`discord_webhook_url.txt`、
`scheduler_state.json`、`admin_password_hash.txt`、`session_secret.txt`
這七個檔案要一起帶上去**——不是重新建立空的，是把你現在本機真實在用
的那幾份複製過去，不然資料會整個歸零、也登入不了。

後兩個是網站登入用的（見 `app/web_auth.py`）：網站放上網路一定要有登入，
不然知道網址的人都能看到、修改學生資料。上傳前先確認本機已經設過密碼
（專案資料夾裡有這兩個檔案）；沒有的話先在本機執行
`python -m app.set_password` 設定。**這七個檔案一定要先存在再啟動
容器**：Docker 掛載不存在的檔案時會自動建成「資料夾」，程式就讀不到了。

```bash
# 在 VPS 上
git clone <你的 repo 位址> coaching-record-tool
cd coaching-record-tool

# 在本機電腦（另開一個終端機），把七個真實資料檔案傳上去
scp coaching.db booking_api_token.txt public_booking_api_token.txt \
    discord_webhook_url.txt scheduler_state.json \
    admin_password_hash.txt session_secret.txt \
    coach@<VPS的IP>:~/coaching-record-tool/
```

要換密碼時，在 VPS 上執行（不用重開容器，下一次登入就生效，所有裝置
都要重新登入）：

```bash
docker compose -f docker-compose.cloud.yml exec coaching-record-tool python -m app.set_password
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

## 步驟八：別忘了動智館自動訂場系統的連線位址也要改

那套另外獨立在跑的動智館自動訂場系統，是打這個工具的
`GET /api/integrations/venue-schedule` 來查課表（見 `ARCHITECTURE.md`）。
它原本設定的網址是本機（例如 `http://127.0.0.1:8000/...` 或區網 IP），
搬去雲端之後要記得把那套系統的設定改成 `https://你的網域/api/...`，
**Bearer Token 不用換**——`booking_api_token.txt` 已經跟著步驟六一起
複製到 VPS 上了，內容是同一組。這步很容易漏掉：漏改的話，那套系統
會繼續打你本機那台（如果本機 Windows 排程還沒關的話還能動，但看到
的是本機那份舊資料），或本機一旦關掉之後直接連不上、訂場排程整個
停擺卻不會有明顯錯誤訊息。

## 步驟九：確認沒問題後，把舊的 Windows 排程退役

在雲端版本穩定跑過幾天、手機也實際連過確認沒問題、動智館那邊也確認
改連到新網址且正常運作之後，才把本機 Windows 工作排程器
（`CoachingRecordToolServer`／`run_server_hidden.vbs`）停用——不要一次
到位，留一個緩衝期比較保險。

---

## 常見問題：容器啟動後一直重開、log 顯示寫入 coaching.db 被拒絕

`Dockerfile` 裡讓容器用一個非 root 的 `appuser` 執行，這在 Windows 上
用 Docker Desktop 不會有事，但在**真正的 Linux 主機**上，bind mount
進去的 `coaching.db` 等檔案，權限是看「主機上這個檔案的擁有者」跟
「容器裡 `appuser` 的 UID」對不對得起來，兩者對不起來的話容器裡的
程式會沒有寫入權限。`docker compose logs coaching-record-tool` 如果
看到 `PermissionError` 或 `unable to open database file`，八成就是
這個問題。兩種修法擇一：

```bash
# 方法一：把主機上這幾個檔案的擁有者，改成跟容器裡 appuser 的 UID 一致
# （容器預設是 1000，可以用這行確認）
docker compose -f docker-compose.cloud.yml exec coaching-record-tool id appuser
sudo chown 1000:1000 coaching.db booking_api_token.txt public_booking_api_token.txt \
    discord_webhook_url.txt scheduler_state.json admin_password_hash.txt session_secret.txt

# 方法二：改用 root 執行（單人小工具、機器只有你在用，風險可接受的話
# 這樣最省事）——把 Dockerfile 裡 `RUN useradd --create-home appuser` 跟
# `USER appuser` 這兩行註解掉，改完要重新 build：
docker compose -f docker-compose.cloud.yml up -d --build
```

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

## 回退到本機（雲端版本出問題、想先切回本機用的時候）

這次雲端化完全沒有動到本機現有的東西——本機的 `coaching.db`、
`run_server_hidden.vbs`、Windows 工作排程器都還在，隨時切得回來。
**唯一要注意的是資料會分岔**：雲端版本正式在用之後，你在雲端上新增/
修改的課程，本機那份 `coaching.db` 完全不知道、也不會自動同步。所以
回退前一定要先把雲端最新的資料抓回來，不能直接啟用本機那份舊資料，
不然雲端上新增的東西會憑空消失。

1. **先把雲端最新的 `coaching.db` 抓回本機、覆蓋掉本機那份舊的**：
   ```bash
   # 在本機電腦執行
   scp coach@<VPS的IP>:~/coaching-record-tool/coaching.db ./coaching.db
   ```
   如果不確定雲端服務還正不正常、`scp` 抓不到最新檔案，改抓
   `backups/` 目錄裡最新一份的備份也可以（見上面「資料庫備份」那節）。
2. 確認抓回來的資料是最新、沒有缺東西之後，再重新啟用 Windows 工作
   排程器（`CoachingRecordToolServer`）跑本機版本。
3. 之後如果要再切回雲端，記得反過來：把本機這段期間的異動再 `scp`
   回 VPS，一樣要先確認哪一份才是最新的，不要兩邊同時有人在用、
   互相蓋掉對方的資料。

---

## 之後要停用時（見 CLAUDE.md 的操作風險提醒，刪除前務必先備份）

1. 先跑一次 `scripts/backup_db.sh`（或直接 `scp` 把 `coaching.db` 抓
   回本機），確認本機電腦上有最新的一份資料。
2. 到 VPS 主機商後台把這台機器 Destroy／刪除，帳單就停了。
3. 到 Cloudflare 把網域的自動續約關掉（如果不打算繼續用這個網域）。
