# Sorigul Transcription Screen Specification

## Screen Purpose

사용자가 전사 대상,
현재 파일,
전체 작업 상태를
한 화면에서 이해할 수 있도록 한다.

## App Shell

Sidebar:

- 소리글
- 전사
- 로그
- Folders
- 설정

기본 진입 화면은 `전사`이며 Dashboard 전용 화면은 사용하지 않는다.

## Folder Area

- 현재 폴더
- Folder Path
- 폴더 변경

## Current Task

- 현재 파일
- 상태
- 진행률
- ETA

## Overall Progress

DONE 파일 수 / 전체 대상 수

TRANSCRIBING과 SAVING은
완료 수에 포함하지 않는다.

## Queue Table

Columns:

- 선택
- 파일명
- 재생시간
- 상태

## Primary Actions

IDLE:

전사 시작 = enabled
전사 중지 = disabled

선택 파일이 없을 때도 전사 시작은 enabled다. Start 시 완료 bundle을 제외한 전체 범위를 확인하고, 확인 화면에는 가능한 범위에서 전체 파일 수, skip 수, 실제 처리 대상 수를 표시한다. 실제 처리 대상이 0개면 작업을 시작하지 않는다.

TRANSCRIBING:

전사 시작 = disabled
전사 중지 = enabled

전사 중 Stop은 현재 파일을 `STOPPED`로 만든다. 대기 또는 작업 자체의 Cancel은 `CANCELLED`로 구분하며, 두 상태의 Retry는 현재 파일을 처음부터 처리한다.

## Long Filename

- 한 줄 ellipsis
- 전체 이름 확인 가능
- 다른 Column 침범 금지

## Accessibility

- 색상만으로 상태 표현 금지
- Keyboard focus 제공
- Icon accessible label 필요
