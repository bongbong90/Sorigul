# Sorigul Frontend Foundation

## 목적

`frontend/`를 향후 Design System / App Shell / Transcription UI를
구현할 수 있는 React 개발 기반으로 구축한다.

이 문서는 Frontend Foundation Phase의 작업 기록이며,
제품 화면이나 실제 기능은 포함하지 않는다.

## 기술 스택

- React
- TypeScript
- Vite
- npm

## frontend 구조

```
frontend/
├─ index.html
├─ package.json
├─ package-lock.json
├─ tsconfig.json
├─ vite.config.ts
└─ src/
   ├─ main.tsx
   ├─ App.tsx
   ├─ components/
   ├─ pages/
   ├─ styles/
   │  └─ base.css
   ├─ assets/
   ├─ hooks/
   ├─ lib/
   └─ types/
```

## 실행 명령

```
cd frontend
npm install
npm run dev
```

## 검증 명령

```
npm run lint
npm run typecheck
npm run build
```

## 현재 비범위

- Design System (Color / Typography / Spacing / Radius / Shadow token)
- App Shell (Sidebar / Navigation)
- Transcription Screen
- Mock Interaction
- Dashboard / Results
- 실제 파일 시스템 / backend 연동

## 다음 단계

Design System Foundation
