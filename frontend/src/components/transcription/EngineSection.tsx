import { useState, useEffect, useRef } from 'react'
import { api, getUserMessage, isRequestAbort, isRequestTimeout } from '../../api/client'
import type { RendezvousState } from '../../api/client'
import { AlertTriangle, CheckCircle, Loader2 } from 'lucide-react'
import { Button } from '../ui/Button'

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
  const [manualModeActive, setManualModeActive] = useState(false)
  const [connectionUncertain, setConnectionUncertain] = useState(false)
  const [startingRendezvous, setStartingRendezvous] = useState(false)
  const manualModeRef = useRef(false)
  const operationControllerRef = useRef<AbortController | null>(null)

  useEffect(() => {
    operationControllerRef.current?.abort()
    operationControllerRef.current = null
    setStartingRendezvous(false)
    if (engine === 'local_whisper') {
      setRequestId(null)
      setColabState('WAITING')
      setVerifying(false)
      setErrorMsg('')
      setManualModeActive(false)
      setConnectionUncertain(false)
      manualModeRef.current = false
    }
    return () => {
      operationControllerRef.current?.abort()
      operationControllerRef.current = null
    }
  }, [engine])

  useEffect(() => {
    let active = true
    let timer: number | undefined
    let controller: AbortController | undefined
    if (engine === 'direct_colab' && requestId && !manualModeActive && !connectionUncertain && !startingRendezvous) {
      const schedule = () => {
        if (active && !manualModeRef.current) timer = window.setTimeout(() => void poll(), 3000)
      }
      const poll = async () => {
        if (manualModeRef.current) return
        controller = new AbortController()
        try {
          const res = await api.pollColabRendezvous(requestId, controller.signal)
          if (!active || manualModeRef.current) return
          if (res.state === 'FOUND' && res.base_url) {
            setColabState('FOUND')
            setVerifying(true)
            try {
              const verifyRes = await api.verifyColabUrl(res.base_url, requestId, controller.signal)
              if (!active || manualModeRef.current) return
              if (verifyRes.state === 'CONNECTED' && verifyRes.base_url) {
                setColabState('CONNECTED')
                setConnectionUncertain(false)
                onBaseUrlChange(verifyRes.base_url)
                setErrorMsg('')
              } else {
                setColabState('FAILED')
                setErrorMsg('연결 확인에 실패했습니다.')
              }
            } catch (error) {
              if (!active || isRequestAbort(error)) return
              if (isRequestTimeout(error)) {
                setColabState('WAITING')
                setConnectionUncertain(true)
                setErrorMsg(getUserMessage(error))
              } else {
                setColabState('FAILED')
                setConnectionUncertain(false)
                setErrorMsg(getUserMessage(error))
              }
            } finally {
              if (active) setVerifying(false)
            }
          } else if (res.state !== 'WAITING') {
            setColabState(res.state)
            setConnectionUncertain(false)
            if (res.state === 'AUTH_REQUIRED') setErrorMsg('Google Drive 인증이 필요합니다.')
            else if (res.state === 'EXPIRED') setErrorMsg('연결 대기 시간이 만료되었습니다.')
            else if (res.state === 'FAILED') setErrorMsg('Colab 연결에 실패했습니다.')
          } else schedule()
        } catch (error) {
          if (!active || isRequestAbort(error)) return
          if (isRequestTimeout(error)) setErrorMsg(getUserMessage(error))
          schedule()
        }
      }
      schedule()
    }
    return () => {
      active = false
      if (timer !== undefined) window.clearTimeout(timer)
      controller?.abort()
    }
  }, [engine, requestId, manualModeActive, connectionUncertain, startingRendezvous, onBaseUrlChange])

  const handleStartRendezvous = async () => {
    const controller = new AbortController()
    operationControllerRef.current?.abort()
    operationControllerRef.current = controller
    setStartingRendezvous(true)
    setConnectionUncertain(false)
    try {
      setColabState('WAITING')
      setRequestId(null)
      setErrorMsg('')
      setManualModeActive(false)
      manualModeRef.current = false
      onBaseUrlChange(null)
      const res = await api.startColabRendezvous(controller.signal)
      if (res.state === 'WAITING' && res.request_id) {
        setRequestId(res.request_id)
        setConnectionUncertain(false)
      } else {
        setColabState(res.state)
        setConnectionUncertain(false)
        if (res.state === 'AUTH_REQUIRED') setErrorMsg('Google Drive 인증이 필요합니다.')
        else setErrorMsg('연결 시작에 실패했습니다.')
      }
    } catch (error) {
      if (isRequestAbort(error)) return
      if (isRequestTimeout(error)) setConnectionUncertain(true)
      else {
        setColabState('FAILED')
        setConnectionUncertain(false)
      }
      setErrorMsg(getUserMessage(error))
    } finally {
      if (operationControllerRef.current === controller) {
        operationControllerRef.current = null
        setStartingRendezvous(false)
      }
    }
  }

  const handleManualVerify = async () => {
    if (!manualUrl) return
    const controller = new AbortController()
    operationControllerRef.current?.abort()
    operationControllerRef.current = controller
    try {
      setManualModeActive(true)
      manualModeRef.current = true
      setConnectionUncertain(false)
      setVerifying(true)
      setErrorMsg('')
      onBaseUrlChange(null)
      let pairingRequestId = requestId
      if (!pairingRequestId || ['EXPIRED', 'FAILED', 'PAIRING_REQUIRED'].includes(colabState)) {
        const started = await api.startColabRendezvous(controller.signal)
        if (started.state !== 'WAITING' || !started.request_id) {
          setColabState(started.state)
          setConnectionUncertain(false)
          setErrorMsg(
            started.state === 'AUTH_REQUIRED'
              ? 'Google Drive 인증이 필요합니다.'
              : '보안 연결 시작에 실패했습니다.',
          )
          return
        }
        pairingRequestId = started.request_id
        setRequestId(pairingRequestId)
        setColabState('WAITING')
      }
      const res = await api.verifyColabUrl(manualUrl, pairingRequestId, controller.signal)
      if (res.state === 'CONNECTED' && res.base_url) {
        setColabState('CONNECTED')
        setConnectionUncertain(false)
        onBaseUrlChange(res.base_url)
      } else {
        setColabState(res.state)
        if (res.state !== 'WAITING') setConnectionUncertain(false)
        if (res.state === 'WAITING') setErrorMsg('Colab 런타임의 보안 연결 준비를 기다리고 있습니다. 다시 확인해 주세요.')
        else if (res.state === 'AUTH_REQUIRED') setErrorMsg('Google Drive 연결이 필요합니다.')
        else if (res.state === 'EXPIRED') setErrorMsg('연결 대기 시간이 만료되었습니다. 다시 확인해 주세요.')
        else if (res.state === 'PAIRING_REQUIRED') setErrorMsg('보안 연결 정보가 만료되었습니다. 다시 확인해 주세요.')
        else setErrorMsg('연결 확인에 실패했습니다.')
      }
    } catch (error) {
      if (isRequestAbort(error)) return
      if (isRequestTimeout(error)) setConnectionUncertain(true)
      else {
        setColabState('FAILED')
        setConnectionUncertain(false)
      }
      setErrorMsg(getUserMessage(error))
    } finally {
      if (operationControllerRef.current === controller) {
        operationControllerRef.current = null
        setVerifying(false)
      }
    }
  }

  return (
    <section className="card engine-section" aria-labelledby="engine-section-title">
      <h3 id="engine-section-title" className="engine-section-title">전사 엔진 선택</h3>
      
      <div className="engine-options">
        <label className={`engine-option${engine === 'local_whisper' ? ' engine-option-selected' : ''}${disabled ? ' engine-option-disabled' : ''}`}>
          <input
            type="radio"
            name="engine"
            value="local_whisper"
            checked={engine === 'local_whisper'}
            onChange={() => onChangeEngine('local_whisper')}
            className="visually-hidden"
            disabled={disabled}
          />
          <div className="engine-option-copy">
            <strong>Local</strong>
            <span>Whisper medium</span>
          </div>
          {engine === 'local_whisper' && <CheckCircle className="engine-icon" aria-hidden="true" />}
        </label>

        <label className={`engine-option${engine === 'direct_colab' ? ' engine-option-selected' : ''}${disabled ? ' engine-option-disabled' : ''}`}>
          <input
            type="radio"
            name="engine"
            value="direct_colab"
            checked={engine === 'direct_colab'}
            onChange={() => onChangeEngine('direct_colab')}
            className="visually-hidden"
            disabled={disabled}
          />
          <div className="engine-option-copy">
            <strong>Colab</strong>
            <span>Whisper medium (GPU)</span>
          </div>
          {engine === 'direct_colab' && <CheckCircle className="engine-icon" aria-hidden="true" />}
        </label>
      </div>

      {engine === 'direct_colab' && (
        <div className="engine-colab-panel">
          <div className="engine-status-row">
            <div className="engine-status-copy">
              <span className="engine-status-label">Colab 연결 상태:</span>
              {connectedBaseUrl ? (
                <span className="engine-state engine-state-connected">
                  <CheckCircle className="engine-icon-small" aria-hidden="true" /> 연결됨
                </span>
              ) : connectionUncertain ? (
                <span className="engine-state engine-state-waiting">
                  <AlertTriangle className="engine-icon-small" aria-hidden="true" /> 연결 결과 확인 필요
                </span>
              ) : verifying || (requestId && colabState === 'FOUND') ? (
                <span className="engine-state engine-state-verifying">
                  <Loader2 className="engine-icon-small engine-spinner" aria-hidden="true" /> 연결 확인 중...
                </span>
              ) : requestId && colabState === 'WAITING' ? (
                <span className="engine-state engine-state-waiting">
                  <Loader2 className="engine-icon-small engine-spinner" aria-hidden="true" /> 연결 대기 중...
                </span>
              ) : (
                <span className="engine-state">연결 안 됨</span>
              )}
            </div>
            
            <Button
              onClick={handleStartRendezvous}
              disabled={disabled || verifying || startingRendezvous || (requestId !== null && colabState === 'WAITING' && !connectionUncertain)}
            >
              Colab 연결
            </Button>
          </div>

          {errorMsg && (
            <div className="engine-error" role="alert">
              <AlertTriangle className="engine-icon-small" aria-hidden="true" /> {errorMsg}
            </div>
          )}

          <div className="engine-manual-section">
            <p className="engine-zero-cost-note">
              사용자가 직접 시작한 Colab 런타임에만 연결합니다. 유료 크레딧 소비가 전혀 없어야 하면 Local 엔진을 사용하세요.
            </p>
            {!showManual ? (
              <button
                type="button"
                onClick={() => setShowManual(true)}
                className="text-action engine-manual-toggle"
              >
                직접 URL 입력
              </button>
            ) : (
              <div className="engine-manual-controls">
                <input
                  type="text"
                  value={manualUrl}
                  onChange={e => setManualUrl(e.target.value)}
                  placeholder="https://xxxxx.trycloudflare.com"
                  className="input engine-manual-input"
                  disabled={disabled || verifying || startingRendezvous}
                />
                <Button
                  variant="secondary"
                  onClick={handleManualVerify}
                  disabled={disabled || verifying || startingRendezvous || !manualUrl}
                >
                  확인
                </Button>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
