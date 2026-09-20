@echo off
rem 录屏/演示一键启动器（双击运行）：重定向 USERPROFILE 避免沙箱权限问题，无浏览器自启
set USERPROFILE=%~dp0..\.tmp_home
set STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
if not exist "%USERPROFILE%" mkdir "%USERPROFILE%"
echo 正在启动创想∞演示环境，启动后请在浏览器打开 http://localhost:8533
echo 录制建议：先点"加载已有报告"展示真实 Run；需要并行画面时再新开一次审查。
python -m streamlit run "%~dp0..\frontend\app.py" --server.headless true --server.port 8533 --browser.gatherUsageStats false
pause
