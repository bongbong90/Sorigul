import { useState, useEffect } from 'react'
import { api } from '../../api/client'
import type { RendezvousState } from '../../api/client'
import { AlertTriangle, CheckCircle, Loader2 } from 'lucide-react'

interface EngineSectionProps {
  engine: 'local_whisper' | 'direct_colab'
  onChangeEngine: (engine: 'local_whisper' | 'direct_colab') => void
  connectedBaseUrl: string | null
  onBaseUrlChange: (url: string | null) => void
  disabled: boolean
}

export function EngineSection({ engine, onChangeEngine, connectedBaseUrl, onBaseUrlChange, disabled }: EngineSectionProps) {
  const [colabState, setColabState] = useState<RendezvousState['state']>('WAITING')
  const [requestId, setRequestId] = useState<string | null>(null)
  const [showManual, setShowManual] = useState(false)
  const [manualUrl, setManualUrl] = useState('')
  const [verifying, setVerifying] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')

  useEffect(() => {
    let timer: number
    if (engine === 'direct_colab' && requestId && (colabState === 'WAITING' || colabState === 'FOUND')) {
      timer = window.setInterval(async () => {
        try {
          const res = await api.pollColabRendezvous(requestId)
          if (res.state === 'FOUND' && res.base_url) {
            setColabState('FOUND')
            setVerifying(true)
            clearInterval(timer)
            try {
              const verifyRes = await api.verifyColabUrl(res.base_url)
              if (verifyRes.state === 'CONNECTED' && verifyRes.base_url) {
                setColabState('CONNECTED')
                onBaseUrlChange(verifyRes.base_url)
                setErrorMsg('')
              } else {
                setColabState('FAILED')
                setErrorMsg('연결 확인에 실패했습니다.')
              }
            } catch (err: any) {
              setColabState('FAILED')
              setErrorMsg(err.userMessage || '오류가 발생했습니다.')
            } finally {
              setVerifying(false)
            }
          } else if (res.state !== 'WAITING') {
            setColabState(res.state)
            if (res.state === 'AUTH_REQUIRED') setErrorMsg('Google Drive 인증이 필요합니다.')
            else if (res.state === 'EXPIRED') setErrorMsg('연결 대기 시간이 만료되었습니다.')
            else if (res.state === 'FAILED') setErrorMsg('Colab 연결에 실패했습니다.')
            clearInterval(timer)
          }
        } catch (e) {
          // ignore transient poll errors
        }
      }, 3000)
    }
    return () => clearInterval(timer)
  }, [engine, requestId, colabState, onBaseUrlChange])

  const handleStartRendezvous = async () => {
    try {
      setColabState('WAITING')
      setErrorMsg('')
      onBaseUrlChange(null)
      const res = await api.startColabRendezvous()
      if (res.state === 'WAITING' && res.request_id) {
        setRequestId(res.request_id)
      } else {
        setColabState(res.state)
        if (res.state === 'AUTH_REQUIRED') setErrorMsg('Google Drive 인증이 필요합니다.')
        else setErrorMsg('연결 시작에 실패했습니다.')
      }
    } catch (err: any) {
      setColabState('FAILED')
      setErrorMsg(err.userMessage || '오류가 발생했습니다.')
    }
  }

  const handleManualVerify = async () => {
    if (!manualUrl) return
    try {
      setVerifying(true)
      setErrorMsg('')
      onBaseUrlChange(null)
      const res = await api.verifyColabUrl(manualUrl)
      if (res.state === 'CONNECTED' && res.base_url) {
        setColabState('CONNECTED')
        onBaseUrlChange(res.base_url)
      } else {
        setColabState('FAILED')
        setErrorMsg('연결 확인에 실패했습니다.')
      }
    } catch (err: any) {
      setColabState('FAILED')
      setErrorMsg(err.userMessage || '오류가 발생했습니다.')
    } finally {
      setVerifying(false)
    }
  }

  return (
    <div className="bg-white p-6 rounded-xl border border-gray-100 shadow-sm space-y-4">
      <h3 className="font-semibold text-gray-900">전사 엔진 선택</h3>
      
      <div className="flex gap-4">
        <label className={"flex-1 flex items-center p-4 border rounded-lg cursor-pointer transition-colors " + (
          engine === 'local_whisper' ? 'border-primary-500 bg-primary-50' : 'border-gray-200 hover:bg-gray-50'
        ) + " " + (disabled ? 'opacity-50 pointer-events-none' : '')}>
          <input
            type="radio"
            name="engine"
            value="local_whisper"
            checked={engine === 'local_whisper'}
            onChange={() => onChangeEngine('local_whisper')}
            className="sr-only"
            disabled={disabled}
          />
          <div className="flex-1">
            <div className="font-medium text-gray-900">Local</div>
            <div className="text-sm text-gray-500">Whisper medium</div>
          </div>
          {engine === 'local_whisper' && <CheckCircle className="w-5 h-5 text-primary-500" />}
        </label>

        <label className={"flex-1 flex items-center p-4 border rounded-lg cursor-pointer transition-colors " + (
          engine === 'direct_colab' ? 'border-primary-500 bg-primary-50' : 'border-gray-200 hover:bg-gray-50'
        ) + " " + (disabled ? 'opacity-50 pointer-events-none' : '')}>
          <input
            type="radio"
            name="engine"
            value="direct_colab"
            checked={engine === 'direct_colab'}
            onChange={() => onChangeEngine('direct_colab')}
            className="sr-only"
            disabled={disabled}
          />
          <div className="flex-1">
            <div className="font-medium text-gray-900">Colab</div>
            <div className="text-sm text-gray-500">Whisper medium (GPU)</div>
          </div>
          {engine === 'direct_colab' && <CheckCircle className="w-5 h-5 text-primary-500" />}
        </label>
      </div>

      {engine === 'direct_colab' && (
        <div className="p-4 bg-gray-50 rounded-lg space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-gray-700">Colab 연결 상태:</span>
              {connectedBaseUrl ? (
                <span className="text-sm text-green-600 flex items-center gap-1">
                  <CheckCircle className="w-4 h-4" /> 연결됨
                </span>
              ) : verifying || (requestId && colabState === 'FOUND') ? (
                <span className="text-sm text-blue-600 flex items-center gap-1">
                  <Loader2 className="w-4 h-4 animate-spin" /> 연결 확인 중...
                </span>
              ) : requestId && colabState === 'WAITING' ? (
                <span className="text-sm text-yellow-600 flex items-center gap-1">
                  <Loader2 className="w-4 h-4 animate-spin" /> 연결 대기 중...
                </span>
              ) : (
                <span className="text-sm text-gray-500">연결 안 됨</span>
              )}
            </div>
            
            <button
              onClick={handleStartRendezvous}
              disabled={disabled || verifying || (requestId !== null && colabState === 'WAITING')}
              className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-md hover:bg-primary-700 disabled:opacity-50"
            >
              Colab 연결
            </button>
          </div>

          {errorMsg && (
            <div className="text-sm text-red-600 flex items-center gap-1">
              <AlertTriangle className="w-4 h-4" /> {errorMsg}
            </div>
          )}

          <div className="pt-2 border-t border-gray-200">
            {!showManual ? (
              <button
                type="button"
                onClick={() => setShowManual(true)}
                className="text-sm text-gray-500 hover:text-gray-700 underline"
              >
                직접 URL 입력
              </button>
            ) : (
              <div className="flex gap-2">
                <input
                  type="text"
                  value={manualUrl}
                  onChange={e => setManualUrl(e.target.value)}
                  placeholder="https://xxxxx.trycloudflare.com"
                  className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-primary-500"
                  disabled={disabled || verifying}
                />
                <button
                  onClick={handleManualVerify}
                  disabled={disabled || verifying || !manualUrl}
                  className="px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50"
                >
                  확인
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
