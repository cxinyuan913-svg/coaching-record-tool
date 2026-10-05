# 容器化與部署規劃

## 目的

兩個動機，順序很清楚：

1. **實際的可靠性問題**：這次開發過程中反覆碰到「伺服器到底有沒有開著」——Windows 工作排程器要等使用者登入才會觸發，且無法涵蓋「開機但還沒登入」的情況；用 Claude Code CLI 對話手動開的背景程序，又會因為對話環境本身資源不足被中途關掉（開發期間至少發生了三次）。這兩種都不是真正「跟作業系統開機绑定、有自己重啟機制」的做法。
2. **累積 Docker／Kubernetes 的實務經驗**（求職作品集用途）。這個順序很重要：先解決真問題，作品集的加分是附帶結果，不是為了加分而刻意繞路去用不必要的工具。

## 階段一：Docker（近期，對現在的問題有實際幫助）

- 一個 `Dockerfile`：`python:3.11-slim` 為基底，複製程式碼跟 `requirements.txt`、安裝依賴、`CMD` 跑 `uvicorn app.main:app --host 0.0.0.0 --port 8000`。
- 一個 `docker-compose.yml`，掛 volume 保留容器重建之間需要留住的狀態：`coaching.db`、`booking_api_token.txt`、`public_booking_api_token.txt`、`discord_webhook_url.txt`、`scheduler_state.json`——這幾個檔案都不能隨容器重建就消失。
- 設定 `restart: unless-stopped`。這一項直接解決現有的痛點：Docker Desktop 原生就會在容器意外結束時重啟它，不需要「使用者先登入 Windows」這個前提，也不受任何對話環境的資源狀況影響。
- 這一階段做完之後，原本用來解決同一個問題的 Windows 工作排程器設定（`CoachingRecordToolServer`）就可以退役。

## 階段二：Kubernetes（求職作品集為主，誠實承認對這個工具不是必要）

老實說：這個工具是單人使用、資料庫是單一 SQLite 檔案，K8s 真正的價值——多副本、自動擴縮、滾動更新——在這個情境下用不太到。`replicas` 只能設 1，因為 SQLite 不支援多個行程同時寫入同一個檔案；設成 1 的 K8s，本質上只是用比較重的工具去做 Docker `restart: unless-stopped` 就能做到的事。這個限制要老實說明，不能把它描述成「這個專案需要 K8s 才能運作」。

即使如此，寫一份 K8s manifest 仍然有練習價值，因為它會逼你想清楚幾個常被問到的議題：

- 一個 `Deployment`（`replicas: 1`），`livenessProbe`／`readinessProbe` 打現有的 `GET /api/health`。
- 狀態保存：`PersistentVolumeClaim` 掛 SQLite 檔案跟前面提到的幾個本機檔案的位置。
- 密鑰管理：Discord webhook URL、動智館 API token 改用 `Secret` 掛進容器的環境變數，取代現在直接放在本機明碼檔案的做法（見 `app/notifications.py`／`app/auth.py`）。

**如果之後真的想要多副本有意義**，前提是先把 SQLite 換成 Postgres（要先規劃好資料遷移路徑），K8s 才能真正發揮「多個 pod 同時處理請求」的價值。在那之前，`replicas` 永遠只會是 1。

## 現況

階段一的 `Dockerfile`／`docker-compose.yml`／`.dockerignore` 已經寫好，但**這台開發機沒有安裝 Docker，還沒有實際 build/run 測試過**，也還沒有正式切換過去——目前實際負責「讓伺服器保持運作」的仍然是 Windows 工作排程器設定（`CoachingRecordToolServer`），不要在還沒驗證過 Docker 版本真的能跑之前就把它移除。K8s manifest（階段二）尚未動工。

**切換前要做的驗證**（等裝好 Docker Desktop 之後）：
1. `docker compose up --build`，確認能正常啟動、`http://127.0.0.1:8000` 打得開。
2. 確認掛載的四個檔案（`coaching.db` 等）路徑對、容器裡讀到的是真實資料，不是空的。
3. 手動測試「重開容器」場景：`docker compose restart`，確認 `coaching.db` 資料還在（不是被重建成空的）。
4. 確認得到都沒問題、穩定跑一段時間之後，才移除 Windows 工作排程器設定。
