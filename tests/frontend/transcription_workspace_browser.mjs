// #193/#194: production App/pages/CSS; all product I/O replaced with fixtures.
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { execFileSync } from 'node:child_process'
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const frontend = path.join(root, 'frontend')
const { createServer } = await import(pathToFileURL(path.join(frontend, 'node_modules/vite/dist/node/index.js')).href)
const { default: react } = await import(pathToFileURL(path.join(frontend, 'node_modules/@vitejs/plugin-react/dist/index.js')).href)
const mock = `
const params = new URLSearchParams(location.search);
const control = window.__workspace = {created:[], started:[], actions:[], uploads:[], engine:'local_whisper'};
const settings = {notifications:{file_complete:true,job_complete:true},close_behavior:'exit',shutdown:'disabled',transcription_folder:'synthetic',last_course:'기초이론',last_subject:'민법',last_engine:'local_whisper',subject_stage_overrides:{},drive_exam_root:'2026 테스트 시험'};
const files = Array.from({length:params.has('long')?80:3},(_,i)=>({id:'synthetic_'+(i+1),filename:'synthetic_'+(i+1)+'.mp3',completion_status:'INCOMPLETE',duration_seconds:120}));
let state = params.get('state') || 'IDLE';
const makeJob = () => ({job_id:'synthetic-job',folder:'synthetic',status:state,engine:control.engine,files:Object.fromEntries(files.map((f,i)=>[f.id,state==='FAILED'?(i===0?'FAILED':i===1?'DONE':'WAITING'):state==='DONE'?'DONE':i===0?state:'WAITING'])),drive:state==='FAILED'?{synthetic_2:{status:'FAILED',error:'synthetic upload failure'}}:{},events:[],total_files:files.length,done_files:state==='DONE'?files.length:state==='FAILED'?1:0,failed_files:state==='FAILED'?1:0,current_file:state==='TRANSCRIBING'?files[0].id:null,current_progress:state==='TRANSCRIBING'?42:null,error:state==='FAILED'?'Local Whisper 실행 환경이 현재 앱 빌드와 맞지 않습니다.':null});
export const api = {
 health:async()=>({status:'ok'}), settings:async()=>settings,saveSettings:async(v)=>Object.assign(settings,v),
 scan:async()=>files,jobs:async()=>state==='IDLE'?[]:[makeJob()],activeJob:async()=>state==='TRANSCRIBING'?makeJob():null,job:async()=>makeJob(),
 driveStatus:async()=>({auth_state:'CONNECTED'}),shutdown:async()=>({phase:'inactive'}),
 localRuntimeStatus:async()=>({available:false,code:'LOCAL_RUNTIME_PROVENANCE_MISMATCH',message:'Local Whisper 실행 환경이 현재 앱 빌드와 맞지 않습니다.'}),
 events:async()=>[{timestamp:new Date().toISOString(),category:'runtime',level:'error',message:'synthetic runtime failure'}],
 folders:async()=>({scan_id:'synthetic-scan',folder:'synthetic',items:[]}),
 normalizeBatch:async(_,names)=>names.map(n=>({original_name:n,suggested_name:n,result_type:'UNCHANGED',can_apply:false,warnings:[],conflicts:[],detected_course:'기초이론',detected_subject:'민법',detected_week:'1',detected_lesson:'1'})),
 createJob:async(v)=>{control.created.push(v);control.engine=v.engine;state='WAITING';return makeJob()},
 startJob:async(id)=>{control.started.push(id);state='TRANSCRIBING';return makeJob()},
 stopJob:async()=>{control.actions.push('stop');state='STOPPED';return makeJob()},cancelJob:async()=>{control.actions.push('cancel');state='CANCELLED';return makeJob()},retryJob:async()=>{control.actions.push('retry');state='TRANSCRIBING';return makeJob()},
 actionJob:async(_,action)=>{control.actions.push(action);state=action==='retry'?'TRANSCRIBING':action==='stop'?'STOPPED':'CANCELLED';return makeJob()},
 uploadDrive:async(...v)=>{control.uploads.push(v);return {}},
 startColabRendezvous:async()=>({state:'WAITING',request_id:'synthetic-request'}),verifyColabUrl:async()=>({state:'CONNECTED',base_url:'https://synthetic.trycloudflare.com'}),pollColabRendezvous:async()=>({state:'FOUND',base_url:'https://synthetic.trycloudflare.com'}),
};
export const getSavedFolder=()=> 'synthetic'; export const saveFolder=()=>{};
export const getUserMessage=e=>e.message; export const isRequestAbort=e=>e.name==='AbortError'; export const isRequestTimeout=()=>false;
`
const entry = `import React from 'react';import {createRoot} from 'react-dom/client';import App from '/src/App.tsx';
import '/src/styles/tokens.css';import '/src/styles/typography.css';import '/src/styles/base.css';import '/src/styles/components.css';import '/src/styles/app-shell.css';import '/src/styles/transcription-screen.css';import '/src/styles/feature-pages.css';
createRoot(document.getElementById('root')).render(React.createElement(App));`
const server = await createServer({configFile:false,root:frontend,logLevel:'error',resolve:{dedupe:['react','react-dom']},plugins:[react(),{
 name:'synthetic-workspace',enforce:'pre',resolveId(id){
  if(id.endsWith('/api/client'))return '\0workspace-api';
  if(id.endsWith('/lib/native'))return '\0workspace-native';
  if(/\/use(CloseBehaviorSync|DesktopNotifications|TrayProgress|FolderRevision)$/.test(id))return '\0workspace-hooks';
  if(id==='/__workspace_entry.js')return '\0workspace-entry';
 },load(id){
  if(id==='\0workspace-api')return mock;
  if(id==='\0workspace-entry')return entry;
  if(id==='\0workspace-native')return 'export const isTauri=()=>false;export const pickFolder=async()=>null;export const openInBrowser=async()=>{};export const openInExplorer=async()=>{};export const watchSidecarStatus=async(fn)=>{fn({state:"CONNECTED"});return ()=>{}};export const retrySidecarStartup=async()=>{};';
  if(id==='\0workspace-hooks')return 'export const useCloseBehaviorSync=()=>{};export const useDesktopNotifications=()=>{};export const useTrayProgress=()=>{};export const useFolderRevision=()=>{};';
  if(process.env.SORIGUL_QA_BASELINE==='1' && id.replaceAll('\\','/').startsWith(frontend.replaceAll('\\','/')+'/src/')) {
    const relative=path.relative(root,id.split('?')[0]).replaceAll('\\','/');
    return execFileSync('git',['show',`b86cb3b69af8ab3bf3ab6e94d3b5a04c27dfab66:${relative}`],{cwd:root,encoding:'utf8',windowsHide:true});
  }
 },configureServer(s){s.middlewares.use(async(req,res,next)=>{if(!req.url.startsWith('/__workspace__'))return next();res.setHeader('Content-Type','text/html; charset=utf-8');res.end(await s.transformIndexHtml(req.url,'<!doctype html><html><body><div id="root"></div><script type="module" src="/__workspace_entry.js"></script></body></html>'));})}
}],server:{host:'127.0.0.1',port:0}})
await server.listen()
console.log(`READY http://127.0.0.1:${server.httpServer.address().port}/__workspace__`)
process.on('SIGTERM',async()=>{await server.close();process.exit(0)})
