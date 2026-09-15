@echo off
rem 앱 [기록] 에서 복사한 내용을 클립보드에 두고 실행하면 구차고지 엑셀에 적어 기본 프린터로 뽑는다
cd /d %~dp0
python tools\print_board.py
pause
