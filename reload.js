// reload the current page based on file changes

// is "?v={{ range(1, 51) | random }}" required? apparently not

function reload_page () {
  location.reload(true)
}

class ReloadWebsocket {
  constructor() {
    this._socket = null
    this.connect()
    this._connected = false
    this._clear_connected = null
  }

  connect = () => {
    console.debug('websocket connecting...')
    this._connected = false
    const proto = location.protocol.replace('http', 'ws')
    const url = `${proto}//${window.location.host}/.devtools/reload/`
    try {
      this._socket = new WebSocket(url)
    } catch (error) {
      console.warn('ws connection error', error)
      this._socket = null
      return
    }

    this._socket.onclose = this._on_close
    this._socket.onerror = this._on_error
    this._socket.onmessage = this._on_message
    this._socket.onopen = this._on_open
  }

  _on_open = () => {
    console.debug('websocket open')
    setTimeout(() => {
      this._connected = true
    }, 1000)
  }

  _on_message = event => {
    if (event.data !== 'reload') {
      console.warn('unexpected websocket message:', event)
      return
    }
    if (this._connected) {
      console.debug('files changed, reloading', event)
      reload_page()
    }
  }

  _on_error = event => {
    console.debug('websocket error', event)
    clearInterval(this._clear_connected)
  }

  _on_close = event => {
    clearInterval(this._clear_connected)
    if (this._connected) {
      console.debug('websocket closed, reloading', event)
      reload_page()
    } else {
      console.debug('websocket closed, reconnecting in 2s...', event)
      setTimeout(this.connect, 2000)
    }
  }
}

const reload = new ReloadWebsocket()
