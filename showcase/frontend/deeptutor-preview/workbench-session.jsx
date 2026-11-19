import { useEffect, useRef, useState } from 'react'
import { mountSession } from '../chat-frontend/src/mount-session'
import './app/session.css'

export default function SavedSession({ id }) {
  const host = useRef(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    mountSession(host.current, id, controller.signal).catch(failure => {
      if (!controller.signal.aborted) setError(failure.message)
    })
    return () => controller.abort()
  }, [id, attempt])
  return <div className="session-surface">
    {error && <p role="alert">{error} <button onClick={() => {setError(''); setAttempt(n => n+1)}}>重新连接</button></p>}
    <div ref={host}/>
  </div>
}
