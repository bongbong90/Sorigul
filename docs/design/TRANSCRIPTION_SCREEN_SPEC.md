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
- 대시보드
- 결과
- 설정

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

TRANSCRIBING:

전사 시작 = disabled
전사 중지 = enabled

## Long Filename

- 한 줄 ellipsis
- 전체 이름 확인 가능
- 다른 Column 침범 금지

## Accessibility

- 색상만으로 상태 표현 금지
- Keyboard focus 제공
- Icon accessible label 필요
