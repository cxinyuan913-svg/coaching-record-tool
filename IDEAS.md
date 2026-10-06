# 想法收集區

想到新功能先記一行在這裡，附一兩句說明即可，不用當下就做。
每週回顧一次，決定要不要正式排進 spec/ 的開發階段。

## 待修正（bug，不是想法）

（目前沒有）

## 待評估

- 訂場結果回寫 API：讀課表已完成（`GET /api/integrations/venue-schedule`），
  但自動訂場系統無法回寫訂場結果，目前仍靠前端手動標記
- 場館優化建議：`spec/venue-optimization.md` 只有規格、無程式碼；要做的話
  先決定值不值得，再考慮是否擴充成跨天檢查
- 場館交通時間改接 Google Maps API：目前用固定對照表 `venue_travel_times`
  （15 筆），場館變多或不固定時再評估
- SQLite → Postgres：SPEC 階段六原規劃但未執行。單人使用無虞，公開網站／
  LINE 整合後若有併發寫入再評估
- `app/booking_parser/` 技術債：LLM 解析整包已停用，程式、`student_aliases`
  表（0 筆）、`anthropic` 依賴都還在，要不要清掉

> 公開網站與 LINE 官方帳號整合的完整缺口清單在 `STATUS.md` 第 10 節，
> 已知風險在第 9 節，不重複列在這裡。

## 已排入開發
- (項目排入後，從這裡移到對應的 spec/*.md 並在此刪除)
