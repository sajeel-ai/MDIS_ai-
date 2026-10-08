import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

const scrollbarTimers = new WeakMap<Element, number>()

document.addEventListener(
  'scroll',
  (event) => {
    const scroller =
      event.target instanceof Element ? event.target : document.documentElement
    scroller.classList.add('scrollbar-visible')
    const previousTimer = scrollbarTimers.get(scroller)
    if (previousTimer !== undefined) window.clearTimeout(previousTimer)
    scrollbarTimers.set(
      scroller,
      window.setTimeout(() => {
        scroller.classList.remove('scrollbar-visible')
        scrollbarTimers.delete(scroller)
      }, 700),
    )
  },
  { capture: true, passive: true },
)

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
