# PC 쪽 검사

폰이 아니라 **PC 가 하는 일**(엑셀에 받아 적기, 인쇄, 두 PC 사이의 넘김)을 실제
엑셀과 Z: 공유 폴더로 확인하는 검사들이다. 브라우저 검사(`tools/run_tests.ps1`)와 달리
이 PC 와 상황실 공유 폴더가 있어야 돈다.

    py tools\pc\check_agent.py        받아쓰기 — 자리표, 요청 가리기, 열어 둔 엑셀에 적기
    py tools\pc\check_old_yard.py     1차고지 — 열렸을 때·닫혔을 때, 다른 블록 침범 없음
    py tools\pc\check_warm.py         미리 데우기 — 누를 때 1~2초에 끝나는지
    py tools\pc\check_speed.py        한 번만 적는지, 걸리는 시간
    py tools\pc\check_print.py        인쇄 — 1차고지 가로, 두 번 뽑지 않기 (종이는 쓰지 않는다)
    py tools\pc\check_notice.py       안내 창 — 끝나면 바로 닫히는지
    py tools\pc\check_handoff.py      A → 사무실 PC → 폰 으로 결과가 건너가는지
    py tools\pc\check_checklist.py    점검 대상 목록이 폰까지 내려가는지

원본 엑셀은 건드리지 않는다. 모두 복사본을 만들어 그 위에서만 쓰고, 끝나면 지운다.
인쇄 검사는 `PrintOut` 자리를 가로채므로 종이가 나오지 않는다.
