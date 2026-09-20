@echo off
cd /d "C:\Users\Raymond\Documents\coaching-record-tool"
"C:\Users\Raymond\AppData\Local\Programs\Python\Python311\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >> server.log 2>&1
