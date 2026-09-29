"""設定（或更換）網站登入密碼：python -m app.set_password

只把 scrypt 雜湊寫進 admin_password_hash.txt（不進版控），密碼本身不會存
在任何地方。換密碼後，所有已登入的裝置都要重新登入。
"""
import getpass
import sys

from app.web_auth import PASSWORD_HASH_FILE, hash_password, load_or_create_session_secret

MIN_LENGTH = 8


def main() -> int:
    password = getpass.getpass("新密碼（至少 8 個字元，輸入時不會顯示）：")
    if len(password) < MIN_LENGTH:
        print(f"密碼太短，至少要 {MIN_LENGTH} 個字元。")
        return 1
    if getpass.getpass("再輸入一次：") != password:
        print("兩次輸入不一樣，沒有儲存。")
        return 1
    PASSWORD_HASH_FILE.write_text(hash_password(password), encoding="utf-8")
    # 順便把簽章金鑰也建好，部署時兩個檔案一起帶上主機
    load_or_create_session_secret()
    print(f"已儲存到 {PASSWORD_HASH_FILE.name}，網站伺服器不用重開就會生效。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
