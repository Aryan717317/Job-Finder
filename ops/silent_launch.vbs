' silent_launch.vbs – Launches powershell.exe with ZERO visible window.
' Usage: wscript.exe silent_launch.vbs <ps1-script> [args...]
'
' The Windows Task Scheduler invokes:
'   wscript.exe "...\silent_launch.vbs" "...\run_cycle.ps1" -Mode scheduled-task ...
' wscript runs without a console, so no window ever appears.

If WScript.Arguments.Count = 0 Then
    WScript.Quit 1
End If

Dim psScript, args, i
psScript = WScript.Arguments(0)

args = ""
For i = 1 To WScript.Arguments.Count - 1
    arg = WScript.Arguments(i)
    ' Wrap arguments that contain spaces in quotes
    If InStr(arg, " ") > 0 Then
        args = args & " """ & arg & """"
    Else
        args = args & " " & arg
    End If
Next

Dim cmd
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & psScript & """" & args

Dim shell
Set shell = CreateObject("WScript.Shell")
' 0 = hidden window, False = don't wait for completion
shell.Run cmd, 0, False
