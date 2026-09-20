' 隱藏視窗啟動 run_server.bat：.bat 本身一定會跳出主控台視窗，
' 這支 vbs 用 WScript.Shell.Run 的第二個參數 0（隱藏視窗）去執行它，
' Windows 工作排程器（CoachingRecordToolServer）的動作要改成執行這支
' vbs，而不是直接執行 run_server.bat。log 改看 server.log。
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
Set shell = CreateObject("WScript.Shell")
shell.Run """" & scriptDir & "\run_server.bat""", 0, False
